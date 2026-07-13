from pathlib import Path

from sqlalchemy import create_engine, inspect

from lightops.migrations import migrate


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'lightops.db'}"

    assert migrate(database_url) == ["0001_initial"]
    assert migrate(database_url) == []
    assert {"projects", "deployments", "users", "schema_migrations"} <= set(inspect(create_engine(database_url)).get_table_names())
