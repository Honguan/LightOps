from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def record_snapshot(data_dir: Path, snapshot: dict[str, Any]) -> None:
    date = datetime.now(timezone.utc).date().isoformat()
    history_dir = data_dir / "metrics"
    history_dir.mkdir(parents=True, exist_ok=True)
    path = history_dir / f"{date}.jsonl"
    compact = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu_percent": snapshot.get("cpu_percent", 0),
        "memory": snapshot.get("memory", {}),
        "network": snapshot.get("network", {}),
    }
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o640)
    with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(compact) + "\n")


def load_today(data_dir: Path) -> list[dict[str, Any]]:
    date = datetime.now(timezone.utc).date().isoformat()
    path = data_dir / "metrics" / f"{date}.jsonl"
    if not path.is_file():
        return []
    samples = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            samples.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return samples
