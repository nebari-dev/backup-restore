#  services/keycloak.py
import json
import uuid
from http.client import HTTPException
from typing import Any, Dict, List, Optional

import httpx
from pydantic import AnyHttpUrl, BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from backup_restore.services.base import Export, Import, Service, State


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


EXCEPTIONS = {
    httpx.HTTPStatusError: "HTTP Status Error",
    httpx.RequestError: "Request Error",
    ValidationError: "Validation Error",
}


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

    async def _export_clients(self) -> dict:
        """
        Export client data from Keycloak.
        """
        return await self._export_data(
            endpoint="/admin/realms/{realm}/clients",
            schema=ClientSchema,
            success_message="Export clients completed successfully",
            error_message="Failed to export clients",
        )

    async def _export_users(self) -> dict:
        """
        Export user data from Keycloak.
        """
        return await self._export_data(
            endpoint="/admin/realms/{realm}/users",
            schema=UserSchema,
            success_message="Export users completed successfully",
            error_message="Failed to export users",
        )

    async def _export_groups(self) -> dict:
        """
        Export group data from Keycloak.
        """
        return await self._export_data(
            endpoint="/admin/realms/{realm}/groups",
            schema=GroupSchema,
            success_message="Export groups completed successfully",
            error_message="Failed to export groups",
        )

    async def _export_roles(self) -> dict:
        """
        Export role data from Keycloak.
        """
        return await self._export_data(
            endpoint="/admin/realms/{realm}/roles",
            schema=RoleSchema,
            success_message="Export roles completed successfully",
            error_message="Failed to export roles",
        )

    async def _export_identity_providers(self) -> dict:
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
            if not result:
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

    async def _import_clients(self, clients) -> dict:
        return await self._import_data(
            endpoint="/admin/realms/{realm}/clients",
            schema=ClientSchema,
            data=clients,
            success_message="Import clients completed successfully",
            error_message="Failed to import clients",
        )

    async def _import_users(self, users) -> dict:
        return await self._import_data(
            endpoint="/admin/realms/{realm}/users",
            schema=UserSchema,
            data=users,
            success_message="Import users completed successfully",
            error_message="Failed to import users",
        )

    async def _import_groups(self, groups) -> dict:
        return await self._import_data(
            endpoint="/admin/realms/{realm}/groups",
            schema=GroupSchema,
            data=groups,
            success_message="Import groups completed successfully",
            error_message="Failed to import groups",
        )

    async def _import_roles(self, roles) -> dict:
        return await self._import_data(
            endpoint="/admin/realms/{realm}/roles",
            schema=RoleSchema,
            data=roles,
            success_message="Import roles completed successfully",
            error_message="Failed to import roles",
        )

    async def _import_identity_providers(self, identity_providers) -> dict:
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

    def backup(self, storage_client, tar=False) -> None:
        return super().backup(storage_client, tar)
