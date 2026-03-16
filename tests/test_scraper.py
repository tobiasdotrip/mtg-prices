from mtg_prices.scraper import normalize_name, select_best_price


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
