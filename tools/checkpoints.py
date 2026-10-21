"""Deterministic local lesson runner. No AI, credentials, or network required."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ["learning/test_checkpoint_01.py", "checkpoint_tests/test_schema.py"]
LESSONS = [
    """# Checkpoint 1: item API
Implement ItemCreate and POST /items plus GET /items/{item_id} in learning/main.py.
See docs/LEARNING.md. Review the failing tests in the watcher terminal.
Title is required (1–120 characters); brand and size default to None.
Create returns 201 with a generated ID; unknown IDs return 404.
""",
    """# Checkpoint 2: SQLite schema
Checkpoint 1 currently passes. Your API still stores items in memory.

Create learning/schema.sql with a CREATE TABLE IF NOT EXISTS statement.
Table: items. Columns: id TEXT PRIMARY KEY NOT NULL, title TEXT NOT NULL,
brand TEXT, size TEXT. Separate columns with commas and finish with );.
Write it yourself, using our SQL discussion as your guide.

The checks execute your SQL in an isolated in-memory database. They do not
connect your API to SQLite yet or touch any garment data.
Save the SQL file; the watcher will rerun and show the next exercise here.

Explain: why should running CREATE TABLE twice be safe?
""",
    """# Checkpoint 3: connect Python to SQLite
Checkpoints 1 and 2 currently pass. Schema creation alone does NOT persist API data.

Next small exercise: create learning/database.py and write init_db(db_path).
Use Python's sqlite3 module to connect to db_path, load learning/schema.sql
relative to __file__, execute the schema, commit, and close the connection.
Use a temporary database path when experimenting.

Before changing the API, bring your function back to the tutor for review.
Then we will write a persistence acceptance test and replace dictionary storage.
This add-on has automated gates ONLY for checkpoints 1 and 2; it cannot invent
new lessons or review your understanding. Checkpoint 3 is not automatically graded.

To require checkpoint 2 on GitHub, change required_through to 2 in
checkpoints.json and commit that change with your schema.
Do not set it to 3: that gate has not been defined yet.
""",
]

def run_check(path):
    print(f"\nChecking {path}", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", path, "-q"],
            cwd=ROOT, timeout=60,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("Checkpoint timed out after 60 seconds. Check for a hanging test.")
        return False

def check(ci=False):
    if ci:
        try:
            count = json.loads((ROOT / "checkpoints.json").read_text())["required_through"]
            if type(count) is not int or not 1 <= count <= len(CHECKS):
                raise ValueError("required_through must be 1 or 2")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"Invalid checkpoints.json: {exc}", file=sys.stderr)
            return 2
    else:
        count = len(CHECKS)
    passed = 0
    for path in CHECKS[:count]:
        if not run_check(path):
            break
        passed += 1
    if ci:
        return 0 if passed == count else 1
    next_step = ROOT / "learning" / "NEXT_STEP.md"
    temp = next_step.with_suffix(".tmp")
    temp.write_text(LESSONS[passed], encoding="utf-8")
    temp.replace(next_step)
    progress = ROOT / "learning" / ".checkpoint-progress.json"
    progress.write_text(json.dumps({"currently_passing": passed}, indent=2) + "\n")
    print(f"\n{passed}/{len(CHECKS)} gates pass. Open learning/NEXT_STEP.md", flush=True)
    return 0 if passed == count else 1

def fingerprint():
    digest = hashlib.sha256()
    paths = [ROOT / "checkpoints.json", ROOT / "requirements.txt", ROOT / "requirements-dev.txt"]
    for folder in ("learning", "checkpoint_tests", "tools"):
        paths.extend(p for p in (ROOT / folder).rglob("*") if p.suffix in (".py", ".sql"))
    for path in sorted(paths):
        digest.update(str(path).encode())
        try:
            digest.update(path.read_bytes())
        except FileNotFoundError:
            digest.update(b"missing")
    return digest.digest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--watch", action="store_true")
    mode.add_argument("--ci", action="store_true")
    args = parser.parse_args()
    if not args.watch:
        return check(ci=args.ci)
    print("Watching Python/SQL saves. Open learning/NEXT_STEP.md. Stop with Ctrl+C.", flush=True)
    previous = None
    try:
        while True:
            current = fingerprint()
            if current != previous:
                time.sleep(0.3)
                previous = fingerprint()
                check()
            time.sleep(1)
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
