from __future__ import annotations

import json
import os
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any


Sender = Callable[[dict[str, Any]], None]


class NotificationService:
    def __init__(
        self,
        state_path: Path,
        senders: list[Sender],
        cooldown_seconds: int = 1800,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.state_path = state_path
        self.senders = senders
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock

    def process(self, alerts: list[dict[str, Any]]) -> None:
        state = self._load()
        active: dict[str, dict[str, Any]] = state.get("active", {})
        current: set[str] = set()
        now = self.clock()
        for alert in alerts:
            key = f"{alert['type']}:{alert['resource']}"
            current.add(key)
            previous = active.get(key)
            if previous is None or now - float(previous.get("last_sent", 0)) >= self.cooldown_seconds:
                self._send({"event": "alert", **alert})
                active[key] = {**alert, "last_sent": now}
        for key in set(active) - current:
            previous = active.pop(key)
            self._send(
                {
                    "event": "recovery",
                    "type": previous["type"],
                    "severity": "recovery",
                    "resource": previous["resource"],
                    "message": f"{previous['resource']} recovered",
                }
            )
        self._save({"active": active})

    def _send(self, message: dict[str, Any]) -> None:
        for sender in self.senders:
            sender(message)

    def _load(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {"active": {}}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"active": {}}

    def _save(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, self.state_path)


def webhook_sender(url: str) -> Sender:
    def send(message: dict[str, Any]) -> None:
        request = urllib.request.Request(
            url,
            data=json.dumps(message).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10):
            pass

    return send
