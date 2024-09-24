# services/keycloak/schema.py

import uuid
from typing import Dict, List, Optional

import httpx
from pydantic import AnyHttpUrl, BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from backup_restore.services.base import State


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
