from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Card:
    name: str
    quantity: int = 1
    oracle_id: str | None = None
    id: int | None = None


@dataclass
class PriceEntry:
    card_id: int
    price_usd: float | None
    price_eur: float | None
    set_code: str
    set_name: str
    fetched_at: date
    id: int | None = None


@dataclass
class Deck:
    name: str
    id: int | None = None


@dataclass
class CardReport:
    name: str
    quantity: int
    price_usd: float | None
    price_eur: float | None
    set_code: str
    trends: dict[int, float | None] = field(default_factory=dict)
