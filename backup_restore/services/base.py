import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List

import requests
from pydantic import BaseModel, Field


class State(BaseModel):
    """
    State class to manage the schemas and dependencies of different entities
    in a service. It automatically initializes schemas and dependencies from
    the fields defined in the child class.

    Attributes:
        schemas (Dict[str, Any]): A dictionary mapping field names to their corresponding schema data.
        dependencies (Dict[str, List[str]]): A dictionary mapping field names to a list of their dependencies.
    """

    schemas: Dict[str, Any] = Field(default_factory=dict)
    dependencies: Dict[str, List[str]] = Field(default_factory=dict)
    id: str = Field(default_factory=str)

    def __init__(self, **data):
        """
        Initialize the State object and automatically populate the schemas and dependencies
        based on the fields defined in the child class.
        """
        super().__init__(**data)
        self._initialize_schemas_and_dependencies()
        self.id = self._generate_id()

    def _generate_id(self):
        """
        Generate a unique identifier for the State object.
        """
        return uuid.uuid4().hex

    def _initialize_schemas_and_dependencies(self):
        """
        Populate the schemas and dependencies based on the fields defined in the child class.
        """
        for field_name, field_info in self.model_fields.items():
            if field_name in {"schemas", "dependencies", "id"}:
                continue

            # Store the field value in schemas
            self.schemas[field_name] = getattr(self, field_name)

            # Extract dependencies from the field's extra metadata
            self.dependencies[field_name] = (
                getattr(field_info, "json_schema_extra", {}) or {}
            ).get("depends_on", [])

    class Config:
        arbitrary_types_allowed = True


class StateValidator:
    def __init__(self, state, locator=None):
        self.state = state
        self.locator = locator
        self.__validator__()

    def __validator__(self):
        print(f"Validating {self.locator} state... methods and dependencies")
        if self.locator is None:
            raise ValueError(
                f"Validation error, missing state locator for {self.__class__.__name__}"
            )

        locator = f"_{self.locator}_"
        _methods = [method for method in dir(self) if method.startswith(locator)]
        _methods_obj_names = [method[len(locator) :] for method in _methods]

        for obj_name, _ in self.state.dependencies.items():
            if obj_name not in _methods_obj_names:
                raise ValueError(f"Missing {locator} method for {obj_name}.")
        if len(_methods) != len(self.state.schemas):
            raise ValueError(f"Mismatch between schemas and {locator} methods.")


class Export(StateValidator):
    def __init__(self, state):
        super().__init__(state, "export")
        # Additional initialization for Export if needed


class Import(StateValidator):
    def __init__(self, state):
        super().__init__(state, "import")
        # Additional initialization for Import if needed


class Service(ABC):
    """
    Abstract base class for handling import/export operations with dependency management.

    Attributes:
        state (State): The state object holding schemas and dependencies.
    """

    name: str = "Service"
    version: str = "1.0"
    priority: int = 0
    type: str = "Serial"

    def __init__(self, config=dict) -> None:
        super().__init__()
        self.state = State()
        self.config = config
        self.importer = Import(self.state)
        self.exporter = Export(self.state)

    @abstractmethod
    def backup(self, storage_client, **kwargs) -> None:
        """Abstract method for backing up the service data."""
        pass

    @abstractmethod
    def restore(self, storage_client, **kwargs) -> None:
        """Abstract method for restoring the service data."""
        pass


# TODO: to be replaced or removed (as we now have an API client class)
class APIService(Service):
    """
    Abstract subclass of Services that provides common functionality for services that
    interact with RESTful APIs. Includes methods for making HTTP GET and POST requests,
    and for handling import/export operations.

    Attributes:
        token (str): The authentication token used for API requests.
        auth (Dict[str, str]): A dictionary containing authentication details.
    """

    def __init__(self, auth: Dict[str, str] = None) -> None:
        super().__init__()
        self.auth = auth or self.config.get("auth", {})
        self.token = None

    def get(self, endpoint: str, **kwargs):
        """
        Perform a GET request to the given endpoint.

        Args:
            endpoint (str): The API endpoint to send the GET request to.

        Returns:
            dict: The JSON response from the API.
        """
        url = self._build_url(endpoint, **kwargs)
        headers = self._build_headers()
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    def post(self, endpoint: str, json: dict, **kwargs):
        """
        Perform a POST request to the given endpoint.

        Args:
            endpoint (str): The API endpoint to send the POST request to.
            json (dict): The JSON payload to send in the POST request.

        Returns:
            dict: The JSON response from the API.
        """
        url = self._build_url(endpoint, **kwargs)
        headers = self._build_headers(content_type="application/json")
        response = requests.post(url, json=json, headers=headers)
        response.raise_for_status()
        return response.json()

    def _build_url(self, endpoint: str, **kwargs) -> str:
        return self.auth["url"] + endpoint.format(realm=self.auth["realm"], **kwargs)

    def _build_headers(self, content_type: str = None) -> dict:
        """
        Build the headers for the HTTP request.
        """
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if content_type:
            headers["Content-Type"] = content_type
        return headers
