CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY NOT NULL,
    title TEXT NOT NULL,
    brand TEXT,
    size TEXT
);

CREATE TABLE IF NOT EXISTS photos (
    id TEXT PRIMARY KEY NOT NULL,
    item_id TEXT NOT NULL,
    filename TEXT,
    bytes_received INTEGER NOT NULL,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);