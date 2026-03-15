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
