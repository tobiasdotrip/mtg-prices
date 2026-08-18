from __future__ import annotations

import httpx
import pytest

from mtg_prices import __version__
from mtg_prices.scraper import ScryfallClient, normalize_name, select_best_price


def test_normalize_ascii():
    assert normalize_name("Lightning Bolt") == "Lightning Bolt"


def test_normalize_diacritics():
    assert normalize_name("Jötun Grunt") == "Jotun Grunt"


def test_normalize_accented():
    assert normalize_name("Séance") == "Seance"


def test_select_best_price_usd():
    prints = [
        {
            "prices": {"usd": "5.00", "eur": "4.00"},
            "set": "SET1",
            "set_name": "Set One",
            "oracle_id": "abc",
        },
        {
            "prices": {"usd": "3.00", "eur": "2.50"},
            "set": "SET2",
            "set_name": "Set Two",
            "oracle_id": "abc",
        },
        {
            "prices": {"usd": "7.00", "eur": "6.00"},
            "set": "SET3",
            "set_name": "Set Three",
            "oracle_id": "abc",
        },
    ]
    result = select_best_price(prints, max_editions=5)
    assert result is not None
    assert result["price_usd"] == 3.0
    assert result["set_code"] == "SET2"


def test_select_best_price_skips_null():
    prints = [
        {
            "prices": {"usd": None, "eur": None},
            "set": "SET1",
            "set_name": "Set One",
            "oracle_id": "abc",
        },
        {
            "prices": {"usd": "3.00", "eur": "2.50"},
            "set": "SET2",
            "set_name": "Set Two",
            "oracle_id": "abc",
        },
    ]
    result = select_best_price(prints, max_editions=5)
    assert result is not None
    assert result["price_usd"] == 3.0


def test_select_best_price_all_null():
    prints = [
        {
            "prices": {"usd": None, "eur": None},
            "set": "SET1",
            "set_name": "Set One",
            "oracle_id": "abc",
        },
    ]
    result = select_best_price(prints, max_editions=5)
    assert result is None


def test_select_best_price_limits_editions():
    prints = [
        {
            "prices": {"usd": str(i), "eur": str(i)},
            "set": f"S{i}",
            "set_name": f"Set {i}",
            "oracle_id": "abc",
        }
        for i in range(10, 0, -1)  # 10 editions, prices 10 down to 1
    ]
    # Only looks at first 5 (prices 10,9,8,7,6) — cheapest is 6
    result = select_best_price(prints, max_editions=5)
    assert result is not None
    assert result["price_usd"] == 6.0


def test_client_identifies_version_and_accepts_json():
    client = ScryfallClient()
    try:
        assert client._client.headers["User-Agent"] == f"mtg-prices/{__version__}"
        assert client._client.headers["Accept"] == "application/json"
    finally:
        client.close()


@pytest.mark.parametrize(
    ("headers", "expected_wait"),
    [({}, 30.0), ({"Retry-After": "12.5"}, 12.5)],
)
def test_rate_limit_429_waits_before_retry(monkeypatch, headers, expected_wait):
    responses = [
        httpx.Response(429, headers=headers),
        httpx.Response(200),
    ]

    class FakeClient:
        def get(self, url, params=None):
            return responses.pop(0)

    client = ScryfallClient()
    client._client.close()
    client._client = FakeClient()
    sleeps = []
    monkeypatch.setattr("mtg_prices.scraper.time.sleep", sleeps.append)

    response = client._get("https://api.scryfall.com/bulk-data/default-cards")

    assert response.status_code == 200
    assert sleeps == [expected_wait]


def test_card_endpoints_are_limited_to_two_requests_per_second(monkeypatch):
    class FakeClient:
        def get(self, url, params=None):
            return httpx.Response(200)

    client = ScryfallClient()
    client._client.close()
    client._client = FakeClient()
    monotonic = iter([100.0, 100.0, 100.2, 100.5])
    sleeps = []
    monkeypatch.setattr("mtg_prices.scraper.time.monotonic", lambda: next(monotonic))
    monkeypatch.setattr("mtg_prices.scraper.time.sleep", sleeps.append)

    client._get("https://api.scryfall.com/cards/search")
    client._get("https://api.scryfall.com/cards/named")

    assert sleeps == [pytest.approx(0.3)]
