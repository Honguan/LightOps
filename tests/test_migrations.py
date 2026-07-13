from pathlib import Path

from sqlalchemy import create_engine, inspect

from lightops.migrations import migrate, migration_plan


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'lightops.db'}"

    assert migration_plan(database_url) == [{"version": "0001_initial", "reversible": True}]
    assert "schema_migrations" not in inspect(create_engine(database_url)).get_table_names()
    assert migrate(database_url) == ["0001_initial"]
    assert migration_plan(database_url) == []
    assert migrate(database_url) == []
    assert {"projects", "deployments", "users", "schema_migrations"} <= set(inspect(create_engine(database_url)).get_table_names())
