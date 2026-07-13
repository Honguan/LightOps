from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator


SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")


class ProjectCreate(BaseModel):
    name: str
    code: str
    project_type: str
    repository: str
    branch: str = "main"
    deploy_path: str
    health_url: str | None = None
    retain_releases: int = 3

    @field_validator("code")
    @classmethod
    def safe_code(cls, value: str) -> str:
        if not SAFE_NAME.fullmatch(value):
            raise ValueError("code must contain only lowercase letters, numbers, hyphens, or underscores")
        return value

    @field_validator("project_type")
    @classmethod
    def supported_type(cls, value: str) -> str:
        supported = {
            "static", "php", "laravel", "wordpress", "node", "express", "nestjs", "nextjs", "nuxt", "vue", "react",
            "python", "flask", "django", "fastapi", "docker", "docker-compose", "spring-boot", "go",
        }
        if value not in supported:
            raise ValueError("unsupported project type")
        return value

    @field_validator("deploy_path")
    @classmethod
    def absolute_path(cls, value: str) -> str:
        if not Path(value).is_absolute():
            raise ValueError("deploy_path must be absolute")
        return value


class ProjectView(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class BackupCreate(BaseModel):
    name: str
    sources: list[str]

    @field_validator("name")
    @classmethod
    def safe_name(cls, value: str) -> str:
        if not SAFE_NAME.fullmatch(value):
            raise ValueError("name must contain only lowercase letters, numbers, hyphens, or underscores")
        return value

    @field_validator("sources")
    @classmethod
    def absolute_sources(cls, value: list[str]) -> list[str]:
        if not value or any(not Path(item).is_absolute() for item in value):
            raise ValueError("at least one absolute source path is required")
        return value


class BackupRestore(BaseModel):
    target: str

    @field_validator("target")
    @classmethod
    def absolute_target(cls, value: str) -> str:
        if not Path(value).is_absolute():
            raise ValueError("target must be absolute")
        return value


class LoginRequest(BaseModel):
    username: str
    password: str
    totp: str | None = None


class TotpEnable(BaseModel):
    code: str
