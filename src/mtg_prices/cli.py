from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from datetime import date
from pathlib import Path

import click
from rich.console import Console

from mtg_prices import __version__
from mtg_prices.db import Database
from mtg_prices.models import PriceEntry
from mtg_prices.parser import parse_decklist
from mtg_prices.report import (
    build_reports,
    export_csv,
    export_json,
    print_table,
)
from mtg_prices.scraper import ScryfallClient


def _default_data_dir() -> Path:
    """Data dir: $XDG_DATA_HOME/mtg-prices or ~/.local/share/mtg-prices."""
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "mtg-prices"


def _make_console() -> Console:
    """Create a Rich Console that works on Windows/PowerShell."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    return Console(force_terminal=True)


console = _make_console()


def _get_db_path() -> Path:
    data_dir = _default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "mtg_prices.db"


def _setup_logging() -> None:
    data_dir = _default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        data_dir / "errors.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    file_handler.setFormatter(fmt)
    console_handler.setFormatter(fmt)
    root = logging.getLogger("mtg_prices")
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """MTG card price tracker using Scryfall API."""
    _setup_logging()


@main.command()
@click.argument("decklist", type=click.Path(exists=True, path_type=Path))
@click.option("--deck", default=None, help="Associate cards with a named deck")
def fetch(decklist: Path, deck: str | None) -> None:
    """Fetch prices from Scryfall for cards in DECKLIST file."""
    cards = parse_decklist(decklist)
    if not cards:
        console.print("[yellow]No cards found in file.[/yellow]")
        return

    db = Database(_get_db_path())
    db.init()
    client = ScryfallClient()
    console.print("[dim]Loading Scryfall bulk data...[/dim]")
    client.load_bulk_data(_default_data_dir())

    deck_id = None
    if deck:
        deck_id = db.upsert_deck(deck)
        db.clear_deck(deck_id)
        console.print(f"[bold]Deck:[/bold] {deck}\n")

    today = date.today()
    fetched = 0
    errors = 0

    try:
        for card in cards:
            result = client.search_card(card.name)
            if result is None:
                errors += 1
                continue

            card.oracle_id = result.get("oracle_id")
            card_id = db.upsert_card(card)

            if deck_id is not None:
                db.add_card_to_deck(deck_id, card_id, card.quantity)

            entry = PriceEntry(
                card_id=card_id,
                price_usd=result.get("price_usd"),
                price_eur=result.get("price_eur"),
                set_code=result["set_code"],
                set_name=result["set_name"],
                fetched_at=today,
            )
            db.upsert_price(entry)
            fetched += 1
            console.print(
                f"  [green]OK[/green] {card.name} -- ${result.get('price_usd', '?')}"
            )
    finally:
        client.close()
        db.close()

    console.print(f"\n[bold]Fetched {fetched} cards, {errors} errors.[/bold]")


@main.command()
@click.option(
    "--deck", default=None, help="Update prices for a specific deck only"
)
def update(deck: str | None) -> None:
    """Re-fetch prices for all tracked cards (or a specific deck)."""
    db = Database(_get_db_path())
    db.init()

    try:
        if deck:
            deck_obj = db.get_deck_by_name(deck)
            if deck_obj is None:
                console.print(f"[red]Deck '{deck}' not found.[/red]")
                return
            cards = db.get_deck_cards(deck_obj.id)
            console.print(f"[bold]Deck:[/bold] {deck}\n")
        else:
            cards = db.get_all_cards()

        if not cards:
            console.print(
                "[yellow]No cards tracked yet. Run 'fetch' first.[/yellow]"
            )
            return

        client = ScryfallClient()
        console.print("[dim]Loading Scryfall bulk data...[/dim]")
        client.load_bulk_data(_default_data_dir())
        today = date.today()
        fetched = 0
        errors = 0

        try:
            for card in cards:
                result = client.search_card(card.name)
                if result is None:
                    errors += 1
                    continue

                card.oracle_id = result.get("oracle_id")
                db.upsert_card(card)

                old_price_entry = db.get_latest_price(card.id)

                entry = PriceEntry(
                    card_id=card.id,
                    price_usd=result.get("price_usd"),
                    price_eur=result.get("price_eur"),
                    set_code=result["set_code"],
                    set_name=result["set_name"],
                    fetched_at=today,
                )
                db.upsert_price(entry)
                fetched += 1

                new_usd = result.get("price_usd")
                old_usd = (
                    old_price_entry.price_usd if old_price_entry else None
                )
                if (
                    new_usd is not None
                    and old_usd is not None
                    and old_usd != new_usd
                ):
                    diff = new_usd - old_usd
                    sign = "+" if diff > 0 else ""
                    color = "green" if diff > 0 else "red"
                    console.print(
                        f"  [green]OK[/green] {card.name} -- "
                        f"${old_usd:.2f} → ${new_usd:.2f} "
                        f"[{color}]({sign}{diff:.2f})[/{color}]"
                    )
                else:
                    console.print(
                        f"  [green]OK[/green] {card.name} -- ${new_usd or '?'}"
                    )
        finally:
            client.close()

        console.print(
            f"\n[bold]Updated {fetched} cards, {errors} errors.[/bold]"
        )
    finally:
        db.close()


@main.command()
@click.option(
    "--format", "fmt", type=click.Choice(["csv", "json"]), default=None
)
@click.option(
    "--output", "output_path", type=click.Path(path_type=Path), default=None
)
@click.option("--currency", type=click.Choice(["usd", "eur"]), default="usd")
@click.option(
    "--days",
    default="1,7,30",
    help="Trend windows, comma-separated (e.g. 1,7,30,90)",
)
@click.option(
    "--skip-basics", is_flag=True, default=False, help="Exclude basic lands"
)
@click.option("--deck", default=None, help="Report for a specific deck only")
def report(
    fmt: str | None,
    output_path: Path | None,
    currency: str,
    days: str,
    skip_basics: bool,
    deck: str | None,
) -> None:
    """Show price trends for tracked cards."""
    day_list = [int(d.strip()) for d in days.split(",")]

    db = Database(_get_db_path())
    db.init()

    try:
        card_list = None
        if deck:
            deck_obj = db.get_deck_by_name(deck)
            if deck_obj is None:
                console.print(f"[red]Deck '{deck}' not found.[/red]")
                return
            card_list = db.get_deck_cards(deck_obj.id)

        reports = build_reports(
            db,
            days=day_list,
            currency=currency,
            skip_basics=skip_basics,
            card_list=card_list,
        )
        if not reports:
            console.print(
                "[yellow]No price data available. Run 'fetch' first.[/yellow]"
            )
            return

        title = f"Deck: {deck}" if deck else None
        print_table(reports, days=day_list, currency=currency, title=title)

        if fmt:
            if fmt == "csv":
                content = export_csv(reports, days=day_list)
            else:
                content = export_json(reports, days=day_list)

            if output_path is None:
                today = date.today().isoformat()
                data_dir = _default_data_dir()
                data_dir.mkdir(parents=True, exist_ok=True)
                output_path = data_dir / f"export_{today}.{fmt}"

            output_path.write_text(content, encoding="utf-8")
            console.print(f"\n[bold]Exported to {output_path}[/bold]")
    finally:
        db.close()


@main.command(name="list")
@click.option("--deck", default=None, help="List cards in a specific deck")
def list_cards(deck: str | None) -> None:
    """List all tracked cards in the database."""
    db = Database(_get_db_path())
    db.init()

    try:
        if deck:
            deck_obj = db.get_deck_by_name(deck)
            if deck_obj is None:
                console.print(f"[red]Deck '{deck}' not found.[/red]")
                return
            cards = db.get_deck_cards(deck_obj.id)
            label = f"Deck: {deck}"
        else:
            cards = db.get_all_cards()
            label = "All cards"

        if not cards:
            console.print(
                "[yellow]No cards tracked yet. Run 'fetch' first.[/yellow]"
            )
            return
        console.print(f"[bold]{label}[/bold]\n")
        for card in cards:
            console.print(f"  {card.quantity}x {card.name}")
        console.print(f"\n[bold]{len(cards)} cards.[/bold]")
    finally:
        db.close()


@main.command()
def decks() -> None:
    """List all tracked decks."""
    db = Database(_get_db_path())
    db.init()

    try:
        all_decks = db.get_all_decks()
        if not all_decks:
            console.print(
                "[yellow]No decks yet. Use "
                "'fetch --deck <name>' to create one.[/yellow]"
            )
            return
        for d in all_decks:
            card_count = len(db.get_deck_cards(d.id))
            console.print(f"  {d.name} ({card_count} cards)")
        console.print(f"\n[bold]{len(all_decks)} decks.[/bold]")
    finally:
        db.close()
