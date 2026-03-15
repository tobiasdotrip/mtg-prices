from __future__ import annotations

import logging
import time
import unicodedata
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.scryfall.com"
_HEADERS = {
    "User-Agent": "mtg-prices/0.1.0",
    "Accept": "application/json",
}
_REQUEST_DELAY = 0.1  # 100ms between requests


def normalize_name(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def select_best_price(
    prints: list[dict[str, Any]], max_editions: int = 5
) -> dict[str, Any] | None:
    """Select the cheapest USD price among the most recent editions.

    EUR price returned is from the same edition as the best USD price,
    not the cheapest EUR across editions. This is intentional — we track
    by edition, not by individual currency.
    """
    best: dict[str, Any] | None = None
    best_usd = float("inf")
    for card_data in prints[:max_editions]:
        prices = card_data.get("prices", {})
        usd_str = prices.get("usd")
        if usd_str is None:
            continue
        usd = float(usd_str)
        eur_str = prices.get("eur")
        eur = float(eur_str) if eur_str else None
        if usd < best_usd:
            best_usd = usd
            best = {
                "price_usd": usd,
                "price_eur": eur,
                "set_code": card_data["set"],
                "set_name": card_data["set_name"],
                "oracle_id": card_data.get("oracle_id"),
            }
    return best


class ScryfallClient:
    def __init__(self) -> None:
        self._client = httpx.Client(headers=_HEADERS, timeout=30.0)
        self._last_request: float = 0

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < _REQUEST_DELAY:
            time.sleep(_REQUEST_DELAY - elapsed)
        self._last_request = time.monotonic()

    def _get(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        self._rate_limit()
        for attempt in range(3):
            resp = self._client.get(url, params=params)
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = 2 ** attempt
                logger.warning("Scryfall %d, retrying in %ds...", resp.status_code, wait)
                time.sleep(wait)
                continue
            return resp
        return resp  # return last response even if failed

    def search_card(self, name: str) -> dict[str, Any] | None:
        normalized = normalize_name(name)
        # Exact search — returns all prints
        resp = self._get(
            f"{_BASE_URL}/cards/search",
            params={"q": f'!"{normalized}"', "order": "released", "dir": "desc"},
        )
        if resp.status_code == 200:
            data = resp.json()
            prints = data.get("data", [])
            return select_best_price(prints)

        # Fallback: fuzzy search (single result, lose multi-edition selection)
        logger.info("Exact search failed for %r, trying fuzzy", name)
        resp = self._get(
            f"{_BASE_URL}/cards/named",
            params={"fuzzy": name},
        )
        if resp.status_code == 200:
            card_data = resp.json()
            return select_best_price([card_data])

        logger.warning("Card not found on Scryfall: %r", name)
        return None

    def close(self) -> None:
        self._client.close()
