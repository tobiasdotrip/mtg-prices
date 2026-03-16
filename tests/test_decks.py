from datetime import date

from mtg_prices.models import Card, PriceEntry
from mtg_prices.report import build_reports


def test_upsert_deck(db):
    deck_id = db.upsert_deck("Vito EDH")
    assert deck_id > 0


def test_upsert_deck_idempotent(db):
    id1 = db.upsert_deck("Vito EDH")
    id2 = db.upsert_deck("Vito EDH")
    assert id1 == id2


def test_add_card_to_deck(db):
    deck_id = db.upsert_deck("Vito EDH")
    card_id = db.upsert_card(Card(name="Lightning Bolt", quantity=4))
    db.add_card_to_deck(deck_id, card_id, 4)
    cards = db.get_deck_cards(deck_id)
    assert len(cards) == 1
    assert cards[0].name == "Lightning Bolt"
    assert cards[0].quantity == 4


def test_add_card_to_deck_update_quantity(db):
    deck_id = db.upsert_deck("Vito EDH")
    card_id = db.upsert_card(Card(name="Lightning Bolt", quantity=4))
    db.add_card_to_deck(deck_id, card_id, 4)
    db.add_card_to_deck(deck_id, card_id, 2)
    cards = db.get_deck_cards(deck_id)
    assert cards[0].quantity == 2


def test_get_all_decks(db):
    db.upsert_deck("Deck A")
    db.upsert_deck("Deck B")
    decks = db.get_all_decks()
    assert len(decks) == 2
    assert decks[0].name == "Deck A"
    assert decks[1].name == "Deck B"


def test_get_deck_by_name(db):
    db.upsert_deck("Vito EDH")
    deck = db.get_deck_by_name("Vito EDH")
    assert deck is not None
    assert deck.name == "Vito EDH"


def test_get_deck_by_name_not_found(db):
    deck = db.get_deck_by_name("Nonexistent")
    assert deck is None


def test_shared_prices_across_decks(db):
    """A card in multiple decks shares the same price data."""
    card_id = db.upsert_card(Card(name="Sol Ring", quantity=1))
    db.upsert_price(
        PriceEntry(
            card_id=card_id,
            price_usd=1.0,
            price_eur=0.8,
            set_code="CMR",
            set_name="Commander",
            fetched_at=date(2026, 3, 15),
        )
    )
    deck_a = db.upsert_deck("Deck A")
    deck_b = db.upsert_deck("Deck B")
    db.add_card_to_deck(deck_a, card_id, 1)
    db.add_card_to_deck(deck_b, card_id, 1)

    cards_a = db.get_deck_cards(deck_a)
    cards_b = db.get_deck_cards(deck_b)
    price_a = db.get_latest_price(cards_a[0].id)
    price_b = db.get_latest_price(cards_b[0].id)
    assert price_a.price_usd == price_b.price_usd


def test_build_reports_with_card_list(db):
    """build_reports accepts a card_list to filter by deck."""
    for name in ["Lightning Bolt", "Counterspell", "Sol Ring"]:
        card_id = db.upsert_card(Card(name=name, quantity=1))
        db.upsert_price(
            PriceEntry(
                card_id=card_id,
                price_usd=2.0,
                price_eur=1.5,
                set_code="SET",
                set_name="Set",
                fetched_at=date(2026, 3, 15),
            )
        )

    deck_id = db.upsert_deck("Test Deck")
    bolt_id = db.conn.execute(
        "SELECT id FROM cards WHERE name = 'Lightning Bolt'"
    ).fetchone()[0]
    db.add_card_to_deck(deck_id, bolt_id, 4)

    deck_cards = db.get_deck_cards(deck_id)
    reports = build_reports(
        db,
        days=[7],
        currency="usd",
        card_list=deck_cards,
        today=date(2026, 3, 15),
    )
    assert len(reports) == 1
    assert reports[0].name == "Lightning Bolt"
    assert reports[0].quantity == 4
