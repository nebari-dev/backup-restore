from http.client import HTTPException
import json
import os
import shutil
import uuid
from collections import defaultdict, deque
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional
import httpx

import requests
from backup_restore.services.base import Export, Import, Service, State
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from requests.exceptions import RequestException


class ClientSchema(BaseModel):
    client_id: str = Field(None, alias="clientId")
    name: Optional[str] = None
    description: Optional[str] = None
    rootUrl: Optional[str] = Field(None, alias="rootUrl")
    baseUrl: Optional[str] = Field(None, alias="baseUrl")
    redirectUris: Optional[List[str]] = Field(
        default_factory=list, alias="redirectUris"
    )
    enabled: bool = True

    class Config:
        populate_by_name = True


class UserSchema(BaseModel):
    username: str
    email: Optional[str] = None
    firstName: Optional[str] = Field(None, alias="firstName")
    lastName: Optional[str] = Field(None, alias="lastName")
    enabled: bool = True
    emailVerified: bool = Field(False, alias="emailVerified")
    attributes: Optional[Dict[str, List[str]]] = Field(default_factory=dict)

    class Config:
        populate_by_name = True


class GroupSchema(BaseModel):
    id: Optional[str] = None
    name: str
    path: Optional[str] = None
    attributes: Optional[Dict[str, List[str]]] = Field(default_factory=dict)
    subGroups: Optional[List["GroupSchema"]] = Field(
        default_factory=list, alias="subGroups"
    )

    class Config:
        populate_by_name = True


class RoleSchema(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    composite: bool = False
    clientRole: bool = Field(False, alias="clientRole")
    containerId: Optional[str] = Field(None, alias="containerId")

    class Config:
        populate_by_name = True


class IdentityProviderSchema(BaseModel):
    alias: str
    displayName: Optional[str] = Field(None, alias="displayName")
    providerId: str
    enabled: bool = True
    trustEmail: bool = Field(False, alias="trustEmail")
    storeToken: bool = Field(False, alias="storeToken")
    addReadTokenRoleOnCreate: bool = Field(False, alias="addReadTokenRoleOnCreate")
    config: Optional[Dict[str, str]] = Field(default_factory=dict)

    class Config:
        populate_by_name = True


class KeycloakSkeleton(State):
    clients: List[ClientSchema] = Field(default_factory=list)
    users: List[UserSchema] = Field(default_factory=list, depends_on=["groups"])
    groups: List[GroupSchema] = Field(default_factory=list)
    roles: List[RoleSchema] = Field(default_factory=list, depends_on=["clients"])
    identity_providers: List[IdentityProviderSchema] = Field(default_factory=list)
    id: Optional[str] = Field(uuid.uuid4(), alias="reference_id", internal=True)


class KeycloakAuth(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KEYCLOAK_")
    auth_url: AnyHttpUrl = Field(...)
    realm: str = Field("master")
    client_id: str = Field("admin-cli")
    client_secret: str = Field(...)
    verify_ssl: bool = Field(True)


class KeycloakAPIClient:
    """
    Handles direct interactions with the Keycloak API, including GET and POST requests.
    This class is independent of the business logic for exporting and importing data.
    """

    def __init__(self, auth: Dict[str, str]):
        self.auth = auth
        print(f"Auth: {self.auth}")
        self.token = None

    async def _authenticate(self) -> None:
        """
        Authenticate with Keycloak and cache the token. If a cached token exists,
        check its validity using Keycloak's token introspection endpoint.
        """
        if self.token and await self._is_token_valid():
            return

        try:
            print(f"Authenticating with Keycloak at {self.auth['auth_url']}...")
            async with httpx.AsyncClient(
                verify=self.auth.get("verify_ssl", True),
            ) as client:
                response = await client.post(
                    url=f"{self.auth['auth_url']}/realms/{self.auth['realm']}/protocol/openid-connect/token",
                    data={
                        "client_id": self.auth["client_id"],
                        "client_secret": self.auth["client_secret"],
                        "grant_type": "client_credentials",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                self.token = response.json().get("access_token")
        except httpx.RequestError as e:
            raise RuntimeError(f"Failed to authenticate with Keycloak: {e}")

    async def _is_token_valid(self) -> bool:
        """
        Validate the current cached token using Keycloak's token introspection endpoint.

        Returns:
            bool: True if the token is valid, False otherwise.
        """
        try:
            async with httpx.AsyncClient(
                verify=self.auth.get("verify_ssl", True),
            ) as client:
                introspection_response = await client.post(
                    url=f"{self.auth['auth_url']}/realms/{self.auth['realm']}/protocol/openid-connect/token/introspect",
                    data={
                        "client_id": self.auth["client_id"],
                        "client_secret": self.auth["client_secret"],
                        "token": self.token,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                introspection_response.raise_for_status()
                return introspection_response.json().get("active", False)
        except httpx.RequestError as e:
            raise RuntimeError(f"Token introspection failed: {e}")

    async def get(self, endpoint: str) -> List[Dict[str, Any]]:
        """
        Make a GET request to the Keycloak API.
        """
        await self._authenticate()
        try:
            url = f"{self.auth['auth_url']}{endpoint.format(realm=self.auth['realm'])}"
            print(f"GET request to {url}")
            async with httpx.AsyncClient(
                verify=self.auth.get("verify_ssl", True)
            ) as client:
                response = await client.get(
                    url=url,
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise RuntimeError(
                    f"GET request to {endpoint} failed with 403 Forbidden: "
                    f"The current client may not have sufficient permissions "
                    f"over the realm '{self.auth['realm']}'. Please check the corresponding service account roles."
                )
            raise RuntimeError(f"GET request to {endpoint} failed: {e}")
        except httpx.RequestError as e:
            raise RuntimeError(f"GET request to {endpoint} failed: {e}")

    async def post(self, endpoint: str, json: Dict[str, Any]) -> None:
        """
        Make a POST request to the Keycloak API.
        """
        await self._authenticate()
        try:
            url = f"{self.auth['auth_url']}{endpoint.format(realm=self.auth['realm'])}"
            print(f"POST request to {url}")
            async with httpx.AsyncClient(
                verify=self.auth.get("verify_ssl", True)
            ) as client:
                response = await client.post(
                    url=url,
                    json=json,
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise RuntimeError(
                    f"POST request to {endpoint} failed with 403 Forbidden: "
                    f"The current client may not have sufficient permissions "
                    f"over the realm '{self.auth['realm']}'. Please check the corresponding service account roles."
                )
            raise RuntimeError(f"POST request to {endpoint} failed: {e}")
        except httpx.RequestError as e:
            raise RuntimeError(f"POST request to {endpoint} failed: {e}")


class KeycloakExport(Export):
    """
    Handles the export of Keycloak data to predefined schemas.
    """

    def __init__(self, api_client: KeycloakAPIClient, state: KeycloakSkeleton):
        self.api_client = api_client
        self.state = state

    async def _export_clients(self) -> dict:
        print("Exporting client data from Keycloak...")
        data = await self.api_client.get("/admin/realms/{realm}/clients")
        result = [ClientSchema(**item).model_dump() for item in data]
        if not result:
            raise HTTPException(status_code=500, detail="Operation failed")
        return {"message": "Export clients completed successfully", "result": result}

    async def _export_users(self) -> dict:
        print("Exporting user data from Keycloak...")
        data = await self.api_client.get("/admin/realms/{realm}/users")
        result = [UserSchema(**item).model_dump() for item in data]
        if not result:
            raise HTTPException(status_code=500, detail="Operation failed")
        return {"message": "Export users completed successfully", "result": result}

    async def _export_groups(self) -> dict:
        print("Exporting group data from Keycloak...")
        data = await self.api_client.get("/admin/realms/{realm}/groups")
        result = [GroupSchema(**item).model_dump() for item in data]
        if not result:
            raise HTTPException(status_code=500, detail="Operation failed")
        return {"message": "Export groups completed successfully", "result": result}

    async def _export_roles(self) -> dict:
        print("Exporting role data from Keycloak...")
        data = await self.api_client.get("/admin/realms/{realm}/roles")
        result = [RoleSchema(**item).model_dump() for item in data]
        if not result:
            raise HTTPException(status_code=500, detail="Operation failed")
        return {"message": "Export roles completed successfully", "result": result}

    async def _export_identity_providers(self) -> dict:
        print("Exporting identity provider data from Keycloak...")
        data = await self.api_client.get(
            "/admin/realms/{realm}/identity-provider/instances"
        )
        result = [IdentityProviderSchema(**item).model_dump() for item in data]
        if not result:
            raise HTTPException(status_code=500, detail="Operation failed")
        return {
            "message": "Export identity providers completed successfully",
            "result": result,
        }


class KeycloakImport(Import):
    """
    Handles the import of data into Keycloak. Each method expects the relevant data to be passed as an argument.
    """

    def __init__(self, api_client: KeycloakAPIClient, state: KeycloakSkeleton):
        self.api_client = api_client
        self.state = state

    async def _import_clients(self, clients) -> dict:
        print("Importing client data into Keycloak...")

        clients_schema = [ClientSchema(**item) for item in json.loads(clients)]
        for client in clients_schema:
            await self.api_client.post(
                "/admin/realms/{realm}/clients", json=client.model_dump()
            )
        return {"message": "Import clients completed successfully"}

    async def _import_users(self, users) -> dict:
        print("Importing user data into Keycloak...")
        users_schema = [UserSchema(**item) for item in json.loads(users)]
        for user in users_schema:
            await self.api_client.post(
                "/admin/realms/{realm}/users", json=user.model_dump()
            )
        return {"message": "Import users completed successfully"}

    async def _import_groups(self, groups) -> dict:
        print("Importing group data into Keycloak...")
        groups_schema = [GroupSchema(**item) for item in json.loads(groups)]
        for group in groups_schema:
            await self.api_client.post(
                "/admin/realms/{realm}/groups", json=group.model_dump()
            )
        return {"message": "Import groups completed successfully"}

    async def _import_roles(self, roles) -> dict:
        print("Importing role data into Keycloak...")
        roles_schema = [RoleSchema(**item) for item in json.loads(roles)]
        for role in roles_schema:
            await self.api_client.post(
                "/admin/realms/{realm}/roles", json=role.model_dump()
            )
        return {"message": "Import roles completed successfully"}

    async def _import_identity_providers(self, identity_providers) -> dict:
        print("Importing identity provider data into Keycloak...")
        identity_providers_schema = [
            IdentityProviderSchema(**item) for item in json.loads(identity_providers)
        ]
        for idp in identity_providers_schema:
            await self.api_client.post(
                "/admin/realms/{realm}/identity-provider/instances",
                json=idp.model_dump(),
            )
        return {"message": "Import identity providers completed successfully"}


class KeycloakService(Service):
    """
    Main service class for interacting with Keycloak's API, managing data export and import.
    """

    name = "keycloak"
    priority = 10
    type = "Serial"

    state = KeycloakSkeleton()

    def __init__(self, config: Dict[str, str] = {}):
        self.auth = self.validate_config(config)
        self.api_client = KeycloakAPIClient(auth=self.auth)

        self.exporter = KeycloakExport(self.api_client, self.state)
        self.importer = KeycloakImport(self.api_client, self.state)

    def dump_to_file(self, path: str, data: dict) -> None:
        with open(path, "w") as f:
            f.write(json.dumps(data, indent=2))

    def validate_config(self, config: Dict[str, Any]) -> None:
        if not config:
            raise ValueError("Keycloak configuration is missing.")

        try:
            if "auth" in config:
                return KeycloakAuth(**config["auth"]).model_dump()
        except ValidationError as e:
            raise ValueError(f"Invalid Keycloak configuration: {e}")

    # TODO: this needs refactoring
    def backup(self, storage_client, tar=False) -> None:
        with TemporaryDirectory(prefix="keycloak_backup_") as temp_dir:
            try:
                for method_name in self._build_reconciliation_sequence("export"):
                    object_name = method_name.split("_")[-1]
                    data = getattr(self.exporter, method_name)()
                    dump_path = os.path.join(temp_dir, f"{object_name}.json")
                    self.dump_to_file(dump_path, data)
            except Exception as e:
                raise RuntimeError(f"Failed to export data: {e}")

            if tar:
                try:
                    shutil.make_archive(temp_dir, "gztar", temp_dir)
                except Exception as e:
                    raise RuntimeError(f"Failed to create tar archive: {e}")

            storage_client.upload(bucket_name=self.name, dir=temp_dir, tar=tar)

    def restore(self, storage_client) -> None: ...

    # TODO: this needs refactoring
    def _build_reconciliation_sequence(self, prefix: str) -> List[str]:
        """
        Build the execution sequence based on dependencies using topological sort.

        Topological sorting is a linear ordering of nodes in a directed graph where
        for each directed edge uv from node u to node v, u comes before v in the ordering.
        In this context, each node represents an import or export operation, and a directed
        edge from node u to node v indicates that operation u must be completed before operation v.

        The algorithm works as follows:
        1. Create a dependency graph where each operation is a node, and edges represent dependencies.
        2. Calculate the in-degree (number of incoming edges) for each node.
        3. Start with nodes that have an in-degree of 0 (no dependencies) and process them.
        4. Remove processed nodes and update the in-degree of their dependent nodes.
        5. Continue until all nodes are processed, resulting in a sorted sequence.
        6. If a cycle is detected (i.e., if nodes remain unprocessed), raise an error.

        Args:
            prefix (str): The prefix for the methods (e.g., 'import', 'export').

        Returns:
            List[str]: The sorted execution sequence of method names.
        """
        # Step 1: Create a dependency graph
        dependency_graph = defaultdict(list)
        for obj_name, depends_on in self.state.dependencies.items():
            for dependency in depends_on:
                dependency_graph[dependency].append(obj_name)

        # Step 2: Perform topological sorting
        in_degree = {key: 0 for key in self.state.schemas.keys()}
        for key in dependency_graph:
            for dep in dependency_graph[key]:
                in_degree[dep] += 1

        queue = deque([k for k in in_degree if in_degree[k] == 0])
        sorted_sequence = []

        while queue:
            current = queue.popleft()
            sorted_sequence.append(current)
            for dep in dependency_graph[current]:
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)

        if len(sorted_sequence) != len(self.state.schemas):
            raise RuntimeError(
                "A cyclic dependency was detected in the import/export configuration."
            )

        return sorted_sequence

    def _print_execution_sequence(
        self, execution_sequence: List[str], prefix: str
    ) -> None:
        """
        Print the execution sequence for user preview.
        """
        print(f"Execution sequence for {prefix} operation:")
        for step, method_name in enumerate(execution_sequence, start=1):
            print(f"Step {step}: {prefix}_{method_name}")


# maybe some concurrency based on the dependency graph of the services?

if __name__ == "__main__":
    # Example of how to use the service
    auth = {
        "url": "http://keycloak.example.com",
        "realm": "myrealm",
        "client_id": "myclient",
        "client_secret": "mysecret",
    }
    service = KeycloakService(auth=auth)
    print(service.state.schemas)
    # plan = service._build_reconciliation_sequence("import")
    # print(plan)
    # service._print_execution_sequence(plan, "import")
    service.importer()
