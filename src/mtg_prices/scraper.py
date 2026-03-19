from __future__ import annotations

import json
import logging
import time
import unicodedata
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.scryfall.com"
_HEADERS = {
    "User-Agent": "mtg-prices/0.3.0",
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


_KNOWN_SUPER_TYPES = {
    "Creature",
    "Instant",
    "Sorcery",
    "Enchantment",
    "Artifact",
    "Planeswalker",
    "Land",
    "Battle",
}


class ScryfallClient:
    def __init__(self) -> None:
        self._client = httpx.Client(headers=_HEADERS, timeout=30.0)
        self._last_request: float = 0
        self._bulk_index: dict[str, list[dict[str, Any]]] | None = None
        self._bulk_type_index: dict[str, list[dict[str, Any]]] = {}

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < _REQUEST_DELAY:
            time.sleep(_REQUEST_DELAY - elapsed)
        self._last_request = time.monotonic()

    def _get(
        self, url: str, params: dict[str, str] | None = None
    ) -> httpx.Response:
        self._rate_limit()
        for attempt in range(3):
            resp = self._client.get(url, params=params)
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = 2**attempt
                logger.warning(
                    "Scryfall %d, retrying in %ds...", resp.status_code, wait
                )
                time.sleep(wait)
                continue
            return resp
        return resp  # return last response even if failed

    def load_bulk_data(self, cache_dir: Path, max_age_hours: int = 24) -> None:
        """Download Scryfall 'Default Cards' bulk file,
        cache it, and build a name index."""
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "default-cards.json"

        need_download = True
        if cache_file.exists():
            age_hours = (time.time() - cache_file.stat().st_mtime) / 3600
            if age_hours < max_age_hours:
                need_download = False
                logger.info("Using cached bulk data (%.1fh old)", age_hours)

        if need_download:
            logger.info("Fetching bulk data download URL...")
            meta_resp = self._get(f"{_BASE_URL}/bulk-data/default-cards")
            if meta_resp.status_code != 200:
                logger.warning(
                    "Could not fetch bulk data metadata, falling back to API"
                )
                return
            download_uri = meta_resp.json()["download_uri"]

            logger.info("Downloading bulk data...")
            with (
                self._client.stream("GET", download_uri) as stream,
                open(cache_file, "wb") as f,
            ):
                for chunk in stream.iter_bytes(chunk_size=1024 * 64):
                    f.write(chunk)
            logger.info("Bulk data saved to %s", cache_file)

        logger.info("Indexing bulk data...")

        index: dict[str, list[dict[str, Any]]] = {}
        with open(cache_file, encoding="utf-8") as f:
            cards = json.load(f)

        en_cards: list[dict[str, Any]] = []
        for card_data in cards:
            if card_data.get("lang") != "en":
                continue
            name = normalize_name(card_data.get("name", ""))
            if name:
                index.setdefault(name.lower(), []).append(card_data)
            en_cards.append(card_data)

        # Sort each name's prints by release date descending (most recent first)
        for prints in index.values():
            prints.sort(key=lambda c: c.get("released_at", ""), reverse=True)

        self._bulk_index = index
        self._build_type_index(en_cards)
        logger.info("Indexed %d unique card names from bulk data", len(index))
        logger.info("Built type index with %d super-types", len(self._bulk_type_index))

    def search_card(self, name: str) -> dict[str, Any] | None:
        normalized = normalize_name(name)

        # Try bulk index first
        if self._bulk_index is not None:
            key = normalized.lower()
            prints = self._bulk_index.get(key)
            if prints:
                return select_best_price(prints)
            logger.info("Card %r not in bulk index, trying API", name)

        # Exact search — returns all prints
        resp = self._get(
            f"{_BASE_URL}/cards/search",
            params={
                "q": f'!"{normalized}"',
                "unique": "prints",
                "order": "released",
                "dir": "desc",
            },
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

    def _extract_super_type(self, type_line: str) -> str:
        """Extract main type from a type line."""
        # Handle double-faced cards
        main_face = type_line.split("//")[0].strip()
        # Take left side of em-dash (supertypes + type)
        main_part = main_face.split("\u2014")[0].strip()
        # Match against known types
        for word in main_part.split():
            if word in _KNOWN_SUPER_TYPES:
                return word
        return main_part

    def _build_type_index(self, cards: list[dict[str, Any]]) -> None:
        """Build index from cards already filtered to English by load_bulk_data."""
        index: dict[str, list[dict[str, Any]]] = {}
        for card in cards:
            type_line = card.get("type_line", "")
            super_type = self._extract_super_type(type_line)
            index.setdefault(super_type, []).append(card)
        self._bulk_type_index = index

    def get_candidates(
        self, super_type: str, deck_color_identity: list[str]
    ) -> list[dict[str, Any]]:
        """Get cards matching type whose color_identity is a subset of deck's colors."""
        deck_colors = set(deck_color_identity)
        results = []
        for card in self._bulk_type_index.get(super_type, []):
            card_colors = set(card.get("color_identity", []))
            if card_colors <= deck_colors:
                results.append(card)
        return results

    def close(self) -> None:
        self._client.close()
