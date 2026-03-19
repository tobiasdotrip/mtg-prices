from __future__ import annotations

import importlib.resources
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from mtg_prices.models import Card, Deck, PriceEntry

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    oracle_id TEXT,
    quantity INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES cards(id),
    price_usd REAL,
    price_eur REAL,
    set_code TEXT NOT NULL,
    set_name TEXT NOT NULL,
    fetched_at DATE NOT NULL,
    UNIQUE(card_id, fetched_at)
);

CREATE INDEX IF NOT EXISTS idx_prices_card_date ON prices(card_id, fetched_at);

CREATE TABLE IF NOT EXISTS decks (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS deck_cards (
    deck_id INTEGER NOT NULL REFERENCES decks(id),
    card_id INTEGER NOT NULL REFERENCES cards(id),
    quantity INTEGER NOT NULL DEFAULT 1,
    UNIQUE(deck_id, card_id)
);
"""

_MIGRATIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, path: str | Path) -> None:
        self.conn = sqlite3.connect(str(path))
        self.conn.execute("PRAGMA foreign_keys = ON")

    def init(self) -> None:
        self.conn.executescript(_SCHEMA)
        self.conn.executescript(_MIGRATIONS_SCHEMA)
        self._apply_migrations()

    def _apply_migrations(self) -> None:
        row = self.conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        current = row[0] if row[0] is not None else 0

        migrations_dir = importlib.resources.files("mtg_prices") / "migrations"
        migration_files = sorted(
            f
            for f in migrations_dir.iterdir()
            if f.name.endswith(".sql") and f.name.split("_")[0].isdigit()
        )

        for mf in migration_files:
            version = int(mf.name.split("_")[0])
            if version <= current:
                continue
            sql = mf.read_text(encoding="utf-8")
            self.conn.executescript(sql)
            self.conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (version,),
            )
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def upsert_card(self, card: Card) -> int:
        self.conn.execute(
            """
            INSERT INTO cards (name, oracle_id, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                oracle_id = COALESCE(excluded.oracle_id, cards.oracle_id),
                quantity = excluded.quantity
            """,
            (card.name, card.oracle_id, card.quantity),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM cards WHERE name = ?", (card.name,)
        ).fetchone()
        return row[0]

    def upsert_price(self, entry: PriceEntry) -> None:
        self.conn.execute(
            """
            INSERT INTO prices
                (card_id, price_usd, price_eur,
                 set_code, set_name, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(card_id, fetched_at) DO UPDATE SET
                price_usd = excluded.price_usd,
                price_eur = excluded.price_eur,
                set_code = excluded.set_code,
                set_name = excluded.set_name
            """,
            (
                entry.card_id,
                entry.price_usd,
                entry.price_eur,
                entry.set_code,
                entry.set_name,
                entry.fetched_at.isoformat(),
            ),
        )
        self.conn.commit()

    def get_price_at(
        self, card_id: int, target: date, tolerance_days: int = 2
    ) -> PriceEntry | None:
        start = (target - timedelta(days=tolerance_days)).isoformat()
        end = (target + timedelta(days=tolerance_days)).isoformat()
        row = self.conn.execute(
            """
            SELECT id, card_id, price_usd, price_eur, set_code, set_name, fetched_at
            FROM prices
            WHERE card_id = ? AND fetched_at BETWEEN ? AND ?
            ORDER BY ABS(julianday(fetched_at) - julianday(?))
            LIMIT 1
            """,
            (card_id, start, end, target.isoformat()),
        ).fetchone()
        if row is None:
            return None
        return PriceEntry(
            id=row[0],
            card_id=row[1],
            price_usd=row[2],
            price_eur=row[3],
            set_code=row[4],
            set_name=row[5],
            fetched_at=date.fromisoformat(row[6]),
        )

    def get_latest_price(self, card_id: int) -> PriceEntry | None:
        row = self.conn.execute(
            """
            SELECT id, card_id, price_usd, price_eur, set_code, set_name, fetched_at
            FROM prices
            WHERE card_id = ?
            ORDER BY fetched_at DESC
            LIMIT 1
            """,
            (card_id,),
        ).fetchone()
        if row is None:
            return None
        return PriceEntry(
            id=row[0],
            card_id=row[1],
            price_usd=row[2],
            price_eur=row[3],
            set_code=row[4],
            set_name=row[5],
            fetched_at=date.fromisoformat(row[6]),
        )

    def get_all_cards(self) -> list[Card]:
        rows = self.conn.execute(
            "SELECT id, name, oracle_id, quantity FROM cards ORDER BY name"
        ).fetchall()
        return [Card(id=r[0], name=r[1], oracle_id=r[2], quantity=r[3]) for r in rows]

    def upsert_deck(self, name: str, deck_format: str | None = None) -> int:
        if deck_format is not None:
            self.conn.execute(
                "INSERT INTO decks (name, format) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET format = excluded.format",
                (name, deck_format),
            )
        else:
            self.conn.execute(
                "INSERT INTO decks (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
                (name,),
            )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM decks WHERE name = ?", (name,)
        ).fetchone()
        return row[0]

    def add_card_to_deck(self, deck_id: int, card_id: int, quantity: int) -> None:
        self.conn.execute(
            """
            INSERT INTO deck_cards (deck_id, card_id, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(deck_id, card_id) DO UPDATE SET quantity = excluded.quantity
            """,
            (deck_id, card_id, quantity),
        )
        self.conn.commit()

    def remove_card_from_deck(self, deck_id: int, card_id: int) -> None:
        self.conn.execute(
            "DELETE FROM deck_cards WHERE deck_id = ? AND card_id = ?",
            (deck_id, card_id),
        )
        self.conn.commit()

    def clear_deck(self, deck_id: int) -> None:
        self.conn.execute("DELETE FROM deck_cards WHERE deck_id = ?", (deck_id,))
        self.conn.commit()

    def get_deck_cards(self, deck_id: int) -> list[Card]:
        rows = self.conn.execute(
            """
            SELECT c.id, c.name, c.oracle_id, dc.quantity
            FROM cards c
            JOIN deck_cards dc ON dc.card_id = c.id
            WHERE dc.deck_id = ?
            ORDER BY c.name
            """,
            (deck_id,),
        ).fetchall()
        return [Card(id=r[0], name=r[1], oracle_id=r[2], quantity=r[3]) for r in rows]

    def get_all_decks(self) -> list[Deck]:
        rows = self.conn.execute(
            "SELECT id, name, format FROM decks ORDER BY name"
        ).fetchall()
        return [Deck(id=r[0], name=r[1], format=r[2]) for r in rows]

    def get_deck_by_name(self, name: str) -> Deck | None:
        row = self.conn.execute(
            "SELECT id, name, format FROM decks WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return Deck(id=row[0], name=row[1], format=row[2])

    def put_suggest_cache(
        self, deck_id: int, card_id: int, threshold: float, result_json: str
    ) -> None:
        self.conn.execute(
            "INSERT INTO suggest_cache (deck_id, card_id, threshold, result_json) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(deck_id, card_id, threshold) DO UPDATE SET "
            "result_json = excluded.result_json, created_at = CURRENT_TIMESTAMP",
            (deck_id, card_id, threshold, result_json),
        )
        self.conn.commit()

    def get_suggest_cache(
        self, deck_id: int, card_id: int, threshold: float, max_age_hours: int = 24
    ) -> str | None:
        row = self.conn.execute(
            "SELECT result_json, created_at FROM suggest_cache "
            "WHERE deck_id = ? AND card_id = ? AND threshold = ?",
            (deck_id, card_id, threshold),
        ).fetchone()
        if row is None:
            return None
        created_at = datetime.fromisoformat(row[1]).replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - created_at).total_seconds() > max_age_hours * 3600:
            return None
        return row[0]

    def clear_suggest_cache(self) -> None:
        self.conn.execute("DELETE FROM suggest_cache")
        self.conn.commit()
