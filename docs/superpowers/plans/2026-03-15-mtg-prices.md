# MTG Prices Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI tool that scrapes MTG card prices from Scryfall, stores them in SQLite, and reports 7d/30d price trends.

**Architecture:** Python package with Click CLI, httpx for Scryfall API, SQLite for storage, Rich for console output. Modular design: models → db → scraper → report → cli.

**Tech Stack:** Python 3.12+, Click, httpx, Rich, pytest

**Spec:** `docs/superpowers/specs/2026-03-15-mtg-prices-design.md`

---

## Chunk 1: Project Setup + Models + DB

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/mtg_prices/__init__.py`
- Create: `.gitignore`
- Create: `data/.gitkeep`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mtg-prices"
version = "0.1.0"
description = "MTG card price tracker using Scryfall API"
requires-python = ">=3.12"
dependencies = [
    "click>=8.1",
    "httpx>=0.27",
    "rich>=13.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
]

[project.scripts]
mtg-prices = "mtg_prices.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.hatch.build.targets.wheel]
packages = ["src/mtg_prices"]
```

- [ ] **Step 2: Create `src/mtg_prices/__init__.py`**

```python
"""MTG card price tracker using Scryfall API."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Create `.gitignore`**

```
data/*.db
data/*.log
data/export_*
__pycache__/
*.pyc
.venv/
*.egg-info/
dist/
```

- [ ] **Step 4: Create `data/.gitkeep`**

Empty file to track the data directory.

- [ ] **Step 5: Install the package in dev mode**

Run: `cd /c/Users/Koby/Github/mtg-prices && pip install -e ".[dev]" 2>&1 | tail -5`
Expected: Successfully installed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/ .gitignore data/.gitkeep
git commit -m "feat: scaffold project structure"
```

---

### Task 2: Models

**Files:**
- Create: `src/mtg_prices/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write tests for models**

```python
# tests/test_models.py
from datetime import date
from mtg_prices.models import Card, PriceEntry, CardReport


def test_card_creation():
    card = Card(name="Lightning Bolt", quantity=4, oracle_id="abc-123")
    assert card.name == "Lightning Bolt"
    assert card.quantity == 4
    assert card.oracle_id == "abc-123"
    assert card.id is None


def test_card_default_values():
    card = Card(name="Lightning Bolt")
    assert card.quantity == 1
    assert card.oracle_id is None
    assert card.id is None


def test_price_entry_creation():
    entry = PriceEntry(
        card_id=1,
        price_usd=2.50,
        price_eur=2.10,
        set_code="MH3",
        set_name="Modern Horizons 3",
        fetched_at=date(2026, 3, 15),
    )
    assert entry.price_usd == 2.50
    assert entry.set_code == "MH3"
    assert entry.fetched_at == date(2026, 3, 15)


def test_card_report_creation():
    report = CardReport(
        name="Lightning Bolt",
        quantity=4,
        price=2.50,
        set_code="MH3",
        trends={7: 3.2, 30: -1.8},
    )
    assert report.trends[7] == 3.2
    assert report.trends[30] == -1.8


def test_card_report_no_trends():
    report = CardReport(
        name="Lightning Bolt",
        quantity=4,
        price=2.50,
        set_code="MH3",
        trends={7: None, 30: None},
    )
    assert report.trends[7] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement models**

```python
# src/mtg_prices/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Card:
    name: str
    quantity: int = 1
    oracle_id: str | None = None
    id: int | None = None


@dataclass
class PriceEntry:
    card_id: int
    price_usd: float | None
    price_eur: float | None
    set_code: str
    set_name: str
    fetched_at: date
    id: int | None = None


@dataclass
class CardReport:
    name: str
    quantity: int
    price: float | None
    set_code: str
    trends: dict[int, float | None] = field(default_factory=dict)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/mtg_prices/models.py tests/test_models.py
git commit -m "feat: add data models (Card, PriceEntry, CardReport)"
```

---

### Task 3: Database layer

**Files:**
- Create: `src/mtg_prices/db.py`
- Create: `tests/test_db.py`
- Create: `tests/conftest.py`

**Note:** `conftest.py` fixtures are auto-discovered by pytest. Tasks 6 and 7 depend on the `db` fixture defined here — this task must be completed first.

- [ ] **Step 1: Write conftest with in-memory DB fixture**

```python
# tests/conftest.py
import pytest
from mtg_prices.db import Database


@pytest.fixture
def db():
    database = Database(":memory:")
    database.init()
    yield database
    database.close()
```

- [ ] **Step 2: Write tests for DB init and card operations**

```python
# tests/test_db.py
from datetime import date
from mtg_prices.models import Card, PriceEntry


def test_init_creates_tables(db):
    cursor = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert "cards" in tables
    assert "prices" in tables


def test_upsert_card_insert(db):
    card = Card(name="Lightning Bolt", quantity=4, oracle_id="abc-123")
    card_id = db.upsert_card(card)
    assert card_id is not None
    assert card_id > 0


def test_upsert_card_update_quantity(db):
    card1 = Card(name="Lightning Bolt", quantity=4, oracle_id="abc-123")
    id1 = db.upsert_card(card1)
    card2 = Card(name="Lightning Bolt", quantity=2, oracle_id="abc-123")
    id2 = db.upsert_card(card2)
    assert id1 == id2
    # Verify quantity updated
    row = db.conn.execute("SELECT quantity FROM cards WHERE id = ?", (id1,)).fetchone()
    assert row[0] == 2


def test_insert_price(db):
    card = Card(name="Lightning Bolt", quantity=4)
    card_id = db.upsert_card(card)
    entry = PriceEntry(
        card_id=card_id,
        price_usd=2.50,
        price_eur=2.10,
        set_code="MH3",
        set_name="Modern Horizons 3",
        fetched_at=date(2026, 3, 15),
    )
    db.upsert_price(entry)
    row = db.conn.execute("SELECT price_usd FROM prices WHERE card_id = ?", (card_id,)).fetchone()
    assert row[0] == 2.50


def test_upsert_price_same_day(db):
    card = Card(name="Lightning Bolt", quantity=4)
    card_id = db.upsert_card(card)
    entry1 = PriceEntry(
        card_id=card_id, price_usd=2.50, price_eur=2.10,
        set_code="MH3", set_name="Modern Horizons 3", fetched_at=date(2026, 3, 15),
    )
    entry2 = PriceEntry(
        card_id=card_id, price_usd=3.00, price_eur=2.50,
        set_code="MH3", set_name="Modern Horizons 3", fetched_at=date(2026, 3, 15),
    )
    db.upsert_price(entry1)
    db.upsert_price(entry2)
    rows = db.conn.execute("SELECT price_usd FROM prices WHERE card_id = ?", (card_id,)).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 3.00


def test_get_price_at_date(db):
    card = Card(name="Lightning Bolt", quantity=4)
    card_id = db.upsert_card(card)
    entry = PriceEntry(
        card_id=card_id, price_usd=2.50, price_eur=2.10,
        set_code="MH3", set_name="Modern Horizons 3", fetched_at=date(2026, 3, 10),
    )
    db.upsert_price(entry)
    price = db.get_price_at(card_id, date(2026, 3, 10), tolerance_days=2)
    assert price is not None
    assert price.price_usd == 2.50


def test_get_price_at_date_with_tolerance(db):
    card = Card(name="Lightning Bolt", quantity=4)
    card_id = db.upsert_card(card)
    entry = PriceEntry(
        card_id=card_id, price_usd=2.50, price_eur=2.10,
        set_code="MH3", set_name="Modern Horizons 3", fetched_at=date(2026, 3, 9),
    )
    db.upsert_price(entry)
    # Exact date not found, but within ±2 days
    price = db.get_price_at(card_id, date(2026, 3, 10), tolerance_days=2)
    assert price is not None
    assert price.price_usd == 2.50


def test_get_price_at_date_out_of_tolerance(db):
    card = Card(name="Lightning Bolt", quantity=4)
    card_id = db.upsert_card(card)
    entry = PriceEntry(
        card_id=card_id, price_usd=2.50, price_eur=2.10,
        set_code="MH3", set_name="Modern Horizons 3", fetched_at=date(2026, 3, 5),
    )
    db.upsert_price(entry)
    price = db.get_price_at(card_id, date(2026, 3, 10), tolerance_days=2)
    assert price is None


def test_get_latest_price(db):
    card = Card(name="Lightning Bolt", quantity=4)
    card_id = db.upsert_card(card)
    for day, usd in [(10, 2.0), (12, 2.5), (14, 3.0)]:
        entry = PriceEntry(
            card_id=card_id, price_usd=usd, price_eur=None,
            set_code="MH3", set_name="Modern Horizons 3", fetched_at=date(2026, 3, day),
        )
        db.upsert_price(entry)
    price = db.get_latest_price(card_id)
    assert price is not None
    assert price.price_usd == 3.0


def test_get_all_cards(db):
    db.upsert_card(Card(name="Lightning Bolt", quantity=4))
    db.upsert_card(Card(name="Counterspell", quantity=2))
    cards = db.get_all_cards()
    assert len(cards) == 2
    names = {c.name for c in cards}
    assert names == {"Lightning Bolt", "Counterspell"}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_db.py -v`
Expected: FAIL

- [ ] **Step 4: Implement database layer**

```python
# src/mtg_prices/db.py
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from mtg_prices.models import Card, PriceEntry

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
"""


class Database:
    def __init__(self, path: str | Path) -> None:
        self.conn = sqlite3.connect(str(path))
        self.conn.execute("PRAGMA foreign_keys = ON")

    def init(self) -> None:
        self.conn.executescript(_SCHEMA)

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
            INSERT INTO prices (card_id, price_usd, price_eur, set_code, set_name, fetched_at)
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
        return [
            Card(id=r[0], name=r[1], oracle_id=r[2], quantity=r[3])
            for r in rows
        ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/mtg_prices/db.py tests/test_db.py tests/conftest.py
git commit -m "feat: add SQLite database layer with upsert and trend queries"
```

---

## Chunk 2: Scraper + File Parser

### Task 4: File parser

**Files:**
- Create: `src/mtg_prices/parser.py`
- Create: `tests/test_parser.py`

- [ ] **Step 1: Write tests for file parsing**

```python
# tests/test_parser.py
import textwrap
from pathlib import Path

from mtg_prices.parser import parse_decklist


def test_parse_simple_line(tmp_path):
    f = tmp_path / "cards.txt"
    f.write_text("4 Lightning Bolt\n")
    cards = parse_decklist(f)
    assert len(cards) == 1
    assert cards[0].name == "Lightning Bolt"
    assert cards[0].quantity == 4


def test_parse_multiple_lines(tmp_path):
    f = tmp_path / "cards.txt"
    f.write_text("4 Lightning Bolt\n1 Demonic Tutor\n")
    cards = parse_decklist(f)
    assert len(cards) == 2


def test_skip_empty_lines(tmp_path):
    f = tmp_path / "cards.txt"
    f.write_text("4 Lightning Bolt\n\n1 Demonic Tutor\n")
    cards = parse_decklist(f)
    assert len(cards) == 2


def test_skip_comments(tmp_path):
    f = tmp_path / "cards.txt"
    f.write_text("# Creatures\n4 Lightning Bolt\n")
    cards = parse_decklist(f)
    assert len(cards) == 1


def test_card_with_comma_in_name(tmp_path):
    f = tmp_path / "cards.txt"
    f.write_text("1 Sheoldred, the Apocalypse\n")
    cards = parse_decklist(f)
    assert cards[0].name == "Sheoldred, the Apocalypse"


def test_card_with_apostrophe(tmp_path):
    f = tmp_path / "cards.txt"
    f.write_text("1 K'rrik, Son of Yawgmoth\n")
    cards = parse_decklist(f)
    assert cards[0].name == "K'rrik, Son of Yawgmoth"


def test_malformed_line_skipped(tmp_path, caplog):
    f = tmp_path / "cards.txt"
    f.write_text("Lightning Bolt\n4 Counterspell\n")
    cards = parse_decklist(f)
    assert len(cards) == 1
    assert cards[0].name == "Counterspell"


def test_empty_file(tmp_path):
    f = tmp_path / "cards.txt"
    f.write_text("")
    cards = parse_decklist(f)
    assert len(cards) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_parser.py -v`
Expected: FAIL

- [ ] **Step 3: Implement parser**

```python
# src/mtg_prices/parser.py
from __future__ import annotations

import logging
import re
from pathlib import Path

from mtg_prices.models import Card

logger = logging.getLogger(__name__)

_LINE_RE = re.compile(r"^(\d+)\s+(.+)$")


def parse_decklist(path: Path) -> list[Card]:
    cards: list[Card] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if not m:
            logger.warning("Line %d malformed, skipping: %r", lineno, line)
            continue
        qty = int(m.group(1))
        name = m.group(2).strip()
        cards.append(Card(name=name, quantity=qty))
    return cards
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_parser.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/mtg_prices/parser.py tests/test_parser.py
git commit -m "feat: add decklist file parser"
```

---

### Task 5: Scraper (Scryfall client)

**Files:**
- Create: `src/mtg_prices/scraper.py`
- Create: `tests/test_scraper.py`

- [ ] **Step 1: Write tests for name normalization**

```python
# tests/test_scraper.py
from mtg_prices.scraper import normalize_name, select_best_price


def test_normalize_ascii():
    assert normalize_name("Lightning Bolt") == "Lightning Bolt"


def test_normalize_diacritics():
    assert normalize_name("Jötun Grunt") == "Jotun Grunt"


def test_normalize_accented():
    assert normalize_name("Séance") == "Seance"
```

- [ ] **Step 2: Write tests for price selection logic**

```python
# tests/test_scraper.py (append)

def test_select_best_price_usd():
    prints = [
        {"prices": {"usd": "5.00", "eur": "4.00"}, "set": "SET1", "set_name": "Set One", "oracle_id": "abc"},
        {"prices": {"usd": "3.00", "eur": "2.50"}, "set": "SET2", "set_name": "Set Two", "oracle_id": "abc"},
        {"prices": {"usd": "7.00", "eur": "6.00"}, "set": "SET3", "set_name": "Set Three", "oracle_id": "abc"},
    ]
    result = select_best_price(prints, max_editions=5)
    assert result is not None
    assert result["price_usd"] == 3.0
    assert result["set_code"] == "SET2"


def test_select_best_price_skips_null():
    prints = [
        {"prices": {"usd": None, "eur": None}, "set": "SET1", "set_name": "Set One", "oracle_id": "abc"},
        {"prices": {"usd": "3.00", "eur": "2.50"}, "set": "SET2", "set_name": "Set Two", "oracle_id": "abc"},
    ]
    result = select_best_price(prints, max_editions=5)
    assert result is not None
    assert result["price_usd"] == 3.0


def test_select_best_price_all_null():
    prints = [
        {"prices": {"usd": None, "eur": None}, "set": "SET1", "set_name": "Set One", "oracle_id": "abc"},
    ]
    result = select_best_price(prints, max_editions=5)
    assert result is None


def test_select_best_price_limits_editions():
    prints = [
        {"prices": {"usd": str(i), "eur": str(i)}, "set": f"S{i}", "set_name": f"Set {i}", "oracle_id": "abc"}
        for i in range(10, 0, -1)  # 10 editions, prices 10 down to 1
    ]
    # Only looks at first 5 (prices 10,9,8,7,6) — cheapest is 6
    result = select_best_price(prints, max_editions=5)
    assert result is not None
    assert result["price_usd"] == 6.0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_scraper.py -v`
Expected: FAIL

- [ ] **Step 4: Implement scraper (normalization + price selection)**

```python
# src/mtg_prices/scraper.py
from __future__ import annotations

import logging
import time
import unicodedata
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.scryfall.com"
_HEADERS = {
    "User-Agent": "mtg-prices/0.1.0",
    "Accept": "application/json",
}
_REQUEST_DELAY = 0.1  # 100ms between requests


def normalize_name(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def select_best_price(
    prints: list[dict[str, Any]], max_editions: int = 5
) -> dict[str, Any] | None:
    """Select the cheapest USD price among the most recent editions.

    EUR price returned is from the same edition as the best USD price,
    not the cheapest EUR across editions. This is intentional — we track
    by edition, not by individual currency.
    """
    best: dict[str, Any] | None = None
    best_usd = float("inf")
    for card_data in prints[:max_editions]:
        prices = card_data.get("prices", {})
        usd_str = prices.get("usd")
        if usd_str is None:
            continue
        usd = float(usd_str)
        eur_str = prices.get("eur")
        eur = float(eur_str) if eur_str else None
        if usd < best_usd:
            best_usd = usd
            best = {
                "price_usd": usd,
                "price_eur": eur,
                "set_code": card_data["set"],
                "set_name": card_data["set_name"],
                "oracle_id": card_data.get("oracle_id"),
            }
    return best


class ScryfallClient:
    def __init__(self) -> None:
        self._client = httpx.Client(headers=_HEADERS, timeout=30.0)
        self._last_request: float = 0

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < _REQUEST_DELAY:
            time.sleep(_REQUEST_DELAY - elapsed)
        self._last_request = time.monotonic()

    def _get(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        self._rate_limit()
        for attempt in range(3):
            resp = self._client.get(url, params=params)
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = 2 ** attempt
                logger.warning("Scryfall %d, retrying in %ds...", resp.status_code, wait)
                time.sleep(wait)
                continue
            return resp
        return resp  # return last response even if failed

    def search_card(self, name: str) -> dict[str, Any] | None:
        normalized = normalize_name(name)
        # Exact search — returns all prints
        resp = self._get(
            f"{_BASE_URL}/cards/search",
            params={"q": f'!"{normalized}"', "order": "released", "dir": "desc"},
        )
        if resp.status_code == 200:
            data = resp.json()
            prints = data.get("data", [])
            return select_best_price(prints)

        # Fallback: fuzzy search (single result, lose multi-edition selection)
        logger.info("Exact search failed for %r, trying fuzzy", name)
        resp = self._get(
            f"{_BASE_URL}/cards/named",
            params={"fuzzy": name},
        )
        if resp.status_code == 200:
            card_data = resp.json()
            return select_best_price([card_data])

        logger.warning("Card not found on Scryfall: %r", name)
        return None

    def close(self) -> None:
        self._client.close()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_scraper.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/mtg_prices/scraper.py tests/test_scraper.py
git commit -m "feat: add Scryfall client with name normalization and price selection"
```

---

## Chunk 3: Report + CLI

### Task 6: Report module

**Files:**
- Create: `src/mtg_prices/report.py`
- Create: `tests/test_report.py`

- [ ] **Step 1: Write tests for trend calculation**

```python
# tests/test_report.py
import json
import csv
import io
from datetime import date

from mtg_prices.models import Card, PriceEntry, CardReport
from mtg_prices.report import build_reports, export_csv, export_json

BASIC_LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest",
               "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
               "Snow-Covered Mountain", "Snow-Covered Forest", "Wastes"}


def test_build_reports(db):
    card = Card(name="Lightning Bolt", quantity=4)
    card_id = db.upsert_card(card)
    # Today's price
    db.upsert_price(PriceEntry(
        card_id=card_id, price_usd=3.0, price_eur=2.5,
        set_code="MH3", set_name="Modern Horizons 3", fetched_at=date(2026, 3, 15),
    ))
    # 7 days ago
    db.upsert_price(PriceEntry(
        card_id=card_id, price_usd=2.5, price_eur=2.0,
        set_code="MH3", set_name="Modern Horizons 3", fetched_at=date(2026, 3, 8),
    ))
    reports = build_reports(db, days=[7, 30], currency="usd", today=date(2026, 3, 15))
    assert len(reports) == 1
    r = reports[0]
    assert r.name == "Lightning Bolt"
    assert r.price == 3.0
    assert r.trends[7] is not None
    assert abs(r.trends[7] - 20.0) < 0.01  # (3.0 - 2.5) / 2.5 * 100
    assert r.trends[30] is None  # no data 30 days ago


def test_build_reports_skip_basics(db):
    for name in ["Lightning Bolt", "Swamp"]:
        card_id = db.upsert_card(Card(name=name, quantity=1))
        db.upsert_price(PriceEntry(
            card_id=card_id, price_usd=1.0, price_eur=1.0,
            set_code="M21", set_name="Core 2021", fetched_at=date(2026, 3, 15),
        ))
    reports = build_reports(db, days=[7], currency="usd", skip_basics=True, today=date(2026, 3, 15))
    names = [r.name for r in reports]
    assert "Swamp" not in names
    assert "Lightning Bolt" in names


def test_export_csv():
    reports = [
        CardReport(name="Sheoldred, the Apocalypse", quantity=1, price=72.5, set_code="ONE", trends={7: 3.2, 30: -1.8}),
        CardReport(name="Lightning Bolt", quantity=4, price=2.5, set_code="MH3", trends={7: None, 30: None}),
    ]
    output = export_csv(reports, days=[7, 30])
    reader = csv.DictReader(io.StringIO(output))
    rows = list(reader)
    assert len(rows) == 2
    assert rows[0]["name"] == "Sheoldred, the Apocalypse"
    assert rows[0]["trend_7d"] == "+3.2%"


def test_print_table_does_not_crash():
    """Smoke test: print_table should not raise on valid input."""
    from mtg_prices.report import print_table
    reports = [
        CardReport(name="Lightning Bolt", quantity=4, price=2.5, set_code="MH3", trends={7: 3.2, 30: None}),
    ]
    # Rich prints to console; just verify no exception
    print_table(reports, days=[7, 30], currency="usd")


def test_export_json():
    reports = [
        CardReport(name="Lightning Bolt", quantity=4, price=2.5, set_code="MH3", trends={7: 3.2, 30: None}),
    ]
    output = export_json(reports, days=[7, 30])
    data = json.loads(output)
    assert len(data) == 1
    assert data[0]["name"] == "Lightning Bolt"
    assert data[0]["trend_7d"] == 3.2
    assert data[0]["trend_30d"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_report.py -v`
Expected: FAIL

- [ ] **Step 3: Implement report module**

```python
# src/mtg_prices/report.py
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import date, timedelta

from rich.console import Console
from rich.table import Table

from mtg_prices.db import Database
from mtg_prices.models import CardReport

logger = logging.getLogger(__name__)

BASIC_LANDS = frozenset({
    "Plains", "Island", "Swamp", "Mountain", "Forest",
    "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
    "Snow-Covered Mountain", "Snow-Covered Forest", "Wastes",
})

CURRENCY_SYMBOLS = {"usd": "$", "eur": "€"}


def build_reports(
    db: Database,
    days: list[int],
    currency: str = "usd",
    skip_basics: bool = False,
    today: date | None = None,
) -> list[CardReport]:
    today = today or date.today()
    price_field = f"price_{currency}"
    cards = db.get_all_cards()
    reports: list[CardReport] = []

    for card in cards:
        if skip_basics and card.name in BASIC_LANDS:
            continue
        latest = db.get_latest_price(card.id)
        if latest is None:
            continue
        # Note: if latest fetch is older than today, trends are computed
        # relative to that date, not today. This is intentional — we can't
        # invent a price. Log a warning so the user knows data may be stale.
        if latest.fetched_at != today:
            logger.info(
                "Latest price for %r is from %s, not today",
                card.name, latest.fetched_at.isoformat(),
            )
        current_price = getattr(latest, price_field)
        if current_price is None:
            logger.warning("No %s price for %r", currency.upper(), card.name)
            continue

        trends: dict[int, float | None] = {}
        for d in days:
            target = today - timedelta(days=d)
            old = db.get_price_at(card.id, target, tolerance_days=2)
            if old is None:
                trends[d] = None
                continue
            old_price = getattr(old, price_field)
            if old_price is None or old_price == 0:
                trends[d] = None
                continue
            trends[d] = (current_price - old_price) / old_price * 100

        reports.append(CardReport(
            name=card.name,
            quantity=card.quantity,
            price=current_price,
            set_code=latest.set_code,
            trends=trends,
        ))

    reports.sort(key=lambda r: r.price or 0, reverse=True)
    return reports


def print_table(reports: list[CardReport], days: list[int], currency: str = "usd") -> None:
    symbol = CURRENCY_SYMBOLS.get(currency, "$")
    console = Console()
    table = Table(show_footer=True)

    table.add_column("Qté", justify="right", footer="")
    table.add_column("Carte", footer="TOTAL")
    table.add_column("Prix", justify="right", footer="")
    table.add_column("Ext", justify="center")
    for d in days:
        table.add_column(f"{d}j", justify="right")

    total_price = 0.0
    total_qty = 0
    for r in reports:
        total_price += (r.price or 0) * r.quantity
        total_qty += r.quantity
        trend_cols = []
        for d in days:
            t = r.trends.get(d)
            if t is None:
                trend_cols.append("—")
            elif t >= 0:
                trend_cols.append(f"[green]+{t:.1f}%[/green]")
            else:
                trend_cols.append(f"[red]{t:.1f}%[/red]")

        table.add_row(
            str(r.quantity),
            r.name,
            f"{symbol}{r.price:.2f}" if r.price else "—",
            r.set_code.upper(),
            *trend_cols,
        )

    # Update footer
    table.columns[0].footer = str(total_qty)
    table.columns[2].footer = f"{symbol}{total_price:.2f}"

    console.print(table)


def export_csv(reports: list[CardReport], days: list[int]) -> str:
    output = io.StringIO()
    fieldnames = ["qty", "name", "price", "set_code"]
    for d in days:
        fieldnames.append(f"trend_{d}d")
    writer = csv.DictWriter(output, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
    writer.writeheader()
    for r in reports:
        row = {
            "qty": r.quantity,
            "name": r.name,
            "price": r.price,
            "set_code": r.set_code,
        }
        for d in days:
            t = r.trends.get(d)
            row[f"trend_{d}d"] = f"+{t:.1f}%" if t and t >= 0 else f"{t:.1f}%" if t else "—"
        writer.writerow(row)
    return output.getvalue()


def export_json(reports: list[CardReport], days: list[int]) -> str:
    data = []
    for r in reports:
        entry = {
            "qty": r.quantity,
            "name": r.name,
            "price": r.price,
            "set_code": r.set_code,
        }
        for d in days:
            entry[f"trend_{d}d"] = r.trends.get(d)
        data.append(entry)
    return json.dumps(data, indent=2, ensure_ascii=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/mtg_prices/report.py tests/test_report.py
git commit -m "feat: add report module with console, CSV, and JSON export"
```

---

### Task 7: CLI

**Files:**
- Create: `src/mtg_prices/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write tests for CLI commands**

```python
# tests/test_cli.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from mtg_prices.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sample_decklist(tmp_path):
    f = tmp_path / "cards.txt"
    f.write_text("4 Lightning Bolt\n1 Counterspell\n")
    return f


def test_version(runner):
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_fetch_creates_db(runner, sample_decklist, tmp_path):
    db_path = tmp_path / "test.db"
    with patch("mtg_prices.cli._get_db_path", return_value=db_path):
        mock_client = MagicMock()
        mock_client.search_card.return_value = {
            "price_usd": 2.5, "price_eur": 2.0,
            "set_code": "MH3", "set_name": "Modern Horizons 3",
            "oracle_id": "abc-123",
        }
        with patch("mtg_prices.cli.ScryfallClient", return_value=mock_client):
            result = runner.invoke(main, ["fetch", str(sample_decklist)])
    assert result.exit_code == 0
    assert db_path.exists()


def test_list_empty(runner, tmp_path):
    db_path = tmp_path / "test.db"
    with patch("mtg_prices.cli._get_db_path", return_value=db_path):
        result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL

- [ ] **Step 3: Implement CLI**

```python
# src/mtg_prices/cli.py
from __future__ import annotations

import logging
import logging.handlers
from datetime import date
from pathlib import Path

import click
from rich.console import Console

from mtg_prices import __version__
from mtg_prices.db import Database
from mtg_prices.models import PriceEntry
from mtg_prices.parser import parse_decklist
from mtg_prices.report import build_reports, export_csv, export_json, print_table
from mtg_prices.scraper import ScryfallClient

def _default_data_dir() -> Path:
    """Data dir: $XDG_DATA_HOME/mtg-prices or ~/.local/share/mtg-prices."""
    import os
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        base = Path(xdg)
    else:
        base = Path.home() / ".local" / "share"
    return base / "mtg-prices"


console = Console()


def _get_db_path() -> Path:
    data_dir = _default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "mtg_prices.db"


def _setup_logging() -> None:
    data_dir = _default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        data_dir / "errors.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler.setFormatter(fmt)
    console_handler.setFormatter(fmt)
    root = logging.getLogger("mtg_prices")
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """MTG card price tracker using Scryfall API."""
    _setup_logging()


@main.command()
@click.argument("decklist", type=click.Path(exists=True, path_type=Path))
def fetch(decklist: Path) -> None:
    """Fetch prices from Scryfall for cards in DECKLIST file."""
    cards = parse_decklist(decklist)
    if not cards:
        console.print("[yellow]No cards found in file.[/yellow]")
        return

    db = Database(_get_db_path())
    db.init()
    client = ScryfallClient()

    today = date.today()
    fetched = 0
    errors = 0

    try:
        for card in cards:
            result = client.search_card(card.name)
            if result is None:
                errors += 1
                continue

            card.oracle_id = result.get("oracle_id")
            card_id = db.upsert_card(card)

            entry = PriceEntry(
                card_id=card_id,
                price_usd=result.get("price_usd"),
                price_eur=result.get("price_eur"),
                set_code=result["set_code"],
                set_name=result["set_name"],
                fetched_at=today,
            )
            db.upsert_price(entry)
            fetched += 1
            console.print(f"  [green]✓[/green] {card.name} — ${result.get('price_usd', '?')}")
    finally:
        client.close()
        db.close()

    console.print(f"\n[bold]Fetched {fetched} cards, {errors} errors.[/bold]")


@main.command()
@click.option("--format", "fmt", type=click.Choice(["csv", "json"]), default=None)
@click.option("--output", "output_path", type=click.Path(path_type=Path), default=None)
@click.option("--currency", type=click.Choice(["usd", "eur"]), default="usd")
@click.option("--days", default="7,30", help="Trend windows, comma-separated (e.g. 7,30,90)")
@click.option("--skip-basics", is_flag=True, default=False, help="Exclude basic lands")
def report(
    fmt: str | None,
    output_path: Path | None,
    currency: str,
    days: str,
    skip_basics: bool,
) -> None:
    """Show price trends for tracked cards."""
    day_list = [int(d.strip()) for d in days.split(",")]

    db = Database(_get_db_path())
    db.init()

    try:
        reports = build_reports(db, days=day_list, currency=currency, skip_basics=skip_basics)
        if not reports:
            console.print("[yellow]No price data available. Run 'fetch' first.[/yellow]")
            return

        print_table(reports, days=day_list, currency=currency)

        if fmt:
            if fmt == "csv":
                content = export_csv(reports, days=day_list)
            else:
                content = export_json(reports, days=day_list)

            if output_path is None:
                today = date.today().isoformat()
                data_dir = _default_data_dir()
                data_dir.mkdir(parents=True, exist_ok=True)
                output_path = data_dir / f"export_{today}.{fmt}"

            output_path.write_text(content, encoding="utf-8")
            console.print(f"\n[bold]Exported to {output_path}[/bold]")
    finally:
        db.close()


@main.command(name="list")
def list_cards() -> None:
    """List all tracked cards in the database."""
    db = Database(_get_db_path())
    db.init()

    try:
        cards = db.get_all_cards()
        if not cards:
            console.print("[yellow]No cards tracked yet. Run 'fetch' first.[/yellow]")
            return
        for card in cards:
            console.print(f"  {card.quantity}x {card.name}")
        console.print(f"\n[bold]{len(cards)} cards tracked.[/bold]")
    finally:
        db.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/mtg_prices/cli.py tests/test_cli.py
git commit -m "feat: add CLI with fetch, report, and list commands"
```

---

### Task 8: Integration test + final wiring

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Verify package installs and runs**

Run: `pip install -e . && mtg-prices --version`
Expected: `0.1.0`

- [ ] **Step 2: Run full test suite with coverage**

Run: `pytest -v --tb=short`
Expected: All PASS

- [ ] **Step 3: Test fetch with real Scryfall (manual smoke test)**

**Note:** This step hits the real Scryfall API. Skip in CI. For local verification only.

Create a test file:
```bash
echo "1 Lightning Bolt" > /tmp/test_cards.txt
mtg-prices fetch /tmp/test_cards.txt
mtg-prices list
mtg-prices report
```

Expected: price fetched, card listed, report shows price with `—` for trends (first fetch).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: final wiring and integration verification"
```
