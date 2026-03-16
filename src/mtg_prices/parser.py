from __future__ import annotations

import logging
import re
from pathlib import Path

from mtg_prices.models import Card

logger = logging.getLogger(__name__)

_LINE_RE = re.compile(r"^(\d+)\s+(.+)$")


def parse_decklist(path: Path) -> list[Card]:
    cards: list[Card] = []
    for lineno, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if not m:
            logger.warning("Line %d malformed, skipping: %r", lineno, line)
            continue
        qty = int(m.group(1))
        name = m.group(2).strip()
        cards.append(Card(name=name, quantity=qty))
    return cards
