from __future__ import annotations

import gzip
import json
import os

import httpx
import pytest

from mtg_prices.scraper import ScryfallClient

MOCK_CARDS = [
    {
        "name": "Swords to Plowshares",
        "lang": "en",
        "type_line": "Instant",
        "color_identity": ["W"],
        "cmc": 1.0,
        "oracle_text": (
            "Exile target creature. Its controller gains life equal to its power."
        ),
        "keywords": ["Exile"],
        "edhrec_rank": 5,
        "legalities": {"commander": "legal"},
        "prices": {"usd": "1.50", "eur": "1.20"},
        "set": "2xm",
        "set_name": "Double Masters",
        "oracle_id": "aaa",
        "released_at": "2020-08-07",
    },
    {
        "name": "Murder",
        "lang": "en",
        "type_line": "Instant",
        "color_identity": ["B"],
        "cmc": 3.0,
        "oracle_text": "Destroy target creature.",
        "keywords": [],
        "edhrec_rank": 200,
        "legalities": {"commander": "legal"},
        "prices": {"usd": "0.10", "eur": "0.08"},
        "set": "m20",
        "set_name": "Core Set 2020",
        "oracle_id": "bbb",
        "released_at": "2019-07-12",
    },
    {
        "name": "Llanowar Elves",
        "lang": "en",
        "type_line": "Creature \u2014 Elf Druid",
        "color_identity": ["G"],
        "cmc": 1.0,
        "oracle_text": "{T}: Add {G}.",
        "keywords": [],
        "power": "1",
        "toughness": "1",
        "edhrec_rank": 50,
        "legalities": {"commander": "legal"},
        "prices": {"usd": "0.20", "eur": "0.15"},
        "set": "dom",
        "set_name": "Dominaria",
        "oracle_id": "ccc",
        "released_at": "2018-04-27",
    },
]


@pytest.fixture()
def client() -> ScryfallClient:
    c = ScryfallClient()
    c._build_type_index(MOCK_CARDS)
    return c


def test_type_index_built(client: ScryfallClient) -> None:
    assert len(client._bulk_type_index) > 0


def test_type_index_creature(client: ScryfallClient) -> None:
    creatures = client._bulk_type_index.get("Creature", [])
    names = [c["name"] for c in creatures]
    assert "Llanowar Elves" in names


def test_get_candidates_filters_by_type(client: ScryfallClient) -> None:
    results = client.get_candidates("Instant", ["W"])
    names = [c["name"] for c in results]
    assert "Swords to Plowshares" in names
    assert "Llanowar Elves" not in names


def test_get_candidates_subset_color_identity(client: ScryfallClient) -> None:
    results = client.get_candidates("Instant", ["W", "B"])
    names = [c["name"] for c in results]
    assert "Swords to Plowshares" in names
    assert "Murder" in names


def test_get_candidates_excludes_superset(client: ScryfallClient) -> None:
    # Add a W/B card to the index
    wb_card = {
        "name": "Utter End",
        "type_line": "Instant",
        "color_identity": ["W", "B"],
        "prices": {"usd": "0.50"},
    }
    client._bulk_type_index.setdefault("Instant", []).append(wb_card)
    # Mono-W deck should NOT see a W/B card
    results = client.get_candidates("Instant", ["W"])
    names = [c["name"] for c in results]
    assert "Utter End" not in names


def test_get_candidates_colorless_matches_any_deck(
    client: ScryfallClient,
) -> None:
    sol_ring = {
        "name": "Sol Ring",
        "type_line": "Artifact",
        "color_identity": [],
        "prices": {"usd": "1.00"},
    }
    client._bulk_type_index.setdefault("Artifact", []).append(sol_ring)
    results = client.get_candidates("Artifact", ["R"])
    names = [c["name"] for c in results]
    assert "Sol Ring" in names


def test_extract_super_type_simple(client: ScryfallClient) -> None:
    assert client._extract_super_type("Instant") == "Instant"


def test_extract_super_type_with_subtype(client: ScryfallClient) -> None:
    assert client._extract_super_type("Creature \u2014 Elf Druid") == "Creature"


def test_extract_super_type_double_faced(client: ScryfallClient) -> None:
    result = client._extract_super_type(
        "Creature \u2014 Vampire // Creature \u2014 Vampire"
    )
    assert result == "Creature"


def test_extract_super_type_legendary(client: ScryfallClient) -> None:
    result = client._extract_super_type("Legendary Creature \u2014 Human Knight")
    assert result == "Creature"


def _jsonl_gzip(cards: list[dict]) -> bytes:
    return gzip.compress("\n".join(json.dumps(card) for card in cards).encode("utf-8"))


def test_load_bulk_data_downloads_and_streams_jsonl_gzip(tmp_path) -> None:
    bulk_url = "https://data.scryfall.io/default-cards.jsonl.gz"
    seen_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        if request.url.path == "/bulk-data/default-cards":
            return httpx.Response(200, json={"jsonl_download_uri": bulk_url})
        return httpx.Response(200, content=_jsonl_gzip(MOCK_CARDS))

    client = ScryfallClient()
    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        client.load_bulk_data(tmp_path)
    finally:
        client.close()

    assert (tmp_path / "default-cards.jsonl.gz").exists()
    assert "swords to plowshares" in client._bulk_index
    assert "Llanowar Elves" in [
        card["name"] for card in client._bulk_type_index["Creature"]
    ]
    assert [request.url.path for request in seen_requests] == [
        "/bulk-data/default-cards",
        "/default-cards.jsonl.gz",
    ]


@pytest.mark.parametrize("download_status", [200, 503])
def test_invalid_refresh_keeps_and_indexes_stale_cache(
    tmp_path, download_status
) -> None:
    cache_file = tmp_path / "default-cards.jsonl.gz"
    stale_bytes = _jsonl_gzip(MOCK_CARDS)
    cache_file.write_bytes(stale_bytes)
    os.utime(cache_file, (0, 0))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/bulk-data/default-cards":
            return httpx.Response(
                200,
                json={
                    "jsonl_download_uri": (
                        "https://data.scryfall.io/default-cards.jsonl.gz"
                    )
                },
            )
        return httpx.Response(download_status, content=b"not gzip")

    client = ScryfallClient()
    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        client.load_bulk_data(tmp_path, max_age_hours=0)
    finally:
        client.close()

    assert cache_file.read_bytes() == stale_bytes
    assert "murder" in client._bulk_index
    assert not list(tmp_path.glob("default-cards-*"))
