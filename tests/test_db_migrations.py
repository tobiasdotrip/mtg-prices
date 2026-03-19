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
