# mtg-prices

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Scryfall API](https://img.shields.io/badge/data-Scryfall%20API-orange.svg)](https://scryfall.com/docs/api)
[![SQLite](https://img.shields.io/badge/storage-SQLite-003B57.svg)](https://www.sqlite.org/)

CLI tool to track Magic: The Gathering card prices over time using the [Scryfall API](https://scryfall.com/docs/api).

Feed it a decklist, run it daily, and get price trends for your collection.

```
┌─────┬───────────────────────────┬─────────┬─────┬────────┬────────┬────────┐
│ Qte │ Carte                     │    Prix │ Ext │     1j │     7j │    30j │
├─────┼───────────────────────────┼─────────┼─────┼────────┼────────┼────────┤
│   1 │ Sheoldred, the Apocalypse │  $72.35 │ DMU │ +0.4%  │ +3.2%  │ -1.8%  │
│   1 │ Vampiric Tutor            │  $63.12 │ DMR │ -0.1%  │ +0.5%  │ +2.1%  │
│   1 │ Demonic Tutor             │  $52.58 │ CMM │ +0.9%  │ -1.0%  │ -4.3%  │
│  ...│                           │         │     │        │        │        │
├─────┼───────────────────────────┼─────────┼─────┼────────┼────────┼────────┤
│  78 │ TOTAL                     │ $752.26 │     │        │        │        │
└─────┴───────────────────────────┴─────────┴─────┴────────┴────────┴────────┘
```

## Features

- **Daily price tracking** via Scryfall bulk data (free, no API key)
- **Price deltas** — see price changes on each update
- **Price trends** over configurable windows (1d, 7d, 30d, or custom)
- **Deck management** — track multiple decks independently, shared price data
- **Export** to CSV or JSON
- **Skip basics** — filter out basic lands from reports
- **USD & EUR** pricing support
- **SQLite storage** — single file, zero config

## Installation

```bash
git clone https://github.com/tobiasdotrip/mtg-prices.git
cd mtg-prices
pip install -e ".[dev]"
```

## Usage

### Decklist format

One card per line: `<quantity> <card name>`

```
1 Sheoldred, the Apocalypse
4 Lightning Bolt
1 Demonic Tutor
23 Swamp
```

Lines starting with `#` are comments. Empty lines are ignored.

### Fetch prices

```bash
# Fetch prices for a decklist
python -m mtg_prices fetch cards.txt

# Associate with a named deck
python -m mtg_prices fetch cards.txt --deck "Vito EDH"
```

### Update prices

```bash
# Update all tracked cards
python -m mtg_prices update

# Update a specific deck only
python -m mtg_prices update --deck "Vito EDH"
```

Price deltas are shown for each card:

```
  OK Necropotence -- $30.98 → $32.56 (+1.58)
  OK Ink-Eyes, Servant of Oni -- $8.16 → $6.95 (-1.21)
  OK Arcane Signet -- $0.37
```

### View reports

```bash
# Report for all tracked cards
python -m mtg_prices report

# Report for a specific deck
python -m mtg_prices report --deck "Vito EDH"

# EUR prices, custom trend windows
python -m mtg_prices report --currency eur --days 1,7,30,90

# Skip basic lands
python -m mtg_prices report --skip-basics

# Export
python -m mtg_prices report --format csv --output prices.csv
python -m mtg_prices report --format json
```

### Manage decks

```bash
# List all decks
python -m mtg_prices decks

# List cards in a deck
python -m mtg_prices list --deck "Vito EDH"
```

### Automate with cron

Scryfall updates prices once daily. Schedule an update:

```bash
# crontab -e
30 9 * * * cd /path/to/mtg-prices && python -m mtg_prices update
```

## How it works

1. **Parses** the decklist file
2. **Downloads** Scryfall's bulk data (cached locally for 24h)
3. **Selects** the cheapest non-foil price among the 5 most recent editions
4. **Stores** prices in SQLite with daily granularity
5. **Computes** trends by comparing today's price to historical data

Card names are normalized (diacritics removed) before lookup. API fallback with fuzzy matching is used for cards not found in bulk data.

## Project structure

```
src/mtg_prices/
  cli.py        # Click CLI (fetch, report, list, decks)
  scraper.py    # Scryfall client, rate limiting, price selection
  db.py         # SQLite layer (cards, prices, decks)
  report.py     # Rich table, CSV/JSON export
  parser.py     # Decklist file parser
  models.py     # Dataclasses (Card, Deck, PriceEntry, CardReport)
```

## Running tests

```bash
pytest -v
```

## Built with

- [Click](https://click.palletsprojects.com/) — CLI framework
- [httpx](https://www.python-httpx.org/) — HTTP client
- [Rich](https://rich.readthedocs.io/) — Terminal formatting
- [Scryfall](https://scryfall.com/docs/api) — MTG price data
