import sqlite3
from unittest.mock import patch

import pytest

from mtg_prices.db import Database


def test_schema_version_table_created(db):
    row = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    assert row is not None


def test_migrations_applied(db):
    row = db.conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    assert row[0] >= 2


def test_users_table_exists(db):
    row = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    assert row is not None


def test_decks_has_format_column(db):
    db.conn.execute("SELECT format FROM decks LIMIT 0")


def test_decks_has_user_id_column(db):
    db.conn.execute("SELECT user_id FROM decks LIMIT 0")


def test_decks_format_default_is_commander(db):
    db.conn.execute("INSERT INTO decks (name) VALUES ('test_deck')")
    row = db.conn.execute(
        "SELECT format FROM decks WHERE name = 'test_deck'"
    ).fetchone()
    assert row[0] == "commander"


def test_failed_migration_rolls_back_schema_and_version(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_broken.sql").write_text(
        "ALTER TABLE decks ADD COLUMN temporary_column TEXT;\n"
        "ALTER TABLE decks ADD COLUMN name TEXT;\n"
    )
    db = Database(":memory:")
    db.conn.executescript(
        "CREATE TABLE decks (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);\n"
        "CREATE TABLE schema_version (version INTEGER NOT NULL);"
    )

    with (
        patch("mtg_prices.db.importlib.resources.files", return_value=tmp_path),
        pytest.raises(sqlite3.OperationalError),
    ):
        db._apply_migrations()

    columns = [row[1] for row in db.conn.execute("PRAGMA table_info(decks)")]
    assert columns == ["id", "name"]
    assert db.conn.execute("SELECT * FROM schema_version").fetchall() == []
    db.close()
