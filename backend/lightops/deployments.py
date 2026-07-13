from __future__ import annotations

import os
import shutil
import subprocess
import urllib.request
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .store import Project, Store


DeployRunner = Callable[[Sequence[str], Path], tuple[int, str, str]]


def run_deploy_command(command: Sequence[str], cwd: Path) -> tuple[int, str, str]:
    completed = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900, check=False
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


class DeploymentService:
    template_aliases = {
        "wordpress": "static",
        "express": "node",
        "nestjs": "node",
        "nextjs": "node",
        "nuxt": "node",
        "vue": "node",
        "react": "node",
        "flask": "python",
        "django": "python",
        "fastapi": "python",
        "docker": "docker-compose",
    }
    def __init__(self, store: Store, runner: DeployRunner = run_deploy_command, templates_dir: Path | None = None) -> None:
        self.store = store
        self.runner = runner
        self.templates_dir = templates_dir or Path(__file__).resolve().parents[2] / "deployment-templates"

    def deploy(self, code: str, operator: str = "cli") -> dict[str, Any]:
        project = self.store.project(code)
        if project is None:
            raise KeyError(code)
        started = datetime.now(timezone.utc)
        releases_dir = Path(project.deploy_path) / "releases"
        releases_dir.mkdir(parents=True, exist_ok=True)
        release = releases_dir / started.strftime("%Y%m%dT%H%M%S%fZ")
        current = Path(project.deploy_path) / "current"
        previous = str(current.resolve()) if current.exists() else None
        output: list[str] = []
        switched = False
        try:
            clone = ["git", "clone", "--depth", "1", "--branch", project.branch, "--", project.repository, str(release)]
            self._run(clone, releases_dir, output)
            for command in self._build_steps(project.project_type):
                self._run(command, release, output)
            commit_hash = self._run(("git", "rev-parse", "HEAD"), release, output)
            self._switch_current(current, release)
            switched = True
            self._health_check(project.health_url)
            self._prune(releases_dir, project.retain_releases, current.resolve())
        except (OSError, RuntimeError) as error:
            if switched:
                if previous:
                    self._switch_current(current, Path(previous))
                else:
                    current.unlink(missing_ok=True)
            shutil.rmtree(release, ignore_errors=True)
            self._record(project, started, release, previous, operator, "failed", output, str(error), "")
            raise RuntimeError(str(error)) from error
        deployment = self._record(project, started, release, previous, operator, "success", output, "", commit_hash)
        return self._deployment_dict(deployment)

    def rollback(self, code: str, operator: str = "cli") -> dict[str, Any]:
        project = self.store.project(code)
        if project is None:
            raise KeyError(code)
        current = Path(project.deploy_path) / "current"
        releases_dir = Path(project.deploy_path) / "releases"
        active = current.resolve() if current.exists() else None
        candidates = [path for path in sorted(releases_dir.iterdir(), reverse=True) if path.is_dir() and path.resolve() != active]
        if not candidates:
            raise RuntimeError("no previous release is available")
        started = datetime.now(timezone.utc)
        target = candidates[0]
        previous = str(active) if active else None
        self._switch_current(current, target)
        deployment = self._record(project, started, target, previous, operator, "rollback", [], "", "")
        return self._deployment_dict(deployment)

    def history(self, code: str) -> list[dict[str, Any]]:
        project = self.store.project(code)
        if project is None:
            raise KeyError(code)
        return [self._deployment_dict(item) for item in self.store.deployments(project.id)]

    def _run(self, command: Sequence[str], cwd: Path, output: list[str]) -> str:
        code, stdout, stderr = self.runner(command, cwd)
        if stdout:
            output.append(stdout)
        if code:
            raise RuntimeError(stderr or stdout or f"command failed: {command[0]}")
        return stdout

    def _build_steps(self, project_type: str) -> list[list[str]]:
        template_name = self.template_aliases.get(project_type, project_type)
        path = self.templates_dir / f"{template_name}.yaml"
        with path.open(encoding="utf-8") as stream:
            template = yaml.safe_load(stream)
        commands = template.get("commands", [])
        if not all(isinstance(command, list) and command and all(isinstance(item, str) for item in command) for command in commands):
            raise RuntimeError(f"invalid deployment template: {project_type}")
        return commands

    @staticmethod
    def _health_check(url: str | None) -> None:
        if not url:
            return
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                if response.status >= 400:
                    raise RuntimeError(f"health check failed with HTTP {response.status}")
        except OSError as error:
            raise RuntimeError(f"health check failed: {error}") from error

    @staticmethod
    def _switch_current(current: Path, release: Path) -> None:
        temporary = current.with_name(".current-new")
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(release, target_is_directory=True)
        os.replace(temporary, current)

    @staticmethod
    def _prune(releases_dir: Path, retain: int, active: Path) -> None:
        releases = sorted((path for path in releases_dir.iterdir() if path.is_dir()), reverse=True)
        for release in releases[max(1, retain):]:
            if release.resolve() != active:
                shutil.rmtree(release)

    def _record(
        self,
        project: Project,
        started: datetime,
        release: Path,
        previous: str | None,
        operator: str,
        result: str,
        output: list[str],
        error: str,
        commit_hash: str,
    ) -> object:
        return self.store.record_deployment(
            project_id=project.id,
            commit_hash=commit_hash,
            previous_release=previous,
            release_path=str(release),
            operator=operator,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            result=result,
            output="\n".join(output),
            error=error,
        )

    @staticmethod
    def _deployment_dict(deployment: object) -> dict[str, Any]:
        fields = ("id", "project_id", "commit_hash", "previous_release", "release_path", "operator", "started_at", "finished_at", "result", "output", "error")
        return {field: getattr(deployment, field) for field in fields}
