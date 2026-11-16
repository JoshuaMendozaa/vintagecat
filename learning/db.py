import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "vintagecat.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign key support
    return conn

def init_db():
    conn = get_db_connection()
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
            conn.commit()
    finally:
        conn.close()