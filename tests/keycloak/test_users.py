import requests


def test_server_response():
    response = requests.get("http://localhost:8080/")
    assert response.status_code == 200
