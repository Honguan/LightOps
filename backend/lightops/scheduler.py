from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from .backups import BackupService
from .config import Settings
from .insights import daily_report, disk_alerts, ssh_failures
from .history import load_today, record_snapshot
from .monitoring import system_snapshot
from .notifications import NotificationService, webhook_sender


logger = logging.getLogger(__name__)


def build_scheduler(settings: Settings) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    senders = [webhook_sender(settings.webhook_url)] if settings.webhook_url else []
    notifications = NotificationService(settings.data_dir / "notification-state.json", senders)
    scheduler.add_job(
        lambda: monitor_once(notifications, settings),
        "interval",
        minutes=5,
        id="monitor-alerts",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        lambda: write_daily_report(settings),
        "cron",
        hour=settings.report_hour,
        minute=0,
        id="daily-report",
        max_instances=1,
    )
    if settings.backup_sources:
        scheduler.add_job(
            lambda: BackupService(settings.backup_dir, settings.backup_retention).create(
                "automatic", list(settings.backup_sources)
            ),
            "cron",
            hour=(settings.report_hour + 1) % 24,
            minute=0,
            id="automatic-backup",
            max_instances=1,
        )
    return scheduler


def monitor_once(notifications: NotificationService, settings: Settings) -> None:
    try:
        snapshot = system_snapshot()
        record_snapshot(settings.data_dir, snapshot)
        notifications.process(disk_alerts(snapshot))
    except Exception:
        logger.exception("LightOps monitoring cycle failed")


def write_daily_report(settings: Settings) -> None:
    snapshot = system_snapshot()
    report = daily_report(snapshot, disk_alerts(snapshot), ssh_failures(), load_today(settings.data_dir))
    reports_dir = settings.data_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).date().isoformat()
    temporary = reports_dir / f".{date}.tmp"
    target = reports_dir / f"{date}.json"
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
