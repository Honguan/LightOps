from pathlib import Path

from fastapi.testclient import TestClient

from lightops.api import app, get_operations
from lightops.operations import Operations


class FakeOperations(Operations):
    def __init__(self) -> None:
        super().__init__(Path("manifests"), runner=lambda command: (0, "ok", ""))

    def service_statuses(self):
        return [{"name": "nginx", "active": True, "status": "active"}]

    def containers(self):
        return [{"id": "abc", "name": "web", "image": "nginx:latest", "status": "running"}]


client = TestClient(app)
app.dependency_overrides[get_operations] = FakeOperations


def test_services_endpoint_lists_watched_services() -> None:
    response = client.get("/api/services")

    assert response.status_code == 200
    assert response.json() == [{"name": "nginx", "active": True, "status": "active"}]


def test_software_center_lists_manifests() -> None:
    response = client.get("/api/apps")

    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert {"nginx", "apache", "docker"} <= names


def test_docker_endpoint_lists_containers() -> None:
    response = client.get("/api/docker/containers")

    assert response.status_code == 200
    assert response.json()[0]["name"] == "web"


def test_unknown_app_action_is_rejected() -> None:
    response = client.post("/api/apps/not-real/install")

    assert response.status_code == 404
