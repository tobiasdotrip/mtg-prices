CREATE TABLE IF NOT EXISTS suggest_cache (
    id INTEGER PRIMARY KEY,
    deck_id INTEGER NOT NULL,
    card_id INTEGER NOT NULL,
    threshold REAL NOT NULL,
    result_json TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(deck_id, card_id, threshold)
);
