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
        price_usd=2.50,
        price_eur=2.10,
        set_code="MH3",
        trends={7: 3.2, 30: -1.8},
    )
    assert report.trends[7] == 3.2
    assert report.trends[30] == -1.8


def test_card_report_no_trends():
    report = CardReport(
        name="Lightning Bolt",
        quantity=4,
        price_usd=2.50,
        price_eur=None,
        set_code="MH3",
        trends={7: None, 30: None},
    )
    assert report.trends[7] is None
