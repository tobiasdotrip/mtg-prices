from datetime import date
from unittest.mock import MagicMock, patch

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
    assert result.exit_code == 0
    assert "not found" in result.output


@patch("mtg_prices.cli._get_db_path")
@patch("mtg_prices.cli._default_data_dir")
@patch("mtg_prices.cli.ScryfallClient")
def test_suggest_no_expensive_cards(mock_client_cls, mock_data_dir, mock_db_path, tmp_path):
    db_path = tmp_path / "test.db"
    mock_db_path.return_value = str(db_path)
    mock_data_dir.return_value = tmp_path

    db = Database(str(db_path))
    db.init()
    deck_id = db.upsert_deck("Test Deck")
    card_id = db.upsert_card(Card(name="Cheap Card"))
    db.add_card_to_deck(deck_id, card_id, 1)
    db.upsert_price(PriceEntry(
        card_id=card_id, price_usd=1.00, price_eur=0.80,
        set_code="test", set_name="Test Set", fetched_at=date.today(),
    ))
    db.close()

    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client._bulk_type_index = {"Creature": []}
    mock_client._bulk_index = {}

    runner = CliRunner()
    result = runner.invoke(main, ["suggest", "Test Deck"])
    assert result.exit_code == 0
    assert "No cards above" in result.output
