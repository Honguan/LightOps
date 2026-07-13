from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lightops.api import app, get_store
from lightops.store import Store


def test_password_requires_at_least_six_characters(tmp_path: Path) -> None:
    store = Store(f"sqlite:///{tmp_path / 'lightops.db'}")

    store.set_password("admin", "123456")
    with pytest.raises(ValueError, match="at least 6 characters"):
        store.set_password("admin", "12345")


def test_login_protects_api_and_issues_expiring_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LIGHTOPS_AUTH_DISABLED", "false")
    store = Store(f"sqlite:///{tmp_path / 'lightops.db'}")
    store.set_password("admin", "correct horse battery staple")
    app.state.auth_store = store
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)

    unauthenticated = client.get("/api/system")
    login = client.post("/api/auth/login", json={"username": "admin", "password": "correct horse battery staple"})
    authenticated = client.get("/api/system", headers={"Authorization": f"Bearer {login.json()['token']}"})

    assert unauthenticated.status_code == 401
    assert login.status_code == 200
    assert login.json()["expires_at"]
    assert authenticated.status_code == 200
    del app.state.auth_store
    app.dependency_overrides.pop(get_store, None)


def test_invalid_password_is_rejected(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LIGHTOPS_AUTH_DISABLED", "false")
    store = Store(f"sqlite:///{tmp_path / 'lightops.db'}")
    store.set_password("admin", "correct horse battery staple")
    app.state.auth_store = store
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)

    response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})

    assert response.status_code == 401
    del app.state.auth_store
    app.dependency_overrides.pop(get_store, None)
