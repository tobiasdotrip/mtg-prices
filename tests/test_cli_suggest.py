from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from mtg_prices.cli import main
from mtg_prices.db import Database
from mtg_prices.models import Card, PriceEntry


@patch("mtg_prices.cli.ScryfallClient")
@patch("mtg_prices.cli._get_db_path")
def test_suggest_deck_not_found(mock_db_path, mock_client, tmp_path):
    db_path = tmp_path / "test.db"
    mock_db_path.return_value = str(db_path)
    runner = CliRunner()
    result = runner.invoke(main, ["suggest", "Nonexistent Deck"])
    assert result.exit_code == 1
    assert "not found" in result.output


@patch("mtg_prices.cli._get_db_path")
@patch("mtg_prices.cli._default_data_dir")
@patch("mtg_prices.cli.ScryfallClient")
def test_suggest_no_expensive_cards(
    mock_client_cls, mock_data_dir, mock_db_path, tmp_path
):
    db_path = tmp_path / "test.db"
    mock_db_path.return_value = str(db_path)
    mock_data_dir.return_value = tmp_path

    db = Database(str(db_path))
    db.init()
    deck_id = db.upsert_deck("Test Deck")
    card_id = db.upsert_card(Card(name="Cheap Card"))
    db.add_card_to_deck(deck_id, card_id, 1)
    db.upsert_price(
        PriceEntry(
            card_id=card_id,
            price_usd=1.00,
            price_eur=0.80,
            set_code="test",
            set_name="Test Set",
            fetched_at=date.today(),
        )
    )
    db.close()

    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client._bulk_type_index = {"Creature": []}
    mock_client._bulk_index = {}

    runner = CliRunner()
    result = runner.invoke(main, ["suggest", "Test Deck"])
    assert result.exit_code == 0
    assert "No cards above" in result.output


def test_suggest_uses_same_reference_print_as_fetch(tmp_path):
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    db.init()
    deck_id = db.upsert_deck("Test Deck")
    card_id = db.upsert_card(Card(name="Original"))
    db.add_card_to_deck(deck_id, card_id, 1)
    db.upsert_price(
        PriceEntry(
            card_id=card_id,
            price_usd=10.0,
            price_eur=None,
            set_code="old",
            set_name="Old Set",
            fetched_at=date.today(),
        )
    )
    db.close()

    prints = [
        {
            "name": "Original",
            "type_line": "Creature",
            "color_identity": [],
            "prices": {"usd": "50.00"},
            "set": "new",
            "set_name": "New Set",
            "oracle_id": "original",
            "released_at": "2026-02-01",
        },
        {
            "name": "Original",
            "type_line": "Creature",
            "color_identity": [],
            "prices": {"usd": "10.00"},
            "set": "old",
            "set_name": "Old Set",
            "oracle_id": "original",
            "released_at": "2026-01-01",
        },
    ]
    candidate = {
        "name": "Not Actually Cheaper",
        "prices": {"usd": "20.00"},
        "legalities": {"commander": "legal"},
    }
    mock_client = MagicMock()
    mock_client._bulk_index = {"original": prints}
    mock_client._bulk_type_index = {"Creature": [candidate]}
    mock_client._extract_super_type.return_value = "Creature"
    mock_client.get_candidates.return_value = [candidate]

    with (
        patch("mtg_prices.cli._get_db_path", return_value=db_path),
        patch("mtg_prices.cli._default_data_dir", return_value=tmp_path),
        patch("mtg_prices.cli.ScryfallClient", return_value=mock_client),
    ):
        result = CliRunner().invoke(main, ["suggest", "Test Deck"])

    assert result.exit_code == 0
    assert "No suggestions" in result.output
    assert "Not Actually Cheaper" not in result.output


@pytest.mark.parametrize(
    ("choice", "warning_expected"),
    [("all", False), ("1,2", True)],
)
def test_suggest_accepts_only_one_replacement_per_card(
    tmp_path, choice, warning_expected
):
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    db.init()
    deck_id = db.upsert_deck("Test Deck")
    card_id = db.upsert_card(Card(name="Original"))
    db.add_card_to_deck(deck_id, card_id, 1)
    db.upsert_price(
        PriceEntry(
            card_id=card_id,
            price_usd=10.0,
            price_eur=None,
            set_code="set",
            set_name="Set",
            fetched_at=date.today(),
        )
    )
    db.close()

    original = {
        "name": "Original",
        "type_line": "Creature",
        "color_identity": [],
        "prices": {"usd": "10.00"},
        "set": "set",
        "set_name": "Set",
        "oracle_id": "original",
        "released_at": "2026-01-01",
    }
    candidates = [
        {
            "name": "Best Alternative",
            "prices": {"usd": "1.00"},
            "legalities": {"commander": "legal"},
        },
        {
            "name": "Second Alternative",
            "prices": {"usd": "2.00"},
            "legalities": {"commander": "legal"},
        },
    ]
    mock_client = MagicMock()
    mock_client._bulk_index = {"original": [original]}
    mock_client._bulk_type_index = {"Creature": candidates}
    mock_client._extract_super_type.return_value = "Creature"
    mock_client.get_candidates.return_value = candidates

    with (
        patch("mtg_prices.cli._get_db_path", return_value=db_path),
        patch("mtg_prices.cli._default_data_dir", return_value=tmp_path),
        patch("mtg_prices.cli.ScryfallClient", return_value=mock_client),
    ):
        result = CliRunner().invoke(main, ["suggest", "Test Deck"], input=f"{choice}\n")

    assert result.exit_code == 0
    assert "Total potential saving: $9.00" in result.output
    assert ("Only one suggestion can replace" in result.output) is warning_expected
    db = Database(db_path)
    db.init()
    deck = db.get_deck_by_name("Test Deck")
    assert [card.name for card in db.get_deck_cards(deck.id)] == ["Best Alternative"]
    db.close()
