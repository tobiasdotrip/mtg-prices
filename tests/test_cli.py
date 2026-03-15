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
