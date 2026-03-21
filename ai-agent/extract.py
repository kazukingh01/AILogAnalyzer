#!/usr/bin/env python3
"""Extract unanalyzed log portions for a given service.

Reads SQLite state to determine where each log file was last analyzed,
then extracts only the new (unanalyzed) portions into /data/work/<service>/.
Saves current file positions to _state.json for later commit.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = "/data/db/state.db"
LOG_BASE = "/data/logs"
WORK_BASE = "/data/work"


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS log_state (
            service     TEXT NOT NULL,
            filepath    TEXT NOT NULL,
            last_line   INTEGER NOT NULL,
            last_size   INTEGER NOT NULL,
            updated_at  TEXT NOT NULL,
            PRIMARY KEY (service, filepath)
        )
    """)
    conn.commit()


def get_state(conn: sqlite3.Connection, service: str) -> dict[str, dict]:
    """Return {filepath: {last_line, last_size}} for the service."""
    cur = conn.execute(
        "SELECT filepath, last_line, last_size FROM log_state WHERE service = ?",
        (service,),
    )
    return {row[0]: {"last_line": row[1], "last_size": row[2]} for row in cur}


def extract_service(service: str) -> None:
    log_dir = Path(LOG_BASE) / service
    work_dir = Path(WORK_BASE) / service

    if not log_dir.is_dir():
        print(f"Log directory not found: {log_dir}", file=sys.stderr)
        sys.exit(1)

    # Clean previous work files
    if work_dir.exists():
        for f in work_dir.rglob("*"):
            if f.is_file():
                f.unlink()
    work_dir.mkdir(parents=True, exist_ok=True)

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    state = get_state(conn, service)
    conn.close()

    state_entries = []

    # Walk all log files
    for log_file in sorted(log_dir.rglob("*")):
        if not log_file.is_file():
            continue

        rel_path = str(log_file.relative_to(log_dir))
        file_size = log_file.stat().st_size

        prev = state.get(rel_path)
        start_line = 0

        if prev is not None:
            if file_size < prev["last_size"]:
                # File truncated or rotated — read from beginning
                start_line = 0
            else:
                start_line = prev["last_line"]

        # Read file and extract unanalyzed lines
        try:
            with open(log_file, "r", errors="replace") as f:
                lines = f.readlines()
        except (OSError, IOError) as e:
            print(f"Warning: cannot read {log_file}: {e}", file=sys.stderr)
            continue

        total_lines = len(lines)

        if start_line >= total_lines:
            # No new content
            continue

        new_lines = lines[start_line:]

        # Save extracted lines to work directory
        out_file = work_dir / rel_path
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w") as f:
            f.writelines(new_lines)

        state_entries.append(
            {
                "filepath": rel_path,
                "last_line": total_lines,
                "last_size": file_size,
            }
        )

    # Save state file (file A)
    state_file = work_dir / "_state.json"
    with open(state_file, "w") as f:
        json.dump(
            {
                "service": service,
                "files": state_entries,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
            },
            f,
            indent=2,
        )

    print(f"Extracted {len(state_entries)} file(s) for service '{service}'")


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <service_name>", file=sys.stderr)
        sys.exit(1)

    service = sys.argv[1]
    extract_service(service)


if __name__ == "__main__":
    main()
