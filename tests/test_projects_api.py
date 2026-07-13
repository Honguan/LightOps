from pathlib import Path

from fastapi.testclient import TestClient

from lightops.api import app, get_store
from lightops.store import Store


def test_project_can_be_created_and_listed(tmp_path: Path) -> None:
    store = Store(f"sqlite:///{tmp_path / 'lightops.db'}")
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)

    created = client.post(
        "/api/projects",
        json={
            "name": "My Website",
            "code": "my-website",
            "project_type": "static",
            "repository": "https://example.com/site.git",
            "branch": "main",
            "deploy_path": str(tmp_path / "site"),
        },
    )
    listed = client.get("/api/projects")

    assert created.status_code == 201
    assert created.json()["code"] == "my-website"
    assert listed.status_code == 200
    assert [item["name"] for item in listed.json()] == ["My Website"]
    app.dependency_overrides.pop(get_store, None)


def test_project_code_must_be_safe(tmp_path: Path) -> None:
    store = Store(f"sqlite:///{tmp_path / 'lightops.db'}")
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)

    response = client.post(
        "/api/projects",
        json={
            "name": "Unsafe",
            "code": "../unsafe",
            "project_type": "static",
            "repository": "https://example.com/site.git",
            "branch": "main",
            "deploy_path": str(tmp_path / "site"),
        },
    )

    assert response.status_code == 422
    app.dependency_overrides.pop(get_store, None)
