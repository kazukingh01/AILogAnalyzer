#!/usr/bin/env python3
"""Show analysis progress per file from SQLite state."""

import argparse
import sqlite3

DB_PATH = "/data/db/state.db"


def show_status(service: str | None = None, show_all: bool = False) -> None:
    conn = sqlite3.connect(DB_PATH)

    query = "SELECT service, filepath, last_line, total_lines, last_size, updated_at FROM log_state"
    params: tuple = ()
    if service:
        query += " WHERE service = ?"
        params = (service,)
    query += " ORDER BY service, filepath"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        print("No records found.")
        return

    total_analyzed = 0
    total_all = 0
    completed = 0
    incomplete = 0

    current_service = None
    for svc, filepath, last_line, total_lines, last_size, updated_at in rows:
        pct = (last_line / total_lines * 100) if total_lines > 0 else 100.0
        remaining = total_lines - last_line

        total_analyzed += last_line
        total_all += total_lines

        if remaining == 0:
            completed += 1
            if not show_all:
                continue
        else:
            incomplete += 1

        if svc != current_service:
            if current_service is not None:
                print()
            print(f"=== {svc} ===")
            current_service = svc

        print(f"  {filepath:50s}  {last_line:>8} / {total_lines:>8}  ({pct:5.1f}%)  remaining: {remaining}")

    print()
    overall_pct = (total_analyzed / total_all * 100) if total_all > 0 else 100.0
    print(f"Files: {completed} done, {incomplete} in progress")
    print(f"Total: {total_analyzed} / {total_all} lines ({overall_pct:.1f}%)  remaining: {total_all - total_analyzed}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Show log analysis progress")
    parser.add_argument("service", nargs="?", default=None)
    parser.add_argument("--all", "-a", action="store_true", help="Show completed files too")
    args = parser.parse_args()
    show_status(args.service, args.all)


if __name__ == "__main__":
    main()
