from __future__ import annotations

import dataclasses
import json
import logging
import logging.handlers
import os
import sys
from datetime import date
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from mtg_prices import __version__
from mtg_prices.db import Database
from mtg_prices.models import Card, PriceEntry, Suggestion
from mtg_prices.parser import parse_decklist
from mtg_prices.report import (
    build_reports,
    export_csv,
    export_json,
    print_table,
)
from mtg_prices.scraper import ScryfallClient, normalize_name, select_best_price


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
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler.setFormatter(fmt)
    console_handler.setFormatter(fmt)
    root = logging.getLogger("mtg_prices")
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)


def _parse_days(value: str) -> list[int]:
    try:
        days = [int(day.strip()) for day in value.split(",")]
    except ValueError as exc:
        raise click.BadParameter(
            "must be a comma-separated list of positive integers",
            param_hint="--days",
        ) from exc
    if not days or any(day < 1 for day in days):
        raise click.BadParameter(
            "must be a comma-separated list of positive integers",
            param_hint="--days",
        )
    return days


def _select_reference_print(prints: list[dict]) -> dict | None:
    selected = select_best_price(prints)
    if selected is None:
        return None
    return next(
        (
            card
            for card in prints[:5]
            if card.get("set") == selected["set_code"]
            and card.get("prices", {}).get("usd") is not None
            and float(card["prices"]["usd"]) == selected["price_usd"]
        ),
        None,
    )


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """MTG card price tracker using Scryfall API."""
    _setup_logging()


@main.command()
@click.argument("decklist", type=click.Path(exists=True, path_type=Path))
@click.option("--deck", default=None, help="Associate cards with a named deck")
@click.option(
    "--format",
    "deck_format",
    default="commander",
    type=click.Choice(
        ["commander", "standard", "modern", "pioneer", "pauper", "legacy", "vintage"],
        case_sensitive=False,
    ),
    help="Deck format for legality checks (default: commander)",
)
def fetch(decklist: Path, deck: str | None, deck_format: str) -> None:
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

    resolved_deck_cards: list[tuple[int, int]] = []
    if deck:
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

            if deck:
                resolved_deck_cards.append((card_id, card.quantity))

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

        if errors == 0 and deck:
            deck_id = db.upsert_deck(deck, deck_format=deck_format)
            if deck_id is not None:
                db.replace_deck_cards(deck_id, resolved_deck_cards)
        if fetched > 0:
            db.clear_suggest_cache()
    finally:
        client.close()
        db.close()

    console.print(f"\n[bold]Fetched {fetched} cards, {errors} errors.[/bold]")
    if errors:
        message = "Fetch incomplete because not every card could be resolved."
        if deck:
            message += " The existing deck was preserved."
        raise click.ClickException(message)


@main.command()
@click.option("--deck", default=None, help="Update prices for a specific deck only")
def update(deck: str | None) -> None:
    """Re-fetch prices for all tracked cards (or a specific deck)."""
    db = Database(_get_db_path())
    db.init()

    try:
        if deck:
            deck_obj = db.get_deck_by_name(deck)
            if deck_obj is None:
                raise click.ClickException(f"Deck '{deck}' not found.")
            cards = db.get_deck_cards(deck_obj.id)
            console.print(f"[bold]Deck:[/bold] {deck}\n")
        else:
            cards = db.get_all_cards()

        if not cards:
            console.print("[yellow]No cards tracked yet. Run 'fetch' first.[/yellow]")
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
                old_usd = old_price_entry.price_usd if old_price_entry else None
                if new_usd is not None and old_usd is not None and old_usd != new_usd:
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

        if fetched > 0:
            db.clear_suggest_cache()

        console.print(f"\n[bold]Updated {fetched} cards, {errors} errors.[/bold]")
    finally:
        db.close()


@main.command()
@click.option("--format", "fmt", type=click.Choice(["csv", "json"]), default=None)
@click.option("--output", "output_path", type=click.Path(path_type=Path), default=None)
@click.option("--currency", type=click.Choice(["usd", "eur"]), default="usd")
@click.option(
    "--days",
    default="1,7,30",
    help="Trend windows, comma-separated (e.g. 1,7,30,90)",
)
@click.option("--skip-basics", is_flag=True, default=False, help="Exclude basic lands")
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
    day_list = _parse_days(days)

    db = Database(_get_db_path())
    db.init()

    try:
        card_list = None
        if deck:
            deck_obj = db.get_deck_by_name(deck)
            if deck_obj is None:
                raise click.ClickException(f"Deck '{deck}' not found.")
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
                raise click.ClickException(f"Deck '{deck}' not found.")
            cards = db.get_deck_cards(deck_obj.id)
            label = f"Deck: {deck}"
        else:
            cards = db.get_all_cards()
            label = "All cards"

        if not cards:
            console.print("[yellow]No cards tracked yet. Run 'fetch' first.[/yellow]")
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


@main.command()
@click.argument("deck_name")
@click.option(
    "--above",
    default=10.0,
    type=click.FloatRange(min=0),
    help="Only suggest for cards above this price (USD)",
)
@click.option(
    "--top",
    default=None,
    type=click.IntRange(min=1),
    help="Only suggest for top N most expensive cards",
)
@click.option(
    "--max-suggestions",
    default=5,
    type=click.IntRange(min=1, max=20),
    help="Max suggestions per card",
)
@click.option(
    "--include-lands", is_flag=True, default=False, help="Include lands in suggestions"
)
def suggest(
    deck_name: str,
    above: float,
    top: int | None,
    max_suggestions: int,
    include_lands: bool,
) -> None:
    """Suggest budget alternatives for expensive cards in a deck."""
    from mtg_prices.suggest import find_suggestions

    db = Database(_get_db_path())
    db.init()

    try:
        deck = db.get_deck_by_name(deck_name)
        if deck is None:
            raise click.ClickException(f"Deck '{deck_name}' not found.")

        cards = db.get_deck_cards(deck.id)
        if not cards:
            console.print("[yellow]No cards in this deck.[/yellow]")
            return

        # Get latest prices and filter expensive cards
        expensive = []
        for card in cards:
            latest = db.get_latest_price(card.id)
            if latest is None or latest.price_usd is None:
                continue
            if latest.price_usd >= above:
                expensive.append((card, latest))

        expensive.sort(key=lambda x: x[1].price_usd, reverse=True)
        if top is not None:
            expensive = expensive[:top]

        if not expensive:
            console.print(
                f"[yellow]No cards above ${above:.2f} in '{deck_name}'.[/yellow]"
            )
            return

        client = ScryfallClient()
        console.print("[dim]Loading Scryfall bulk data...[/dim]")
        client.load_bulk_data(_default_data_dir())

        if not client._bulk_type_index:
            console.print(
                "[red]Could not load Scryfall bulk data. "
                "Check your internet connection and try again.[/red]"
            )
            client.close()
            return

        table = Table(title=f'Budget Suggestions for "{deck_name}"')
        table.add_column("#", justify="right", style="dim")
        table.add_column("Card", style="bold")
        table.add_column("Price", justify="right")
        table.add_column("Suggestion")
        table.add_column("Price", justify="right")
        table.add_column("Saving", justify="right")

        total_saving = 0.0
        numbered_suggestions: list[tuple[Card, Suggestion]] = []
        suggestion_num = 0
        try:
            for card, price_entry in expensive:
                key = normalize_name(card.name).lower()
                bulk_prints = (
                    client._bulk_index.get(key, []) if client._bulk_index else []
                )
                if not bulk_prints:
                    continue
                original_card = _select_reference_print(bulk_prints)
                if original_card is None:
                    continue

                super_type = client._extract_super_type(
                    original_card.get("type_line", "")
                )
                if super_type == "Land" and not include_lands:
                    continue
                candidates = client.get_candidates(
                    super_type, original_card.get("color_identity", [])
                )

                cached = db.get_suggest_cache(
                    deck_id=deck.id, card_id=card.id, threshold=above
                )
                if cached:
                    suggestions_data = json.loads(cached)
                    suggestions = [Suggestion(**s) for s in suggestions_data]
                else:
                    suggestions = find_suggestions(
                        original_card=original_card,
                        candidates=candidates,
                        deck_format=deck.format,
                        max_suggestions=20,
                    )
                    cache_data = json.dumps(
                        [dataclasses.asdict(s) for s in suggestions]
                    )
                    db.put_suggest_cache(
                        deck_id=deck.id,
                        card_id=card.id,
                        threshold=above,
                        result_json=cache_data,
                    )
                suggestions = suggestions[:max_suggestions]

                if not suggestions:
                    table.add_row(
                        "",
                        card.name,
                        f"${price_entry.price_usd:.2f}",
                        "[dim]No suggestions[/dim]",
                        "",
                        "",
                    )
                    continue

                total_saving += suggestions[0].saving
                for i, s in enumerate(suggestions):
                    suggestion_num += 1
                    numbered_suggestions.append((card, s))
                    table.add_row(
                        str(suggestion_num),
                        card.name if i == 0 else "",
                        f"${s.original_price:.2f}" if i == 0 else "",
                        s.suggested_name,
                        f"${s.suggested_price:.2f}",
                        f"[green]-${s.saving:.2f}[/green]",
                    )
        finally:
            client.close()

        console.print(table)
        console.print(f"\n[bold]Total potential saving: ${total_saving:.2f}[/bold]")

        if not numbered_suggestions:
            return

        console.print(
            "\n[dim]Accept swaps? Enter numbers (e.g. 1,4,6), "
            "'all', or Enter to skip:[/dim]"
        )
        choice = input("> ").strip()
        if not choice:
            return

        if choice.lower() == "all":
            selected = set()
            seen_card_ids: set[int | None] = set()
            for num, (card, _) in enumerate(numbered_suggestions, 1):
                if card.id not in seen_card_ids:
                    selected.add(num)
                    seen_card_ids.add(card.id)
        else:
            try:
                selected = {int(n.strip()) for n in choice.split(",")}
            except ValueError:
                console.print("[red]Invalid input.[/red]")
                return

        swapped = 0
        swapped_card_ids: set[int | None] = set()
        for num in sorted(selected):
            if num < 1 or num > len(numbered_suggestions):
                console.print(f"[yellow]#{num} out of range, skipped.[/yellow]")
                continue
            original_card_obj, suggestion = numbered_suggestions[num - 1]
            if original_card_obj.id in swapped_card_ids:
                console.print(
                    f"[yellow]Only one suggestion can replace "
                    f"{original_card_obj.name}; #{num} skipped.[/yellow]"
                )
                continue
            new_card = Card(name=suggestion.suggested_name)
            new_card_id = db.upsert_card(new_card)
            db.remove_card_from_deck(deck.id, original_card_obj.id)
            db.add_card_to_deck(deck.id, new_card_id, original_card_obj.quantity)
            swapped_card_ids.add(original_card_obj.id)
            swapped += 1
            console.print(
                f"  [green]✓[/green] {original_card_obj.name} → {suggestion.suggested_name}"
            )

        if swapped > 0:
            db.clear_suggest_cache()
            console.print(
                f"\n[bold]{swapped} card(s) swapped. "
                f"Run 'mtg-prices update --deck \"{deck_name}\"' to fetch prices.[/bold]"
            )
    finally:
        db.close()
