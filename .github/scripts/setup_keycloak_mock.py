import os
from keycloak import KeycloakAdmin

# Environment variables
KEYCLOAK_SERVER_URL = os.environ.get("KEYCLOAK_SERVER_URL", "http://localhost:8080/")
KEYCLOAK_ADMIN_USERNAME = os.environ.get("KEYCLOAK_ADMIN_USERNAME", "admin")
KEYCLOAK_ADMIN_PASSWORD = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")

KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "test")
KEYCLOAK_CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID", "test-client")
KEYCLOAK_CLIENT_SECRET = os.environ.get("KEYCLOAK_CLIENT_SECRET", "test-client-secret")

# Initialize Keycloak Admin client
keycloak_admin = KeycloakAdmin(
    server_url=KEYCLOAK_SERVER_URL,
    username=KEYCLOAK_ADMIN_USERNAME,
    password=KEYCLOAK_ADMIN_PASSWORD,
    realm_name=KEYCLOAK_REALM,
    verify=False,
)


# Create users with additional attributes
def create_user(username: str, first_name: str, last_name: str, email: str):
    keycloak_admin.create_user(
        {
            "username": username,
            "firstName": first_name,
            "lastName": last_name,
            "email": email,
            "enabled": True,
            "credentials": [
                {"type": "password", "value": "password", "temporary": False}
            ],
        }
    )


USERS = [
    {
        "username": "user1",
        "first_name": "Alice",
        "last_name": "Smith",
        "email": "alice@example.com",
    },
    {
        "username": "user2",
        "first_name": "Bob",
        "last_name": "Brown",
        "email": "bob@example.com",
    },
    {
        "username": "user3",
        "first_name": "Carol",
        "last_name": "Jones",
        "email": "carol@example.com",
    },
]

for user in USERS:
    create_user(**user)


# Create groups
def create_group(name: str):
    keycloak_admin.create_group({"name": name})


GROUPS = ["developers", "testers", "admins"]
for group in GROUPS:
    create_group(group)


# Add users to groups
def add_users_to_group(group_name: str, usernames: list):
    group_id = keycloak_admin.get_group_by_path(f"/{group_name}")["id"]
    for username in usernames:
        user_id = keycloak_admin.get_user_id(username)
        keycloak_admin.group_user_add(user_id=user_id, group_id=group_id)


add_users_to_group("developers", ["user1", "user2"])
add_users_to_group("testers", ["user2", "user3"])
add_users_to_group("admins", ["user3", "user1"])


# Create realm roles
def create_realm_role(role_name: str):
    keycloak_admin.create_realm_role({"name": role_name})


REALM_ROLES = ["manage-users", "view-realm", "manage-clients"]
for role in REALM_ROLES:
    create_realm_role(role)


# Assign realm roles to groups
def assign_realm_roles_to_group(group_name: str, role_names: list):
    group_id = keycloak_admin.get_group_by_path(f"/{group_name}")["id"]
    roles = [keycloak_admin.get_realm_role(role_name) for role_name in role_names]
    keycloak_admin.assign_group_realm_roles(group_id=group_id, roles=roles)


assign_realm_roles_to_group("developers", ["view-realm"])
assign_realm_roles_to_group("admins", ["manage-users", "manage-clients"])


# Create client roles
def create_client_role(client_id: str, role_name: str):
    client_uuid = keycloak_admin.get_client_id(client_id)
    keycloak_admin.create_client_role(client_uuid, {"name": role_name})


CLIENT_ROLES = {
    "read-data": ["scope:read"],
    "write-data": ["scope:write"],
    "delete-data": ["scope:delete"],
}

for role_name, scopes in CLIENT_ROLES.items():
    create_client_role(KEYCLOAK_CLIENT_ID, role_name)


# Assign client roles to groups
def assign_client_roles_to_group(group_name: str, client_id: str, role_names: list):
    group_id = keycloak_admin.get_group_by_path(f"/{group_name}")["id"]
    client_uuid = keycloak_admin.get_client_id(client_id)
    roles = [
        keycloak_admin.get_client_role(client_uuid, role_name)
        for role_name in role_names
    ]
    keycloak_admin.assign_group_client_roles(
        group_id=group_id, client_id=client_uuid, roles=roles
    )


assign_client_roles_to_group(
    "developers", KEYCLOAK_CLIENT_ID, ["read-data", "write-data"]
)
assign_client_roles_to_group("testers", KEYCLOAK_CLIENT_ID, ["read-data"])
assign_client_roles_to_group(
    "admins", KEYCLOAK_CLIENT_ID, ["read-data", "write-data", "delete-data"]
)


# Configure authentication flows
def create_auth_flow(flow_alias: str):
    keycloak_admin.create_authentication_flow(
        {
            "alias": flow_alias,
            "description": "Custom authentication flow for development",
            "providerId": "basic-flow",
            "topLevel": True,
            "builtIn": False,
        }
    )


create_auth_flow("dev-auth-flow")

# Set the custom flow as the realm's browser flow
keycloak_admin.update_realm(KEYCLOAK_REALM, {"browserFlow": "dev-auth-flow"})


# Add identity provider (e.g., GitHub)
def create_identity_provider(alias: str, provider_id: str, config: dict):
    payload = {
        "alias": alias,
        "displayName": alias.capitalize(),
        "providerId": provider_id,
        "enabled": True,
        "config": config,
    }
    keycloak_admin.create_identity_provider(payload)


create_identity_provider(
    alias="github",
    provider_id="github",
    config={
        "clientId": "your-github-client-id",
        "clientSecret": "your-github-client-secret",
        "useJwksUrl": "true",
        "jwksUrl": "https://github.com/login/oauth/access_token",
        "authorizationUrl": "https://github.com/login/oauth/authorize",
        "tokenUrl": "https://github.com/login/oauth/access_token",
        "defaultScope": "user:email",
    },
)

# Update realm-level settings (e.g., password policy)
keycloak_admin.update_realm(
    KEYCLOAK_REALM,
    {
        "passwordPolicy": "length(8) and notUsername(#2) and regexPattern('^[a-zA-Z0-9]+$')",
        "smtpServer": {
            "host": "smtp.example.com",
            "port": "587",
            "from": "noreply@example.com",
            "auth": "true",
            "user": "smtp-user",
            "password": "smtp-password",
        },
    },
)

print("Development realm setup is complete.")
