import json
import os
import time

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
    realm_name="master",
    verify=False,
)

# Wait for Keycloak server to be available
for _ in range(10):
    try:
        keycloak_admin.get_realms()
        break
    except:
        time.sleep(5)
else:
    raise Exception("Keycloak server is not responding.")

# Check if the realm already exists
realms = keycloak_admin.get_realms()
if KEYCLOAK_REALM not in [realm["realm"] for realm in realms]:
    # Create a new realm
    keycloak_admin.create_realm(payload={"realm": KEYCLOAK_REALM, "enabled": True})
    print(f"Realm '{KEYCLOAK_REALM}' created.")

# Switch to the new realm
keycloak_admin.connection.realm_name = KEYCLOAK_REALM

# Check if the client exists
clients = keycloak_admin.get_clients()
client = next((c for c in clients if c["clientId"] == KEYCLOAK_CLIENT_ID), None)

if not client:
    # Create the client
    client_id = keycloak_admin.create_client(
        payload={
            "clientId": KEYCLOAK_CLIENT_ID,
            "name": KEYCLOAK_CLIENT_ID,
            "enabled": True,
            "clientAuthenticatorType": "client-secret",
            "secret": KEYCLOAK_CLIENT_SECRET,
            "protocol": "openid-connect",
            "publicClient": False,
            "serviceAccountsEnabled": True,
            "standardFlowEnabled": False,
            "directAccessGrantsEnabled": False,
        }
    )
    print(f"Client '{KEYCLOAK_CLIENT_ID}' created.")
else:
    client_id = client["id"]
    print(f"Client '{KEYCLOAK_CLIENT_ID}' already exists.")

# Get the service account user ID
service_account_user = keycloak_admin.get_client_service_account_user(client_id)
service_account_user_id = service_account_user["id"]

# Get realm-management client ID
realm_management_client_id = keycloak_admin.get_client_id("realm-management")
realm_admin_role_id = keycloak_admin.get_client_role_id(
    client_id=realm_management_client_id, role_name="realm-admin"
)

realm_admin_role = keycloak_admin.get_role_by_id(role_id=realm_admin_role_id)

# Check if the role is already assigned to the service account user
assigned_roles = keycloak_admin.get_client_role_members(
    client_id=realm_management_client_id,
    role_name="realm-admin",
)
role_already_assigned = any(
    role["id"] == service_account_user_id for role in assigned_roles
)

if not role_already_assigned:
    # Assign the realm-admin role to the service account user
    keycloak_admin.assign_client_role(
        user_id=service_account_user_id,
        client_id=realm_management_client_id,
        roles=[realm_admin_role],
    )
    print("Assigned 'realm-admin' role to the service account user.")
else:
    print("'realm-admin' role is already assigned to the service account user.")

# Test client connection
try:
    keycloak_admin_test = KeycloakAdmin(
        server_url=KEYCLOAK_SERVER_URL,
        realm_name=KEYCLOAK_REALM,
        client_id=KEYCLOAK_CLIENT_ID,
        client_secret_key=KEYCLOAK_CLIENT_SECRET,
        verify=False,
    )
    print("Connected to the client using service account.")
except Exception as e:
    raise Exception("Could not connect to the client.") from e

# Get users info from the realm
users = keycloak_admin.get_users()
print(json.dumps(users, indent=2))
