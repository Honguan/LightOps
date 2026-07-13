from __future__ import annotations

import json
import logging
import platform
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from .backups import BackupService
from .config import Settings
from .insights import daily_report, disk_alerts, process_rankings, ssh_failures
from .history import load_today, record_snapshot
from .monitoring import system_snapshot
from .notifications import NotificationService, webhook_sender
from .operations import Operations
from .store import Store


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
    operations = Operations(
        settings.manifests_dir,
        privileged=platform.system() == "Linux",
        additional_services=settings.custom_services,
    )
    rankings = process_rankings()
    abnormal = [item for item in rankings["by_cpu"] if item["cpu_percent"] >= 80]
    abnormal.extend(item for item in rankings["by_memory"] if item["memory_percent"] >= 50 and item not in abnormal)
    services = operations.service_statuses()
    containers = operations.containers()
    key = settings.secret_key_file.read_bytes().strip() if settings.secret_key_file.is_file() else None
    deployments = Store(settings.database_url, key).recent_deployments()
    report = daily_report(
        snapshot,
        disk_alerts(snapshot),
        ssh_failures(),
        load_today(settings.data_dir),
        abnormal_processes=abnormal,
        service_stops=[item for item in services if not item["active"]],
        docker_anomalies=[item for item in containers if not str(item["status"]).lower().startswith("up")],
        backup_results=BackupService(settings.backup_dir, settings.backup_retention).list()[:20],
        deployment_results=[
            {"project_id": item.project_id, "result": item.result, "finished_at": item.finished_at.isoformat()}
            for item in deployments
        ],
    )
    reports_dir = settings.data_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).date().isoformat()
    temporary = reports_dir / f".{date}.tmp"
    target = reports_dir / f"{date}.json"
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
