# mtg-prices

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/tobiasdotrip/mtg-prices/actions/workflows/ci.yml/badge.svg)](https://github.com/tobiasdotrip/mtg-prices/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Scryfall API](https://img.shields.io/badge/data-Scryfall%20API-orange.svg)](https://scryfall.com/docs/api)
[![SQLite](https://img.shields.io/badge/storage-SQLite-003B57.svg)](https://www.sqlite.org/)

CLI tool to track Magic: The Gathering card prices over time using the [Scryfall API](https://scryfall.com/docs/api).

Feed it a decklist, run it daily, and get price trends for your collection.

```
┌─────┬───────────────────────────┬─────────┬─────┬────────┬────────┬────────┐
│ Qty │ Card                      │   Price │ Set │     1d │     7d │    30d │
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
- **Budget suggestions** — find cheaper alternatives for expensive cards, with role-based scoring
- **Deck management** — track multiple decks independently, shared price data
- **Deck formats** — commander, standard, modern, pioneer, pauper, legacy, vintage
- **Export** to CSV or JSON
- **Skip basics** — filter out basic lands from reports
- **USD & EUR** pricing support
- **SQLite storage** — single file, zero config, automatic schema migrations

## Installation

Requires Python 3.12 or newer.

```bash
git clone https://github.com/tobiasdotrip/mtg-prices.git
cd mtg-prices
python -m pip install .
mtg-prices --version
```

## Quickstart

Create a `cards.txt` decklist using the format below, then run:

```bash
mtg-prices fetch cards.txt --deck "My Deck" --format commander
mtg-prices report --deck "My Deck"
mtg-prices suggest "My Deck"
mtg-prices update --deck "My Deck"
```

The first fetch downloads Scryfall's bulk card data and may take a moment.

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
mtg-prices fetch cards.txt

# Associate with a named deck
mtg-prices fetch cards.txt --deck "Vito EDH"

# Specify a format (default: commander)
mtg-prices fetch cards.txt --deck "Vito EDH" --format commander
```

### Update prices

```bash
# Update all tracked cards
mtg-prices update

# Update a specific deck only
mtg-prices update --deck "Vito EDH"
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
mtg-prices report

# Report for a specific deck
mtg-prices report --deck "Vito EDH"

# EUR prices, custom trend windows
mtg-prices report --currency eur --days 1,7,30,90

# Skip basic lands
mtg-prices report --skip-basics

# Export
mtg-prices report --format csv --output prices.csv
mtg-prices report --format json
```

### Budget suggestions

```bash
# Suggest cheaper alternatives for cards above $10
mtg-prices suggest "Vito EDH"

# Custom threshold
mtg-prices suggest "Vito EDH" --above 20.00

# Top 5 most expensive only, max 3 suggestions each
mtg-prices suggest "Vito EDH" --top 5 --max-suggestions 3

# Include lands (excluded by default)
mtg-prices suggest "Vito EDH" --include-lands
```

Suggestions are scored by functional role, oracle text similarity, CMC, keywords, EDHREC popularity, and power/toughness. Accept swaps interactively by entering suggestion numbers, `all`, or Enter to skip.

### Manage decks

```bash
# List all decks
mtg-prices decks

# List cards in a deck
mtg-prices list --deck "Vito EDH"
```

### Automate with cron

Scryfall updates prices once daily. Schedule an update:

```bash
# Find the absolute path to the installed command
command -v mtg-prices

# crontab -e
30 9 * * * /absolute/path/to/mtg-prices update
```

### Data and logs

Application data is stored in `$XDG_DATA_HOME/mtg-prices` when
`XDG_DATA_HOME` is set, or in `~/.local/share/mtg-prices` otherwise. This
directory contains the SQLite database, the cached Scryfall bulk data,
`errors.log`, and exports created without an explicit `--output` path.

Back up `mtg_prices.db` to preserve deck and price history.

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
  cli.py        # Click CLI (fetch, update, report, suggest, list, decks)
  scraper.py    # Scryfall client, bulk data indexing, rate limiting
  suggest.py    # Budget swap scoring engine (roles, oracle text, CMC, keywords)
  db.py         # SQLite layer with automatic schema migrations
  report.py     # Rich table, CSV/JSON export
  parser.py     # Decklist file parser
  models.py     # Dataclasses (Card, Deck, PriceEntry, Suggestion, CardReport)
  migrations/   # Numbered SQL migration files
```

## Development

```bash
git clone https://github.com/tobiasdotrip/mtg-prices.git
cd mtg-prices
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

ruff check .
ruff format --check .
pytest -v
python -m build
```

## Built with

- [Click](https://click.palletsprojects.com/) — CLI framework
- [httpx](https://www.python-httpx.org/) — HTTP client
- [Rich](https://rich.readthedocs.io/) — Terminal formatting
- [Scryfall](https://scryfall.com/docs/api) — MTG price data
