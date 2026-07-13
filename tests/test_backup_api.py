from pathlib import Path

from fastapi.testclient import TestClient

from lightops.api import app, get_backup_service
from lightops.backups import BackupService


def test_directory_backup_can_be_created_and_listed(tmp_path: Path) -> None:
    source = tmp_path / "website"
    source.mkdir()
    (source / "index.html").write_text("LightOps", encoding="utf-8")
    service = BackupService(tmp_path / "backups")
    app.dependency_overrides[get_backup_service] = lambda: service
    client = TestClient(app)

    created = client.post("/api/backups", json={"name": "website", "sources": [str(source)]})
    listed = client.get("/api/backups")

    assert created.status_code == 201
    assert created.json()["name"] == "website"
    assert Path(created.json()["path"]).is_file()
    assert len(listed.json()) == 1
    app.dependency_overrides.pop(get_backup_service, None)


def test_backup_rejects_missing_source(tmp_path: Path) -> None:
    service = BackupService(tmp_path / "backups")
    app.dependency_overrides[get_backup_service] = lambda: service
    client = TestClient(app)

    response = client.post("/api/backups", json={"name": "missing", "sources": [str(tmp_path / "none")]})

    assert response.status_code == 400
    app.dependency_overrides.pop(get_backup_service, None)
