import csv
import io
import json
from datetime import date

from mtg_prices.models import Card, CardReport, PriceEntry
from mtg_prices.report import (
    build_reports,
    export_csv,
    export_json,
    print_table,
)


def test_build_reports(db):
    card = Card(name="Lightning Bolt", quantity=4)
    card_id = db.upsert_card(card)
    db.upsert_price(
        PriceEntry(
            card_id=card_id,
            price_usd=3.0,
            price_eur=2.5,
            set_code="MH3",
            set_name="Modern Horizons 3",
            fetched_at=date(2026, 3, 15),
        )
    )
    db.upsert_price(
        PriceEntry(
            card_id=card_id,
            price_usd=2.5,
            price_eur=2.0,
            set_code="MH3",
            set_name="Modern Horizons 3",
            fetched_at=date(2026, 3, 8),
        )
    )
    reports = build_reports(
        db, days=[7, 30], currency="usd", today=date(2026, 3, 15)
    )
    assert len(reports) == 1
    r = reports[0]
    assert r.name == "Lightning Bolt"
    assert r.price_usd == 3.0
    assert r.price_eur == 2.5
    assert r.trends[7] is not None
    assert abs(r.trends[7] - 20.0) < 0.01  # (3.0 - 2.5) / 2.5 * 100
    assert r.trends[30] is None


def test_build_reports_null_currency_included(db):
    """Cards with null price in requested currency
    should appear with None, not be skipped."""
    card_id = db.upsert_card(Card(name="US Only Card", quantity=1))
    db.upsert_price(
        PriceEntry(
            card_id=card_id,
            price_usd=5.0,
            price_eur=None,
            set_code="SET",
            set_name="Some Set",
            fetched_at=date(2026, 3, 15),
        )
    )
    reports = build_reports(
        db, days=[7], currency="eur", today=date(2026, 3, 15)
    )
    assert len(reports) == 1
    assert reports[0].price_eur is None
    assert reports[0].trends[7] is None


def test_build_reports_skip_basics(db):
    for name in ["Lightning Bolt", "Swamp"]:
        card_id = db.upsert_card(Card(name=name, quantity=1))
        db.upsert_price(
            PriceEntry(
                card_id=card_id,
                price_usd=1.0,
                price_eur=1.0,
                set_code="M21",
                set_name="Core 2021",
                fetched_at=date(2026, 3, 15),
            )
        )
    reports = build_reports(
        db, days=[7], currency="usd", skip_basics=True, today=date(2026, 3, 15)
    )
    names = [r.name for r in reports]
    assert "Swamp" not in names
    assert "Lightning Bolt" in names


def test_export_csv():
    reports = [
        CardReport(
            name="Sheoldred, the Apocalypse",
            quantity=1,
            price_usd=72.5,
            price_eur=65.0,
            set_code="ONE",
            trends={7: 3.2, 30: -1.8},
        ),
        CardReport(
            name="Lightning Bolt",
            quantity=4,
            price_usd=2.5,
            price_eur=2.0,
            set_code="MH3",
            trends={7: None, 30: None},
        ),
    ]
    output = export_csv(reports, days=[7, 30])
    reader = csv.DictReader(io.StringIO(output))
    rows = list(reader)
    assert len(rows) == 2
    assert rows[0]["name"] == "Sheoldred, the Apocalypse"
    assert rows[0]["price_usd"] == "72.5"
    assert rows[0]["price_eur"] == "65.0"
    assert rows[0]["trend_7d"] == "+3.2%"


def test_export_csv_zero_trend():
    """A trend of exactly 0% should show +0.0%, not —."""
    reports = [
        CardReport(
            name="Bolt",
            quantity=1,
            price_usd=2.0,
            price_eur=None,
            set_code="M21",
            trends={7: 0.0},
        ),
    ]
    output = export_csv(reports, days=[7])
    assert "+0.0%" in output


def test_print_table_does_not_crash():
    reports = [
        CardReport(
            name="Lightning Bolt",
            quantity=4,
            price_usd=2.5,
            price_eur=2.0,
            set_code="MH3",
            trends={7: 3.2, 30: None},
        ),
    ]
    print_table(reports, days=[7, 30], currency="usd")


def test_export_json():
    reports = [
        CardReport(
            name="Lightning Bolt",
            quantity=4,
            price_usd=2.5,
            price_eur=2.0,
            set_code="MH3",
            trends={7: 3.2, 30: None},
        ),
    ]
    output = export_json(reports, days=[7, 30])
    data = json.loads(output)
    assert len(data) == 1
    assert data[0]["name"] == "Lightning Bolt"
    assert data[0]["price_usd"] == 2.5
    assert data[0]["price_eur"] == 2.0
    assert data[0]["trend_7d"] == 3.2
    assert data[0]["trend_30d"] is None
