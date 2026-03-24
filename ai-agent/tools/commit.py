#!/usr/bin/env python3
"""Commit analyzed log positions to SQLite.

Reads _state.json (file A) and updates the SQLite database with
the new file positions, marking those log portions as analyzed.
Then cleans up the work directory.
"""

import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = "/data/db/db.sqlite"
WORK_BASE = "/data/work"


def commit_service(service: str) -> None:
    work_dir = Path(WORK_BASE)
    state_file = work_dir / "_state.json"

    if not state_file.exists():
        print(f"No state file found: {state_file}", file=sys.stderr)
        sys.exit(1)

    with open(state_file) as f:
        state = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    now = int(datetime.now(timezone.utc).timestamp())

    for entry in state["files"]:
        conn.execute(
            """
            INSERT INTO log_state (service, filepath, last_line, total_lines, last_size, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (service, filepath)
            DO UPDATE SET last_line = excluded.last_line,
                          total_lines = excluded.total_lines,
                          last_size = excluded.last_size,
                          updated_at = excluded.updated_at
            """,
            (service, entry["filepath"], entry["last_line"], entry["total_lines"], entry["last_size"], now),
        )

    conn.commit()
    conn.close()

    # Clean up work directory (keep log files)
    keep_files = {"analyze.log", "claude_stream.jsonl", "_state.json", "_search_result.txt"}
    for item in work_dir.rglob("*"):
        if item.is_file() and item.name not in keep_files:
            item.unlink()
    for item in sorted(work_dir.rglob("*"), reverse=True):
        if item.is_dir() and not any(item.iterdir()):
            item.rmdir()

    print(f"Committed {len(state['files'])} file(s) for service '{service}'")


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <service_name>", file=sys.stderr)
        sys.exit(1)

    service = sys.argv[1]
    commit_service(service)


if __name__ == "__main__":
    main()
