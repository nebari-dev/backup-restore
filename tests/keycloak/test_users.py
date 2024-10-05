import requests


def test_keycloak_users():
    # Replace with the actual endpoint and logic
    response = requests.get("http://localhost:8000/backup/keycloak/users")
    print(response.json())
    assert response.status_code == 200
