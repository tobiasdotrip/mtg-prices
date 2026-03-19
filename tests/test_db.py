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
    row = db.conn.execute(
        "SELECT price_usd FROM prices WHERE card_id = ?", (card_id,)
    ).fetchone()
    assert row[0] == 2.50


def test_upsert_price_same_day(db):
    card = Card(name="Lightning Bolt", quantity=4)
    card_id = db.upsert_card(card)
    entry1 = PriceEntry(
        card_id=card_id,
        price_usd=2.50,
        price_eur=2.10,
        set_code="MH3",
        set_name="Modern Horizons 3",
        fetched_at=date(2026, 3, 15),
    )
    entry2 = PriceEntry(
        card_id=card_id,
        price_usd=3.00,
        price_eur=2.50,
        set_code="MH3",
        set_name="Modern Horizons 3",
        fetched_at=date(2026, 3, 15),
    )
    db.upsert_price(entry1)
    db.upsert_price(entry2)
    rows = db.conn.execute(
        "SELECT price_usd FROM prices WHERE card_id = ?", (card_id,)
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 3.00


def test_get_price_at_date(db):
    card = Card(name="Lightning Bolt", quantity=4)
    card_id = db.upsert_card(card)
    entry = PriceEntry(
        card_id=card_id,
        price_usd=2.50,
        price_eur=2.10,
        set_code="MH3",
        set_name="Modern Horizons 3",
        fetched_at=date(2026, 3, 10),
    )
    db.upsert_price(entry)
    price = db.get_price_at(card_id, date(2026, 3, 10), tolerance_days=2)
    assert price is not None
    assert price.price_usd == 2.50


def test_get_price_at_date_with_tolerance(db):
    card = Card(name="Lightning Bolt", quantity=4)
    card_id = db.upsert_card(card)
    entry = PriceEntry(
        card_id=card_id,
        price_usd=2.50,
        price_eur=2.10,
        set_code="MH3",
        set_name="Modern Horizons 3",
        fetched_at=date(2026, 3, 9),
    )
    db.upsert_price(entry)
    price = db.get_price_at(card_id, date(2026, 3, 10), tolerance_days=2)
    assert price is not None
    assert price.price_usd == 2.50


def test_get_price_at_date_out_of_tolerance(db):
    card = Card(name="Lightning Bolt", quantity=4)
    card_id = db.upsert_card(card)
    entry = PriceEntry(
        card_id=card_id,
        price_usd=2.50,
        price_eur=2.10,
        set_code="MH3",
        set_name="Modern Horizons 3",
        fetched_at=date(2026, 3, 5),
    )
    db.upsert_price(entry)
    price = db.get_price_at(card_id, date(2026, 3, 10), tolerance_days=2)
    assert price is None


def test_get_latest_price(db):
    card = Card(name="Lightning Bolt", quantity=4)
    card_id = db.upsert_card(card)
    for day, usd in [(10, 2.0), (12, 2.5), (14, 3.0)]:
        entry = PriceEntry(
            card_id=card_id,
            price_usd=usd,
            price_eur=None,
            set_code="MH3",
            set_name="Modern Horizons 3",
            fetched_at=date(2026, 3, day),
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
