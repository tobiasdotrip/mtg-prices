from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from mtg_prices.cli import main
from mtg_prices.db import Database
from mtg_prices.models import Card


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
    assert "0.4.1" in result.output


def test_fetch_creates_db(runner, sample_decklist, tmp_path):
    db_path = tmp_path / "test.db"
    with patch("mtg_prices.cli._get_db_path", return_value=db_path):
        mock_client = MagicMock()
        mock_client.search_card.return_value = {
            "price_usd": 2.5,
            "price_eur": 2.0,
            "set_code": "MH3",
            "set_name": "Modern Horizons 3",
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


@pytest.mark.parametrize(
    "args",
    [
        ["update", "--deck", "Missing"],
        ["report", "--deck", "Missing"],
        ["list", "--deck", "Missing"],
    ],
)
def test_missing_deck_returns_nonzero(runner, tmp_path, args):
    with patch("mtg_prices.cli._get_db_path", return_value=tmp_path / "test.db"):
        result = runner.invoke(main, args)

    assert result.exit_code == 1
    assert "Deck 'Missing' not found" in result.output


def test_fetch_partial_failure_preserves_existing_deck(runner, tmp_path):
    db_path = tmp_path / "test.db"
    decklist = tmp_path / "cards.txt"
    decklist.write_text("1 Keep Me\n1 Fails Temporarily\n")

    db = Database(db_path)
    db.init()
    deck_id = db.upsert_deck("Existing", deck_format="modern")
    for name in ("Keep Me", "Fails Temporarily"):
        card_id = db.upsert_card(Card(name=name))
        db.add_card_to_deck(deck_id, card_id, 1)
    db.close()

    mock_client = MagicMock()
    mock_client.search_card.side_effect = [
        {
            "price_usd": 2.5,
            "price_eur": 2.0,
            "set_code": "MH3",
            "set_name": "Modern Horizons 3",
            "oracle_id": "abc-123",
        },
        None,
    ]
    with (
        patch("mtg_prices.cli._get_db_path", return_value=db_path),
        patch("mtg_prices.cli._default_data_dir", return_value=tmp_path),
        patch("mtg_prices.cli.ScryfallClient", return_value=mock_client),
    ):
        result = runner.invoke(
            main,
            ["fetch", str(decklist), "--deck", "Existing", "--format", "standard"],
        )

    assert result.exit_code == 1
    assert "existing deck was preserved" in result.output
    db = Database(db_path)
    db.init()
    deck = db.get_deck_by_name("Existing")
    assert deck.format == "modern"
    assert {card.name for card in db.get_deck_cards(deck.id)} == {
        "Keep Me",
        "Fails Temporarily",
    }
    db.close()


def test_successful_fetch_replaces_deck_and_clears_cache(runner, tmp_path):
    db_path = tmp_path / "test.db"
    decklist = tmp_path / "cards.txt"
    decklist.write_text("2 New Card\n")

    db = Database(db_path)
    db.init()
    deck_id = db.upsert_deck("Existing")
    old_card_id = db.upsert_card(Card(name="Old Card"))
    db.add_card_to_deck(deck_id, old_card_id, 1)
    db.put_suggest_cache(deck_id, old_card_id, 10.0, "[]")
    db.close()

    mock_client = MagicMock()
    mock_client.search_card.return_value = {
        "price_usd": 1.0,
        "price_eur": 0.8,
        "set_code": "TST",
        "set_name": "Test Set",
        "oracle_id": "new-card",
    }
    with (
        patch("mtg_prices.cli._get_db_path", return_value=db_path),
        patch("mtg_prices.cli._default_data_dir", return_value=tmp_path),
        patch("mtg_prices.cli.ScryfallClient", return_value=mock_client),
    ):
        result = runner.invoke(main, ["fetch", str(decklist), "--deck", "Existing"])

    assert result.exit_code == 0
    db = Database(db_path)
    db.init()
    deck = db.get_deck_by_name("Existing")
    cards = db.get_deck_cards(deck.id)
    assert [(card.name, card.quantity) for card in cards] == [("New Card", 2)]
    assert db.get_suggest_cache(deck.id, old_card_id, 10.0) is None
    db.close()


@pytest.mark.parametrize(
    "args",
    [
        ["report", "--days", "1,nope,30"],
        ["report", "--days", "0"],
        ["suggest", "Deck", "--above", "-1"],
        ["suggest", "Deck", "--top", "0"],
        ["suggest", "Deck", "--max-suggestions", "0"],
        ["suggest", "Deck", "--max-suggestions", "21"],
    ],
)
def test_cli_rejects_invalid_numeric_options_without_traceback(runner, tmp_path, args):
    with patch("mtg_prices.cli._default_data_dir", return_value=tmp_path):
        result = runner.invoke(main, args)

    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert "Traceback" not in result.output
