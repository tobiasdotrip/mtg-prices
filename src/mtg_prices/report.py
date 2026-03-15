from __future__ import annotations

import csv
import io
import json
import logging
from datetime import date, timedelta

from rich.console import Console
from rich.table import Table

from mtg_prices.db import Database
from mtg_prices.models import CardReport

logger = logging.getLogger(__name__)

BASIC_LANDS = frozenset({
    "Plains", "Island", "Swamp", "Mountain", "Forest",
    "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
    "Snow-Covered Mountain", "Snow-Covered Forest", "Wastes",
})

CURRENCY_SYMBOLS = {"usd": "$", "eur": "€"}


def build_reports(
    db: Database,
    days: list[int],
    currency: str = "usd",
    skip_basics: bool = False,
    today: date | None = None,
) -> list[CardReport]:
    today = today or date.today()
    price_field = f"price_{currency}"
    cards = db.get_all_cards()
    reports: list[CardReport] = []

    for card in cards:
        if skip_basics and card.name in BASIC_LANDS:
            continue
        latest = db.get_latest_price(card.id)
        if latest is None:
            continue
        # Note: if latest fetch is older than today, trends are computed
        # relative to that date, not today. This is intentional — we can't
        # invent a price. Log a warning so the user knows data may be stale.
        if latest.fetched_at != today:
            logger.info(
                "Latest price for %r is from %s, not today",
                card.name, latest.fetched_at.isoformat(),
            )
        current_price = getattr(latest, price_field)
        if current_price is None:
            logger.warning("No %s price for %r", currency.upper(), card.name)

        trends: dict[int, float | None] = {}
        if current_price is not None:
            for d in days:
                target = today - timedelta(days=d)
                old = db.get_price_at(card.id, target, tolerance_days=2)
                if old is None:
                    trends[d] = None
                    continue
                old_price = getattr(old, price_field)
                if old_price is None or old_price == 0:
                    trends[d] = None
                    continue
                trends[d] = (current_price - old_price) / old_price * 100
        else:
            for d in days:
                trends[d] = None

        reports.append(CardReport(
            name=card.name,
            quantity=card.quantity,
            price_usd=latest.price_usd,
            price_eur=latest.price_eur,
            set_code=latest.set_code,
            trends=trends,
        ))

    price_attr = f"price_{currency}"
    reports.sort(key=lambda r: getattr(r, price_attr) or 0, reverse=True)
    return reports


def print_table(reports: list[CardReport], days: list[int], currency: str = "usd") -> None:
    symbol = CURRENCY_SYMBOLS.get(currency, "$")
    console = Console(force_terminal=True)
    table = Table(show_footer=True)

    table.add_column("Qté", justify="right", footer="")
    table.add_column("Carte", footer="TOTAL")
    table.add_column("Prix", justify="right", footer="")
    table.add_column("Ext", justify="center")
    for d in days:
        table.add_column(f"{d}j", justify="right")

    price_attr = f"price_{currency}"
    total_price = 0.0
    total_qty = 0
    for r in reports:
        price = getattr(r, price_attr)
        total_price += (price or 0) * r.quantity
        total_qty += r.quantity
        trend_cols = []
        for d in days:
            t = r.trends.get(d)
            if t is None:
                trend_cols.append("—")
            elif t >= 0:
                trend_cols.append(f"[green]+{t:.1f}%[/green]")
            else:
                trend_cols.append(f"[red]{t:.1f}%[/red]")

        table.add_row(
            str(r.quantity),
            r.name,
            f"{symbol}{price:.2f}" if price is not None else "—",
            r.set_code.upper(),
            *trend_cols,
        )

    # Update footer
    table.columns[0].footer = str(total_qty)
    table.columns[2].footer = f"{symbol}{total_price:.2f}"

    console.print(table)


def _format_trend(t: float | None) -> str:
    if t is None:
        return "—"
    return f"+{t:.1f}%" if t >= 0 else f"{t:.1f}%"


def export_csv(reports: list[CardReport], days: list[int]) -> str:
    output = io.StringIO()
    fieldnames = ["qty", "name", "price_usd", "price_eur", "set_code"]
    for d in days:
        fieldnames.append(f"trend_{d}d")
    writer = csv.DictWriter(output, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
    writer.writeheader()
    for r in reports:
        row: dict[str, object] = {
            "qty": r.quantity,
            "name": r.name,
            "price_usd": r.price_usd,
            "price_eur": r.price_eur,
            "set_code": r.set_code,
        }
        for d in days:
            row[f"trend_{d}d"] = _format_trend(r.trends.get(d))
        writer.writerow(row)
    return output.getvalue()


def export_json(reports: list[CardReport], days: list[int]) -> str:
    data = []
    for r in reports:
        entry: dict[str, object] = {
            "qty": r.quantity,
            "name": r.name,
            "price_usd": r.price_usd,
            "price_eur": r.price_eur,
            "set_code": r.set_code,
        }
        for d in days:
            entry[f"trend_{d}d"] = r.trends.get(d)
        data.append(entry)
    return json.dumps(data, indent=2, ensure_ascii=False)
