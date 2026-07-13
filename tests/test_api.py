from fastapi.testclient import TestClient

from lightops.api import app


client = TestClient(app)


def test_health_endpoint_reports_version() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_system_endpoint_exposes_required_metrics() -> None:
    response = client.get("/api/system")

    assert response.status_code == 200
    assert {
        "cpu_percent",
        "cpu_per_core",
        "memory",
        "swap",
        "disks",
        "network",
        "load_average",
        "uptime_seconds",
        "operating_system",
        "kernel_version",
    } <= response.json().keys()


def test_process_endpoint_returns_cpu_and_memory_rankings() -> None:
    response = client.get("/api/processes")

    assert response.status_code == 200
    assert {"by_cpu", "by_memory"} == response.json().keys()


def test_alert_endpoint_applies_disk_thresholds(monkeypatch) -> None:
    monkeypatch.setattr(
        "lightops.api.system_snapshot",
        lambda: {"disks": [{"path": "/", "percent": 96}], "cpu_percent": 10, "memory": {"percent": 20}},
    )

    response = client.get("/api/alerts")

    assert response.status_code == 200
    assert response.json()[0]["severity"] == "critical"


def test_daily_report_has_health_score() -> None:
    response = client.get("/api/reports/daily")

    assert response.status_code == 200
    assert 0 <= response.json()["health_score"] <= 100
    assert "generated_at" in response.json()
