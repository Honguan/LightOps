from __future__ import annotations

import os
import platform
import time
from typing import Any

import psutil


def system_snapshot() -> dict[str, Any]:
    boot_time = psutil.boot_time()
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    network = psutil.net_io_counters()
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "cpu_per_core": psutil.cpu_percent(interval=None, percpu=True),
        "memory": _usage(memory.total, memory.used, memory.percent),
        "swap": _usage(swap.total, swap.used, swap.percent),
        "disks": [_disk_usage(partition.mountpoint) for partition in psutil.disk_partitions(all=False)],
        "network": {
            "bytes_sent": network.bytes_sent,
            "bytes_received": network.bytes_recv,
        },
        "load_average": list(os.getloadavg()) if hasattr(os, "getloadavg") else [0.0, 0.0, 0.0],
        "uptime_seconds": max(0, int(time.time() - boot_time)),
        "operating_system": platform.platform(),
        "kernel_version": platform.release(),
    }


def _usage(total: int, used: int, percent: float) -> dict[str, int | float]:
    return {"total": total, "used": used, "percent": percent}


def _disk_usage(path: str) -> dict[str, Any]:
    usage = psutil.disk_usage(path)
    result = {
        "path": path,
        "total": usage.total,
        "used": usage.used,
        "percent": usage.percent,
    }
    if hasattr(os, "statvfs"):
        stat = os.statvfs(path)
        inode_total = stat.f_files
        inode_used = inode_total - stat.f_ffree
        result["inode_total"] = inode_total
        result["inode_used"] = inode_used
        result["inode_percent"] = round(inode_used / inode_total * 100, 2) if inode_total else 0.0
    return result
