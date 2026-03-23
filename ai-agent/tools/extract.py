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

DB_PATH = "/data/db/db"
LOG_BASE = "/data/logs"
WORK_BASE = "/data/work"
MAX_LINES = int(os.environ.get("MAX_EXTRACT_LINES", "0"))  # 0 = unlimited


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS log_state (
            service      TEXT NOT NULL,
            filepath     TEXT NOT NULL,
            last_line    INTEGER NOT NULL,
            total_lines  INTEGER NOT NULL DEFAULT 0,
            last_size    INTEGER NOT NULL,
            updated_at   INTEGER NOT NULL,
            PRIMARY KEY (service, filepath)
        )
    """)
    # Migrate: add total_lines if missing
    cur = conn.execute("PRAGMA table_info(log_state)")
    columns = {row[1]: row[2] for row in cur}
    if "total_lines" not in columns:
        conn.execute("ALTER TABLE log_state ADD COLUMN total_lines INTEGER NOT NULL DEFAULT 0")
    # Migrate: updated_at TEXT -> INTEGER (Unix epoch)
    if columns.get("updated_at") == "TEXT":
        conn.execute("""
            CREATE TABLE log_state_new (
                service      TEXT NOT NULL,
                filepath     TEXT NOT NULL,
                last_line    INTEGER NOT NULL,
                total_lines  INTEGER NOT NULL DEFAULT 0,
                last_size    INTEGER NOT NULL,
                updated_at   INTEGER NOT NULL,
                PRIMARY KEY (service, filepath)
            )
        """)
        conn.execute("""
            INSERT INTO log_state_new (service, filepath, last_line, total_lines, last_size, updated_at)
            SELECT service, filepath, last_line, total_lines, last_size,
                   CAST(strftime('%s', updated_at) AS INTEGER)
            FROM log_state
        """)
        conn.execute("DROP TABLE log_state")
        conn.execute("ALTER TABLE log_state_new RENAME TO log_state")
    conn.commit()


def get_state(conn: sqlite3.Connection, service: str) -> dict[str, dict]:
    """Return {filepath: {last_line, last_size}} for the service."""
    cur = conn.execute(
        "SELECT filepath, last_line, last_size FROM log_state WHERE service = ?",
        (service,),
    )
    return {row[0]: {"last_line": row[1], "last_size": row[2]} for row in cur}


def extract_service(service: str) -> None:
    log_dir = Path(LOG_BASE)
    work_dir = Path(WORK_BASE)

    if not log_dir.is_dir():
        print(f"Log directory not found: {log_dir}", file=sys.stderr)
        sys.exit(1)

    # Clean previous work files
    if work_dir.exists():
        for f in work_dir.rglob("*"):
            if f.is_file():
                f.unlink()
    work_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    state = get_state(conn, service)
    conn.close()

    state_entries = []
    total_extracted = 0

    # Walk all log files
    for log_file in sorted(log_dir.rglob("*")):
        if not log_file.is_file():
            continue

        # Stop if we've hit the max lines limit
        if MAX_LINES > 0 and total_extracted >= MAX_LINES:
            break

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

        actual_total = len(lines)

        if start_line >= actual_total:
            # No new content
            continue

        new_lines = lines[start_line:]

        # Cap lines if max limit is set
        processed_up_to = actual_total
        if MAX_LINES > 0:
            remaining = MAX_LINES - total_extracted
            if len(new_lines) > remaining:
                new_lines = new_lines[:remaining]
                # Record only up to the lines we actually extracted
                processed_up_to = start_line + len(new_lines)

        # Save extracted lines to work directory
        out_file = work_dir / rel_path
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w") as f:
            f.writelines(new_lines)

        total_extracted += len(new_lines)

        state_entries.append(
            {
                "filepath": rel_path,
                "last_line": processed_up_to,
                "total_lines": actual_total,
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

    limit_msg = f" (limit: {MAX_LINES})" if MAX_LINES > 0 else ""
    print(
        f"Extracted {total_extracted} line(s) from {len(state_entries)} file(s) "
        f"for service '{service}'{limit_msg}"
    )


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <service_name>", file=sys.stderr)
        sys.exit(1)

    service = sys.argv[1]
    extract_service(service)


if __name__ == "__main__":
    main()
