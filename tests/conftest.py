import pytest


@pytest.fixture(autouse=True)
def disable_authentication_for_non_auth_tests(monkeypatch, tmp_path):
    monkeypatch.setenv("LIGHTOPS_AUTH_DISABLED", "true")
    monkeypatch.setenv("LIGHTOPS_SCHEDULER_DISABLED", "true")
    monkeypatch.setenv("LIGHTOPS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LIGHTOPS_BACKUP_DIR", str(tmp_path / "backups"))
