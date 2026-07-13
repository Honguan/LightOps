from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


FAILED_SSH = re.compile(r"Failed password for (?:invalid user )?(?P<user>\S+) from (?P<ip>[0-9a-fA-F:.]+)")


def process_rankings(limit: int = 10) -> dict[str, list[dict[str, Any]]]:
    processes: list[dict[str, Any]] = []
    for process in psutil.process_iter(["pid", "username", "name", "cmdline", "cpu_percent", "memory_percent", "create_time"]):
        try:
            info = process.info
            processes.append(
                {
                    "pid": info["pid"],
                    "user": info.get("username") or "",
                    "name": info.get("name") or "",
                    "command": " ".join(info.get("cmdline") or []),
                    "cpu_percent": round(info.get("cpu_percent") or 0.0, 2),
                    "memory_percent": round(info.get("memory_percent") or 0.0, 2),
                    "runtime_seconds": max(0, int(datetime.now(timezone.utc).timestamp() - (info.get("create_time") or 0))),
                }
            )
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return {
        "by_cpu": sorted(processes, key=lambda item: item["cpu_percent"], reverse=True)[:limit],
        "by_memory": sorted(processes, key=lambda item: item["memory_percent"], reverse=True)[:limit],
    }


def ssh_failures(log_paths: tuple[Path, ...] = (Path("/var/log/auth.log"), Path("/var/log/secure")), limit: int = 100) -> list[dict[str, str]]:
    path = next((candidate for candidate in log_paths if candidate.is_file()), None)
    if path is None:
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-5000:]
    failures = []
    for line in reversed(lines):
        match = FAILED_SSH.search(line)
        if match:
            failures.append({"user": match.group("user"), "ip": match.group("ip"), "message": line[:500]})
            if len(failures) >= limit:
                break
    return failures


def disk_alerts(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = []
    for disk in snapshot.get("disks", []):
        percent = float(disk.get("percent", 0))
        if percent >= 95:
            severity = "critical"
        elif percent >= 90:
            severity = "severe"
        elif percent >= 80:
            severity = "warning"
        else:
            severity = None
        if severity is not None:
            alerts.append(
                {
                    "type": "disk_usage",
                    "severity": severity,
                    "resource": disk.get("path", ""),
                    "value": percent,
                    "message": f"Disk {disk.get('path', '')} is {percent:.1f}% full",
                }
            )
        inode_percent = float(disk.get("inode_percent", 0))
        if inode_percent >= 90:
            alerts.append(
                {
                    "type": "inode_usage",
                    "severity": "severe",
                    "resource": disk.get("path", ""),
                    "value": inode_percent,
                    "message": f"Inodes on {disk.get('path', '')} are {inode_percent:.1f}% full",
                }
            )
    return alerts


def daily_report(
    snapshot: dict[str, Any],
    alerts: list[dict[str, Any]],
    failures: list[dict[str, str]],
    samples: list[dict[str, Any]] | None = None,
    *,
    abnormal_processes: list[dict[str, Any]] | None = None,
    service_stops: list[dict[str, Any]] | None = None,
    docker_anomalies: list[dict[str, Any]] | None = None,
    backup_results: list[dict[str, Any]] | None = None,
    deployment_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    samples = samples or [snapshot]
    cpu_values = [float(sample.get("cpu_percent", 0)) for sample in samples]
    memory_values = [float(sample.get("memory", {}).get("percent", 0)) for sample in samples]
    score = 100
    severity_penalty = {"warning": 10, "severe": 25, "critical": 40}
    score -= sum(severity_penalty.get(alert["severity"], 0) for alert in alerts)
    if float(snapshot.get("cpu_percent", 0)) >= 90:
        score -= 15
    if float(snapshot.get("memory", {}).get("percent", 0)) >= 90:
        score -= 15
    score -= min(20, len(failures) // 5)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "health_score": max(0, min(100, score)),
        "cpu": {
            "current_percent": snapshot.get("cpu_percent", 0),
            "average_percent": round(sum(cpu_values) / len(cpu_values), 2),
            "peak_percent": max(cpu_values),
        },
        "memory": {
            **snapshot.get("memory", {}),
            "average_percent": round(sum(memory_values) / len(memory_values), 2),
            "peak_percent": max(memory_values),
        },
        "disks": snapshot.get("disks", []),
        "network": snapshot.get("network", {}),
        "ssh_failed_logins": len(failures),
        "abnormal_processes": abnormal_processes or [],
        "service_stops": service_stops or [],
        "docker_anomalies": docker_anomalies or [],
        "backup_results": backup_results or [],
        "deployment_results": deployment_results or [],
        "alert_count": len(alerts),
        "alerts": alerts,
    }
