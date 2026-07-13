from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Sequence


Runner = Callable[[Sequence[str]], tuple[int, str, str]]


class PackageManager:
    name: str

    def __init__(self, runner: Runner) -> None:
        self.runner = runner

    def run_action(self, action: str, packages: list[str]) -> tuple[int, str, str]:
        if action not in {"install", "update", "remove"}:
            raise ValueError(action)
        verb = "install" if action == "update" else action
        return self.runner([self.name, verb, "-y", *packages])

    def installed(self, packages: list[str]) -> bool:
        raise NotImplementedError

    def installed_version(self, package: str) -> str | None:
        raise NotImplementedError

    def available_version(self, package: str) -> str | None:
        return None


class AptPackageManager(PackageManager):
    name = "apt-get"

    def installed(self, packages: list[str]) -> bool:
        if shutil.which("dpkg-query") is None:
            return any(shutil.which(package) for package in packages)
        return all(self.runner(["dpkg-query", "-W", "-f=${Status}", package])[0] == 0 for package in packages)

    def installed_version(self, package: str) -> str | None:
        if shutil.which("dpkg-query") is None:
            return None
        code, output, _ = self.runner(["dpkg-query", "-W", "-f=${Version}", package])
        return output if code == 0 else None

    def available_version(self, package: str) -> str | None:
        if shutil.which("apt-cache") is None:
            return None
        code, output, _ = self.runner(["apt-cache", "policy", package])
        if code:
            return None
        for line in output.splitlines():
            if line.strip().startswith("Candidate:"):
                return line.split(":", 1)[1].strip()
        return None


class RpmPackageManager(PackageManager):
    def installed(self, packages: list[str]) -> bool:
        if shutil.which("rpm") is None:
            return any(shutil.which(package) for package in packages)
        return all(self.runner(["rpm", "-q", package])[0] == 0 for package in packages)

    def installed_version(self, package: str) -> str | None:
        if shutil.which("rpm") is None:
            return None
        code, output, _ = self.runner(["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}", package])
        return output if code == 0 else None


class DnfPackageManager(RpmPackageManager):
    name = "dnf"


class YumPackageManager(RpmPackageManager):
    name = "yum"


def detect_package_manager(runner: Runner) -> PackageManager:
    if shutil.which("apt-get"):
        return AptPackageManager(runner)
    if shutil.which("dnf"):
        return DnfPackageManager(runner)
    if shutil.which("yum"):
        return YumPackageManager(runner)
    if shutil.which("dpkg-query") or shutil.which("apt-cache"):
        return AptPackageManager(runner)
    if os.name == "nt":
        return AptPackageManager(runner)
    raise RuntimeError("no supported package manager found")
