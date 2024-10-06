import requests


def test_keycloak_users():
    # Replace with the actual endpoint and logic
    response = requests.get("http://localhost:8020/backup/keycloak/users")
    print(response.json())
    assert response.status_code == 200


def create_user():
    # Replace with the actual endpoint and logic
    response = requests.post(
        "http://localhost:8020/backup/keycloak/users", json={"username": "testuser"}
    )
    print(response.json())
    assert response.status_code == 201


def remove_user():
    # Replace with the actual endpoint and logic
    response = requests.delete("http://localhost:8020/backup/keycloak/users/1")
    print(response.json())
    assert response.status_code == 204


def create_group():
    # Replace with the actual endpoint and logic
    response = requests.post(
        "http://localhost:8020/backup/keycloak/groups", json={"name": "testgroup"}
    )
    print(response.json())
    assert response.status_code == 201


def remove_group():
    # Replace with the actual endpoint and logic
    response = requests.delete("http://localhost:8020/backup/keycloak/groups/1")
    print(response.json())
    assert response.status_code == 204
