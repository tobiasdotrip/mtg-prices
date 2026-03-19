import json
from datetime import datetime, timedelta
from mtg_prices.db import Database


def test_put_suggest_cache(db):
    db.conn.execute("INSERT INTO cards (id, name) VALUES (1, 'Test Card')")
    db.conn.execute("INSERT INTO decks (id, name) VALUES (1, 'Test Deck')")
    db.conn.commit()
    data = [{"name": "Alt Card", "price": 1.0}]
    db.put_suggest_cache(deck_id=1, card_id=1, threshold=10.0, result_json=json.dumps(data))


def test_get_suggest_cache_hit(db):
    db.conn.execute("INSERT INTO cards (id, name) VALUES (1, 'Test Card')")
    db.conn.execute("INSERT INTO decks (id, name) VALUES (1, 'Test Deck')")
    db.conn.commit()
    data = [{"name": "Alt Card", "price": 1.0}]
    db.put_suggest_cache(deck_id=1, card_id=1, threshold=10.0, result_json=json.dumps(data))
    result = db.get_suggest_cache(deck_id=1, card_id=1, threshold=10.0, max_age_hours=24)
    assert result is not None
    assert json.loads(result) == data


def test_get_suggest_cache_miss(db):
    result = db.get_suggest_cache(deck_id=99, card_id=99, threshold=10.0, max_age_hours=24)
    assert result is None


def test_get_suggest_cache_expired(db):
    db.conn.execute("INSERT INTO cards (id, name) VALUES (1, 'Test Card')")
    db.conn.execute("INSERT INTO decks (id, name) VALUES (1, 'Test Deck')")
    db.conn.commit()
    data = [{"name": "Alt Card"}]
    db.put_suggest_cache(deck_id=1, card_id=1, threshold=10.0, result_json=json.dumps(data))
    old_ts = (datetime.now() - timedelta(hours=25)).isoformat()
    db.conn.execute(
        "UPDATE suggest_cache SET created_at = ? WHERE deck_id = 1 AND card_id = 1",
        (old_ts,),
    )
    db.conn.commit()
    result = db.get_suggest_cache(deck_id=1, card_id=1, threshold=10.0, max_age_hours=24)
    assert result is None


def test_clear_suggest_cache(db):
    db.conn.execute("INSERT INTO cards (id, name) VALUES (1, 'Test Card')")
    db.conn.execute("INSERT INTO decks (id, name) VALUES (1, 'Test Deck')")
    db.conn.commit()
    db.put_suggest_cache(deck_id=1, card_id=1, threshold=10.0, result_json="[]")
    db.clear_suggest_cache()
    result = db.get_suggest_cache(deck_id=1, card_id=1, threshold=10.0, max_age_hours=24)
    assert result is None
