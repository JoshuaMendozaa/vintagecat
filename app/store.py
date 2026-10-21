import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as con:
            con.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY, document TEXT NOT NULL, version INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, item_id TEXT NOT NULL, kind TEXT NOT NULL,
                state TEXT NOT NULL, payload TEXT NOT NULL, error TEXT,
                created_at TEXT NOT NULL, finished_at TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_job
                ON jobs(item_id, kind) WHERE state IN ('queued', 'running');
            CREATE TABLE IF NOT EXISTS usage (month TEXT PRIMARY KEY, calls INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS cache (query TEXT PRIMARY KEY, created_at TEXT NOT NULL, result TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def recover(self):
        with self.connect() as con:
            con.execute("UPDATE jobs SET state='interrupted', error=?, finished_at=? WHERE state IN ('queued','running')",
                        ("Application restarted. Review and retry explicitly.", now()))

    def create(self, item):
        with self.connect() as con:
            con.execute("INSERT INTO items VALUES(?,?,1)", (item["id"], json.dumps(item)))

    def get(self, item_id):
        with self.connect() as con:
            row = con.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        if not row:
            raise KeyError(item_id)
        data = json.loads(row["document"])
        data["version"] = row["version"]
        return data

    def all(self):
        with self.connect() as con:
            rows = con.execute("SELECT * FROM items ORDER BY rowid DESC").fetchall()
        return [dict(json.loads(r["document"]), version=r["version"]) for r in rows]

    def mutate(self, item_id, fn, expected_version=None):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            if not row:
                raise KeyError(item_id)
            if expected_version is not None and expected_version != row["version"]:
                raise ValueError("This item changed. Reload it before saving to avoid losing edits.")
            data = json.loads(row["document"])
            fn(data)
            data["updated_at"] = now()
            data.pop("version", None)
            con.execute("UPDATE items SET document=?, version=version+1 WHERE id=?", (json.dumps(data), item_id))
        return self.get(item_id)

    def job(self, job_id):
        with self.connect() as con:
            row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise KeyError(job_id)
        return dict(row)

