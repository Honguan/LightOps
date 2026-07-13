from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence

from sqlalchemy import Engine, create_engine, text

from .config import load_settings
from .store import Base


Migration = tuple[str, bool, Callable[[Engine], None]]


def initial_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


MIGRATIONS: tuple[Migration, ...] = (("0001_initial", True, initial_schema),)


def migrate(database_url: str) -> list[str]:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(64) PRIMARY KEY)"))
        applied = {row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))}
    completed = []
    for version, _reversible, upgrade in MIGRATIONS:
        if version in applied:
            continue
        upgrade(engine)
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO schema_migrations (version) VALUES (:version)"), {"version": version})
        completed.append(version)
    return completed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lightops-migrate")
    parser.add_argument("command", choices=("up",))
    args = parser.parse_args(argv)
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    for version in migrate(settings.database_url):
        print(f"Applied migration {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
