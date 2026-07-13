from __future__ import annotations

import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class BackupService:
    def __init__(self, backup_dir: Path, retention: int = 7) -> None:
        self.backup_dir = backup_dir
        self.retention = max(1, retention)

    def create(self, name: str, sources: list[str]) -> dict[str, Any]:
        source_paths = [Path(source) for source in sources]
        missing = [str(path) for path in source_paths if not path.exists()]
        if missing:
            raise ValueError(f"backup source does not exist: {', '.join(missing)}")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.backup_dir / f"{name}-{stamp}.tar.gz"
        temporary = target.with_suffix(target.suffix + ".tmp")
        try:
            with tarfile.open(temporary, "w:gz") as archive:
                for source in source_paths:
                    archive.add(source, arcname=source.name, recursive=True)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        self._prune(name)
        return self._describe(target)

    def list(self) -> list[dict[str, Any]]:
        if not self.backup_dir.exists():
            return []
        return [self._describe(path) for path in sorted(self.backup_dir.glob("*.tar.gz"), reverse=True)]

    def restore(self, filename: str, target_dir: Path) -> dict[str, str]:
        archive_path = self.backup_dir / filename
        if archive_path.parent.resolve() != self.backup_dir.resolve() or not archive_path.is_file():
            raise ValueError("backup does not exist")
        target_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "r:gz") as archive:
            root = target_dir.resolve()
            for member in archive.getmembers():
                destination = (target_dir / member.name).resolve()
                if root != destination and root not in destination.parents:
                    raise ValueError("backup contains an unsafe path")
            archive.extractall(target_dir)
        return {"backup": filename, "target": str(target_dir), "status": "ok"}

    @staticmethod
    def _describe(path: Path) -> dict[str, Any]:
        stat = path.stat()
        name = path.name.rsplit("-", 1)[0]
        return {
            "name": name,
            "filename": path.name,
            "path": str(path),
            "size": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        }

    def _prune(self, name: str) -> None:
        archives = sorted(self.backup_dir.glob(f"{name}-*.tar.gz"), reverse=True)
        for archive in archives[self.retention :]:
            archive.unlink()
