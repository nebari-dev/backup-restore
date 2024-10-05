import os
import time

from keycloak import KeycloakAdmin

# Environment variables
KEYCLOAK_SERVER_URL = os.environ.get(
    "KEYCLOAK_SERVER_URL", "http://localhost:8080/auth/"
)
KEYCLOAK_ADMIN_USERNAME = os.environ.get("KEYCLOAK_ADMIN_USERNAME", "admin")
KEYCLOAK_ADMIN_PASSWORD = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "test")
KEYCLOAK_CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID", "my-client")
KEYCLOAK_CLIENT_SECRET = os.environ.get("KEYCLOAK_CLIENT_SECRET", "my-client-secret")

# Initialize Keycloak Admin client
keycloak_admin = KeycloakAdmin(
    server_url=KEYCLOAK_SERVER_URL,
    username=KEYCLOAK_ADMIN_USERNAME,
    password=KEYCLOAK_ADMIN_PASSWORD,
    realm_name="master",
    verify=True,
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
keycloak_admin.realm_name = KEYCLOAK_REALM

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

# Get realm-admin role
roles = keycloak_admin.get_realm_roles()
realm_admin_role = next((role for role in roles if role["name"] == "realm-admin"), None)

if realm_admin_role:
    # Assign realm-admin role to the service account
    keycloak_admin.assign_realm_roles(
        user_id=service_account_user_id, roles=[realm_admin_role]
    )
    print("Assigned 'realm-admin' role to the service account.")
else:
    print("realm-admin role not found.")
