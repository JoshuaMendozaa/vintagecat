CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY NOT NULL,
    title TEXT NOT NULL,
    brand TEXT,
    size TEXT,
    color TEXT,
    listing_drafts_json TEXT,
    condition_notes TEXT NOT NULL DEFAULT '[]',
    analysis_json TEXT
);

CREATE TABLE IF NOT EXISTS photos (
    id TEXT PRIMARY KEY NOT NULL,
    item_id TEXT NOT NULL,
    filename TEXT,
    bytes_received INTEGER NOT NULL,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sold_comparables (
    id TEXT PRIMARY KEY NOT NULL,
    item_id TEXT NOT NULL,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    currency TEXT NOT NULL,
    sold_price_cents INTEGER NOT NULL,
    sold_on TEXT,
    UNIQUE(item_id, source_url),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);