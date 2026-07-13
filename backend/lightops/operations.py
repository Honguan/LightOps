from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import yaml

from .packages import PackageManager, detect_package_manager


Runner = Callable[[Sequence[str]], tuple[int, str, str]]


def run_command(command: Sequence[str]) -> tuple[int, str, str]:
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, check=False)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


class Operations:
    watched_services = (
        "nginx", "apache2", "httpd", "docker", "mariadb", "mysql", "postgresql", "redis", "redis-server", "sshd", "ssh",
        "fail2ban", "ufw", "firewalld",
    )
    stacks = {
        "lamp": ("apache", "mariadb", "php", "composer"),
        "lemp": ("nginx", "mariadb", "php", "composer"),
        "docker": ("docker", "git"),
        "node": ("nodejs", "pnpm", "pm2", "git"),
        "python": ("python", "pipx", "supervisor", "git"),
    }

    def __init__(
        self,
        manifests_dir: Path,
        runner: Runner = run_command,
        privileged: bool = False,
        additional_services: tuple[str, ...] = (),
    ) -> None:
        self.manifests_dir = manifests_dir
        self.runner = runner
        self.privileged = privileged
        self._packages: PackageManager | None = None
        self.services = self.watched_services + tuple(
            name for name in additional_services if name.replace("@", "").replace("-", "").replace("_", "").replace(".", "").isalnum()
        )

    def manifests(self) -> list[dict[str, Any]]:
        result = []
        for path in sorted(self.manifests_dir.glob("*.yaml")):
            with path.open(encoding="utf-8") as stream:
                manifest = yaml.safe_load(stream)
            manifest["installed"] = self._package_installed(manifest)
            manifest["installed_version"] = self._installed_version(manifest) if manifest["installed"] else None
            manifest["available_version"] = self._available_version(manifest)
            manifest["status"] = self._service_status(manifest.get("service", {}).get("name"))
            result.append(manifest)
        return result

    def manifest(self, name: str) -> dict[str, Any] | None:
        path = self.manifests_dir / f"{name}.yaml"
        if not path.is_file():
            return None
        with path.open(encoding="utf-8") as stream:
            return yaml.safe_load(stream)

    def app_action(self, name: str, action: str) -> dict[str, Any]:
        manifest = self.manifest(name)
        if manifest is None:
            raise KeyError(name)
        if self.privileged:
            return self._privileged(["app", action, name])
        if action in {"install", "update", "remove"}:
            manager = self._package_manager()
            custom = manifest.get("commands", {}).get(manager.name, {}).get(action)
            if custom:
                if not isinstance(custom, list) or not all(isinstance(item, str) for item in custom):
                    raise RuntimeError(f"invalid command handler for {name}")
                code, output, error = self.runner(custom)
            else:
                packages = manifest.get("packages", {}).get(manager.name, [])
                if not packages:
                    raise RuntimeError(f"{name} is unavailable for {manager.name}")
                code, output, error = manager.run_action(action, packages)
        elif action in {"start", "stop", "restart"}:
            service = manifest.get("service", {}).get("name")
            if not service:
                raise RuntimeError(f"{name} has no managed service")
            command = ["systemctl", action, service]
            code, output, error = self.runner(command)
        else:
            raise ValueError(action)
        if code:
            raise RuntimeError(error or output or f"command failed with exit code {code}")
        return {"name": name, "action": action, "status": "ok", "output": output}

    def stack_install(self, name: str) -> dict[str, Any]:
        apps = self.stacks.get(name)
        if apps is None:
            raise KeyError(name)
        results = [self.app_action(app, "install") for app in apps]
        return {"name": name, "status": "ok", "apps": results}

    def app_logs(self, name: str, lines: int = 200) -> list[dict[str, str]]:
        manifest = self.manifest(name)
        if manifest is None:
            raise KeyError(name)
        if self.privileged:
            return self._privileged(["app", "logs", name])
        result = []
        for configured in manifest.get("log_paths", []):
            path = Path(configured)
            candidates = sorted(path.glob("*.log")) if path.is_dir() else [path]
            for candidate in candidates[:20]:
                if candidate.is_file():
                    content = candidate.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
                    result.append({"path": str(candidate), "content": "\n".join(content)})
        return result

    def service_statuses(self) -> list[dict[str, Any]]:
        return [
            {"name": name, "active": status == "active", "status": status}
            for name in self.services
            if (status := self._service_status(name)) != "not-found"
        ]

    def service_action(self, name: str, action: str) -> dict[str, str]:
        if name not in self.services or action not in {"start", "stop", "restart"}:
            raise ValueError("unsupported service action")
        if self.privileged:
            return self._privileged(["service", action, name])
        code, output, error = self.runner(["systemctl", action, name])
        if code:
            raise RuntimeError(error or output)
        return {"name": name, "action": action, "status": "ok"}

    def containers(self) -> list[dict[str, Any]]:
        if self.privileged:
            return self._privileged(["docker", "list"])
        if shutil.which("docker") is None:
            return []
        code, output, _ = self.runner(["docker", "ps", "-a", "--format", "{{json .}}"])
        if code:
            return []
        containers = [self._container(json.loads(line)) for line in output.splitlines() if line]
        stats_code, stats_output, _ = self.runner(["docker", "stats", "--no-stream", "--format", "{{json .}}"])
        if stats_code == 0:
            stats = [json.loads(line) for line in stats_output.splitlines() if line]
            by_name = {item.get("Name", ""): item for item in stats}
            for container in containers:
                item = by_name.get(container["name"], {})
                container.update(
                    {
                        "cpu_percent": item.get("CPUPerc", "0%"),
                        "memory_percent": item.get("MemPerc", "0%"),
                        "memory_usage": item.get("MemUsage", ""),
                    }
                )
        return containers

    def container_action(self, container_id: str, action: str) -> dict[str, str]:
        if action not in {"start", "stop", "restart"} or not container_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError("invalid container action")
        if self.privileged:
            return self._privileged(["docker", action, container_id])
        code, output, error = self.runner(["docker", action, container_id])
        if code:
            raise RuntimeError(error or output)
        return {"id": container_id, "action": action, "status": "ok"}

    def container_logs(self, container_id: str, lines: int = 200) -> dict[str, str]:
        if not container_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError("invalid container id")
        if self.privileged:
            return self._privileged(["docker", "logs", container_id])
        code, output, error = self.runner(["docker", "logs", "--tail", str(lines), container_id])
        if code:
            raise RuntimeError(error or output)
        return {"id": container_id, "logs": "\n".join(item for item in (output, error) if item)}

    def _package_manager(self) -> PackageManager:
        if self._packages is None:
            self._packages = detect_package_manager(self.runner)
        return self._packages

    def _package_installed(self, manifest: dict[str, Any]) -> bool:
        manager = self._package_manager()
        packages = manifest.get("packages", {}).get(manager.name, [])
        return bool(packages) and manager.installed(packages)

    def _installed_version(self, manifest: dict[str, Any]) -> str | None:
        manager = self._package_manager()
        packages = manifest.get("packages", {}).get(manager.name, [])
        if not packages:
            return None
        return manager.installed_version(packages[0])

    def _available_version(self, manifest: dict[str, Any]) -> str | None:
        manager = self._package_manager()
        packages = manifest.get("packages", {}).get(manager.name, [])
        if not packages:
            return None
        return manager.available_version(packages[0])

    def _service_status(self, name: str | None) -> str:
        if not name or shutil.which("systemctl") is None:
            return "not-found"
        code, output, _ = self.runner(["systemctl", "is-active", name])
        return output or ("inactive" if code else "active")

    def _privileged(self, arguments: list[str]) -> Any:
        helper = os.getenv("LIGHTOPS_PRIVILEGED_HELPER", "/opt/lightops/current/venv/bin/lightops-privileged")
        code, output, error = self.runner(["sudo", "-n", helper, *arguments])
        if code:
            raise RuntimeError(error or output or "privileged operation failed")
        try:
            return json.loads(output)
        except json.JSONDecodeError as error:
            raise RuntimeError("privileged helper returned invalid output") from error

    @staticmethod
    def _container(raw: dict[str, str]) -> dict[str, str]:
        return {
            "id": raw.get("ID", ""),
            "name": raw.get("Names", ""),
            "image": raw.get("Image", ""),
            "status": raw.get("Status", ""),
        }
