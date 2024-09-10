import asyncio
import inspect
import json
import os
import shutil
from collections import defaultdict, deque
from http.client import HTTPException
from tempfile import TemporaryDirectory
from typing import Any, Dict, List

import httpx
from pydantic import BaseModel, ValidationError

from backup_restore.services.base import Export, Import, Service
from backup_restore.services.keycloak.schema import (
    EXCEPTIONS,
    ClientSchema,
    GroupSchema,
    IdentityProviderSchema,
    KeycloakAuth,
    KeycloakSkeleton,
    RoleSchema,
    UserSchema,
)


class KeycloakAPIClient:
    """
    Handles direct interactions with the Keycloak API, including GET and POST requests.
    This class is independent of the business logic for exporting and importing data.
    """

    def __init__(self, auth: Dict[str, str]):
        self.auth = auth
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


class ResponseModel(BaseModel):
    message: str = ""
    result: Any = None
    error: str = ""
    status: int = 200


class KeycloakExport(Export):
    """
    Handles the export of Keycloak data to predefined schemas.
    """

    def __init__(self, api_client: KeycloakAPIClient, state: KeycloakSkeleton):
        self.api_client = api_client
        self.state = state

    async def export_clients(self) -> dict:
        """
        Export client data from Keycloak.
        """
        return await self._export_data(
            endpoint="/admin/realms/{realm}/clients",
            schema=ClientSchema,
            success_message="Export clients completed successfully",
            error_message="Failed to export clients",
        )

    async def export_users(self) -> dict:
        """
        Export user data from Keycloak.
        """
        return await self._export_data(
            endpoint="/admin/realms/{realm}/users",
            schema=UserSchema,
            success_message="Export users completed successfully",
            error_message="Failed to export users",
        )

    async def export_groups(self) -> dict:
        """
        Export group data from Keycloak.
        """
        return await self._export_data(
            endpoint="/admin/realms/{realm}/groups",
            schema=GroupSchema,
            success_message="Export groups completed successfully",
            error_message="Failed to export groups",
        )

    async def export_roles(self) -> dict:
        """
        Export role data from Keycloak.
        """
        return await self._export_data(
            endpoint="/admin/realms/{realm}/roles",
            schema=RoleSchema,
            success_message="Export roles completed successfully",
            error_message="Failed to export roles",
        )

    async def export_identity_providers(self) -> dict:
        """
        Export identity provider data from Keycloak.
        """
        return await self._export_data(
            endpoint="/admin/realms/{realm}/identity-provider/instances",
            schema=IdentityProviderSchema,
            success_message="Export identity providers completed successfully",
            error_message="Failed to export identity providers",
        )

    async def _export_data(
        self, endpoint: str, schema, success_message: str, error_message: str
    ) -> dict:
        try:
            print(f"Exporting data from {endpoint}...")
            data = await self.api_client.get(endpoint)
            result = [schema(**item).model_dump() for item in data]
            if not result and result != []:
                raise HTTPException(status_code=500, detail="No data found")
            return ResponseModel(message=success_message, result=result).model_dump()

        except httpx.HTTPStatusError as e:
            return ResponseModel(
                error=f"{error_message}: HTTP Status Error - {str(e)}",
                status=e.response.status_code,
            ).model_dump()

        except Exception as e:
            return ResponseModel(
                error=f"{error_message}: {EXCEPTIONS.get(type(e), 'Unknown Error')}",
                status=500,
            ).model_dump()


class KeycloakImport(Import):
    """
    Handles the import of data into Keycloak. Each method expects the relevant data to be passed as an argument.
    """

    def __init__(self, api_client: KeycloakAPIClient, state: KeycloakSkeleton):
        self.api_client = api_client
        self.state = state

    async def import_clients(self, clients: List[ClientSchema]) -> dict:
        return await self._import_data(
            endpoint="/admin/realms/{realm}/clients",
            schema=ClientSchema,
            data=clients,
            success_message="Import clients completed successfully",
            error_message="Failed to import clients",
        )

    async def import_users(self, users: List[UserSchema]) -> dict:
        return await self._import_data(
            endpoint="/admin/realms/{realm}/users",
            schema=UserSchema,
            data=users,
            success_message="Import users completed successfully",
            error_message="Failed to import users",
        )

    async def import_groups(self, groups: List[GroupSchema]) -> dict:
        return await self._import_data(
            endpoint="/admin/realms/{realm}/groups",
            schema=GroupSchema,
            data=groups,
            success_message="Import groups completed successfully",
            error_message="Failed to import groups",
        )

    async def import_roles(self, roles: List[RoleSchema]) -> dict:
        return await self._import_data(
            endpoint="/admin/realms/{realm}/roles",
            schema=RoleSchema,
            data=roles,
            success_message="Import roles completed successfully",
            error_message="Failed to import roles",
        )

    async def import_identity_providers(
        self, identity_providers: List[IdentityProviderSchema]
    ) -> dict:
        return await self._import_data(
            endpoint="/admin/realms/{realm}/identity-provider/instances",
            schema=IdentityProviderSchema,
            data=identity_providers,
            success_message="Import identity providers completed successfully",
            error_message="Failed to import identity providers",
        )

    async def _import_data(
        self, endpoint: str, schema, data: str, success_message: str, error_message: str
    ) -> dict:
        try:
            print(f"Importing data to {endpoint}...")
            data_schema = [schema(**item) for item in json.loads(data)]
            for item in data_schema:
                await self.api_client.post(endpoint, json=item.model_dump())
            return ResponseModel(message=success_message).model_dump()
        except httpx.HTTPStatusError as e:
            return ResponseModel(
                error=f"{error_message}: HTTP Status Error - {str(e)}",
                status=e.response.status_code,
            ).model_dump()
        except Exception as e:
            return ResponseModel(
                error=f"{error_message}: {EXCEPTIONS.get(type(e), 'Unknown Error')}",
                status=500,
            ).model_dump()


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

    def validate_config(self, config: Dict[str, Any]) -> None:
        if not config:
            raise ValueError("Keycloak configuration is missing.")

        try:
            if "auth" in config:
                return KeycloakAuth(**config["auth"]).model_dump()
        except ValidationError as e:
            raise ValueError(f"Invalid Keycloak configuration: {e}")

    def restore(self, storage_client, **kwargs) -> None:
        return super().restore(storage_client, **kwargs)

    def backup(
        self, storage_client, bucket_name, tar=False, archive_only=True, raw=False
    ) -> None:
        try:
            with TemporaryDirectory(prefix="keycloak_backup_") as temp_dir:
                print(f"Exporting Keycloak data to {temp_dir}...")
                self._export_data(temp_dir=temp_dir, raw=raw)
                if tar:
                    self._create_tar_archive(temp_dir)
                # this needs refactor, as the storage_client should've already been
                # initialized with the bucket naming, and we should be able to pass a
                # locator (service_name) that in theory would correlate to the current
                # snapshot
                if archive_only:
                    storage_client.upload(
                        bucket_name=bucket_name, dir=temp_dir, tar=tar
                    )
                else:
                    # load stored data as single json and returns
                    return self._load_exported_data(temp_dir)

        except Exception as e:
            raise RuntimeError(f"Backup failed: {e}")

    def _dump_to_file(self, path: str, data: dict) -> None:
        with open(path, "w") as f:
            f.write(json.dumps(data, indent=2))

    def _load_exported_data(self, temp_dir: str):
        __files__ = os.listdir(temp_dir)
        data = {}
        for file in __files__:
            with open(os.path.join(temp_dir, file), "r") as f:
                data[file.split(".")[0]] = json.load(f)
        return data

    def _export_data(self, temp_dir: str, raw: bool = False) -> None:
        for object_name, data in self._generate_export_data(raw=raw):
            dump_path = os.path.join(temp_dir, f"{object_name}.json")
            self._dump_to_file(dump_path, data)

    def _to_sync(self, coroutine_function, debug=True):
        try:
            loop = asyncio.get_running_loop()

        except RuntimeError:
            # There is no existing event loop, so we can start our own.
            return asyncio.run(coroutine_function, debug=debug)

        else:
            # Enable debug mode
            loop.set_debug(debug)

            # Run the coroutine and wait for the result.
            task = loop.create_task(coroutine_function)
            return asyncio.ensure_future(task, loop=loop)

    def _generate_export_data(self, raw: bool = False):
        _export_sequence = self._build_reconciliation_sequence("export")
        print(f"Export sequence: {_export_sequence}")
        for method_name in _export_sequence:
            object_name = method_name.split("_")[-1]
            # handles async method execution
            if inspect.iscoroutinefunction(getattr(self.exporter, method_name)):
                # run async method in sync context
                data = self._to_sync(getattr(self.exporter, method_name)())
            else:
                data = getattr(self.exporter, method_name)()
            if raw:
                data = data.get("result", [])
            yield object_name, data

    def _create_tar_archive(self, temp_dir: str) -> None:
        try:
            shutil.make_archive(temp_dir, "gztar", temp_dir)
        except Exception as e:
            raise RuntimeError(f"Failed to create tar archive: {e}")

    def _build_reconciliation_sequence(self, prefix: str) -> List[str]:
        dependency_graph = self._build_dependency_graph()
        sorted_sequence = self._topological_sort(dependency_graph)

        if len(sorted_sequence) != len(self.state.schemas):
            raise RuntimeError(
                "A cyclic dependency was detected in the import/export configuration."
            )

        return [f"{prefix}_{name}" for name in sorted_sequence]

    def _build_dependency_graph(self):
        dependency_graph = defaultdict(list)
        for obj_name, depends_on in self.state.dependencies.items():
            for dependency in depends_on:
                dependency_graph[dependency].append(obj_name)
        return dependency_graph

    def _topological_sort(self, dependency_graph):
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

        return sorted_sequence
