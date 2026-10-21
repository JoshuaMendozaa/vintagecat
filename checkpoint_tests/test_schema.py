"""Checkpoint 2: execute the learner's schema in an isolated in-memory database."""
from pathlib import Path
import sqlite3
import pytest

SCHEMA = Path(__file__).resolve().parents[1] / "learning" / "schema.sql"

@pytest.fixture
def db():
    assert SCHEMA.is_file(), "Create learning/schema.sql using NEXT_STEP.md"
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(SCHEMA.read_text())
        yield conn
    finally:
        conn.close()

def test_schema_can_run_twice(db):
    db.executescript(SCHEMA.read_text())
    columns = {row[1]: row for row in db.execute("PRAGMA table_info(items)")}
    assert set(columns) == {"id", "title", "brand", "size"}
    assert all(row[2].upper() == "TEXT" for row in columns.values())
    assert columns["id"][5] == 1

def test_optional_values_can_be_null(db):
    db.execute("INSERT INTO items (id, title) VALUES (?, ?)", ("one", "Work jacket"))
    assert db.execute("SELECT brand, size FROM items").fetchone() == (None, None)

def test_duplicate_id_is_rejected(db):
    db.execute("INSERT INTO items (id, title) VALUES (?, ?)", ("one", "Jacket"))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO items (id, title) VALUES (?, ?)", ("one", "Jeans"))

@pytest.mark.parametrize("item_id,title", [(None, "Jacket"), ("one", None)])
def test_required_values_cannot_be_null(db, item_id, title):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO items (id, title) VALUES (?, ?)", (item_id, title))
