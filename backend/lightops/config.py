from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    log_dir: Path
    backup_dir: Path
    manifests_dir: Path
    auth_disabled: bool
    scheduler_disabled: bool
    webhook_url: str | None
    report_hour: int
    backup_sources: tuple[str, ...]
    backup_retention: int
    secret_key_file: Path
    ip_allowlist: tuple[str, ...]
    custom_services: tuple[str, ...]
    database_url_override: str | None

    @property
    def database_url(self) -> str:
        return self.database_url_override or f"sqlite:///{self.data_dir / 'lightops.db'}"


def load_settings() -> Settings:
    source_root = Path(__file__).resolve().parents[2]
    return Settings(
        data_dir=Path(os.getenv("LIGHTOPS_DATA_DIR", "/var/lib/lightops")),
        log_dir=Path(os.getenv("LIGHTOPS_LOG_DIR", "/var/log/lightops")),
        backup_dir=Path(os.getenv("LIGHTOPS_BACKUP_DIR", "/var/backups/lightops")),
        manifests_dir=Path(os.getenv("LIGHTOPS_MANIFESTS_DIR", str(source_root / "manifests"))),
        auth_disabled=os.getenv("LIGHTOPS_AUTH_DISABLED", "false").lower() == "true",
        scheduler_disabled=os.getenv("LIGHTOPS_SCHEDULER_DISABLED", "false").lower() == "true",
        webhook_url=os.getenv("LIGHTOPS_WEBHOOK_URL") or None,
        report_hour=int(os.getenv("LIGHTOPS_REPORT_HOUR", "1")),
        backup_sources=tuple(item for item in os.getenv("LIGHTOPS_BACKUP_SOURCES", "").split(",") if item),
        backup_retention=int(os.getenv("LIGHTOPS_BACKUP_RETENTION", "7")),
        secret_key_file=Path(os.getenv("LIGHTOPS_SECRET_KEY_FILE", "/etc/lightops/secret.key")),
        ip_allowlist=tuple(item.strip() for item in os.getenv("LIGHTOPS_IP_ALLOWLIST", "").split(",") if item.strip()),
        custom_services=tuple(item.strip() for item in os.getenv("LIGHTOPS_CUSTOM_SERVICES", "").split(",") if item.strip()),
        database_url_override=os.getenv("LIGHTOPS_DATABASE_URL") or None,
    )
