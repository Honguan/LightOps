from pathlib import Path

from lightops.notifications import NotificationService


def test_alerts_are_deduplicated_and_recovery_is_sent(tmp_path: Path) -> None:
    sent = []
    service = NotificationService(tmp_path / "notification-state.json", [sent.append], cooldown_seconds=300, clock=lambda: 1000)
    alert = {"type": "disk_usage", "severity": "critical", "resource": "/", "value": 96, "message": "Disk / is 96% full"}

    service.process([alert])
    service.process([alert])
    service.process([])

    assert [message["event"] for message in sent] == ["alert", "recovery"]
    assert sent[0]["severity"] == "critical"
