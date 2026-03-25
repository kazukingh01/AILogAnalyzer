#!/usr/bin/env python3
"""Extract unanalyzed log portions for a given service.

Reads SQLite state to determine where each log file was last analyzed,
then extracts only the new (unanalyzed) portions into /data/work/<service>/.
Saves current file positions to _state.json for later commit.
"""

import fnmatch
import gzip
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = "/data/db/db.sqlite"
LOG_BASE = "/data/logs"
WORK_BASE = "/data/work"
MAX_LINES = int(os.environ.get("MAX_EXTRACT_LINES", "0"))  # 0 = unlimited
FILE_PATTERN = os.environ.get("LOG_FILE_PATTERN", "*.log")  # glob pattern for target files


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS log_state (
            service      TEXT NOT NULL,
            filepath     TEXT NOT NULL,
            last_line    INTEGER NOT NULL,
            total_lines  INTEGER NOT NULL DEFAULT 0,
            last_size    INTEGER NOT NULL,
            updated_at   INTEGER NOT NULL,
            file_head    TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (service, filepath)
        )
    """)
    # Migrate: add total_lines if missing
    cur = conn.execute("PRAGMA table_info(log_state)")
    columns = {row[1]: row[2] for row in cur}
    if "total_lines" not in columns:
        conn.execute("ALTER TABLE log_state ADD COLUMN total_lines INTEGER NOT NULL DEFAULT 0")
    # Migrate: add file_head if missing
    if "file_head" not in columns:
        conn.execute("ALTER TABLE log_state ADD COLUMN file_head TEXT NOT NULL DEFAULT ''")
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
                file_head    TEXT NOT NULL DEFAULT '',
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
    """Return {filepath: {last_line, last_size, file_head}} for the service."""
    cur = conn.execute(
        "SELECT filepath, last_line, last_size, file_head FROM log_state WHERE service = ?",
        (service,),
    )
    return {row[0]: {"last_line": row[1], "last_size": row[2], "file_head": row[3]} for row in cur}


HEAD_LINES = 10  # Number of head lines to store for rotation detection

# Pattern to match logrotate generation files: name.log.N or name.log.N.gz
ROTATE_GEN_RE = re.compile(r"^(.+\.log)\.(\d+)(\.gz)?$")


def read_file_lines(path: Path) -> list[str]:
    """Read lines from a plain or gzip file."""
    try:
        if path.suffix == ".gz":
            with gzip.open(path, "rt", errors="replace") as f:
                return f.readlines()
        else:
            with open(path, "r", errors="replace") as f:
                return f.readlines()
    except (OSError, IOError, gzip.BadGzipFile) as e:
        print(f"Warning: cannot read {path}: {e}", file=sys.stderr)
        return []


MAX_HEAD_BYTES = 4096  # Cap head text to avoid SQLite "string or blob too big"


def get_file_head(lines: list[str], n: int = HEAD_LINES) -> str:
    """Return first n lines joined as a single string for comparison, capped at MAX_HEAD_BYTES."""
    head = "".join(lines[:n])
    if len(head) > MAX_HEAD_BYTES:
        head = head[:MAX_HEAD_BYTES]
    return head


def find_rotated_generations(log_dir: Path, base_rel: str) -> list[tuple[int, Path]]:
    """Find all rotated generations for a base log file.

    Returns sorted list of (generation_number, path), e.g. [(1, .log.1.gz), (2, .log.2.gz)].
    Lower generation number = more recent.
    """
    base_path = log_dir / base_rel
    parent = base_path.parent
    generations = []
    if not parent.is_dir():
        return generations
    for f in parent.iterdir():
        if not f.is_file():
            continue
        rel = str(f.relative_to(log_dir))
        m = ROTATE_GEN_RE.match(rel)
        if m and m.group(1) == base_rel:
            gen_num = int(m.group(2))
            generations.append((gen_num, f))
    return sorted(generations, key=lambda x: x[0])


def is_logrotate_target(log_dir: Path, rel_path: str) -> bool:
    """Check if a file is a logrotate generation file (e.g. .log.1.gz)."""
    return ROTATE_GEN_RE.match(rel_path) is not None


def extract_service(service: str, keep_files: set[str] | None = None) -> None:
    log_dir = Path(LOG_BASE)
    work_dir = Path(WORK_BASE)

    if not log_dir.is_dir():
        print(f"Log directory not found: {log_dir}", file=sys.stderr)
        sys.exit(1)

    # Clean previous work files (keep specified files)
    if keep_files is None:
        keep_files = {"analyze.log", "claude_stream.jsonl"}
    if work_dir.exists():
        for f in work_dir.rglob("*"):
            if f.is_file() and f.name not in keep_files:
                f.unlink()
    work_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    state = get_state(conn, service)
    conn.close()

    state_entries = []
    total_extracted = 0

    # Walk all log files (skip logrotate generation files — handled via base file)
    for log_file in sorted(log_dir.rglob("*")):
        if not log_file.is_file():
            continue

        # Stop if we've hit the max lines limit
        if MAX_LINES > 0 and total_extracted >= MAX_LINES:
            break

        rel_path = str(log_file.relative_to(log_dir))

        # Skip logrotate generation files; they are processed when their base file is encountered
        if is_logrotate_target(log_dir, rel_path):
            continue

        # Filter by glob pattern if specified
        if FILE_PATTERN and not fnmatch.fnmatch(rel_path, FILE_PATTERN):
            continue

        file_size = log_file.stat().st_size
        prev = state.get(rel_path)

        if prev is not None:
            current_lines = read_file_lines(log_file)
            if not current_lines:
                continue
            actual_total = len(current_lines)
            prev_head = prev.get("file_head", "")
            current_head = get_file_head(current_lines)

            # Determine if rotation/reset occurred
            head_ok = prev_head and current_head == prev_head
            size_ok = file_size >= prev["last_size"]
            lines_ok = actual_total >= prev["last_line"]

            # Determine head status string for logging
            if not prev_head:
                head_status = "head=N/A(no prev)"
            elif current_head == prev_head:
                head_status = "head=match"
            else:
                head_status = "head=MISMATCH"

            if head_ok and size_ok:
                # No rotation — normal incremental extraction
                new_lines, processed_up_to = _extract_incremental(
                    current_lines, prev["last_line"]
                )
                print(
                    f"  {rel_path}: {head_status}, no rotation, "
                    f"lines {prev['last_line']}->{actual_total}, "
                    f"extracting {len(new_lines)} lines"
                )
            else:
                # Rotation or reset detected — check for logrotate generations
                generations = find_rotated_generations(log_dir, rel_path)

                if generations and prev_head:
                    # Search generations for previous head
                    gen_names = [f".{g[0]}{'.gz' if g[1].suffix == '.gz' else ''}" for g in generations]
                    print(
                        f"  {rel_path}: {head_status}, rotation detected, "
                        f"generations={gen_names}"
                    )

                    if MAX_LINES > 0:
                        print(
                            f"    -> MAX_LINES={MAX_LINES} is set, skipping generation search, "
                            f"reading current file from beginning",
                            file=sys.stderr,
                        )
                        new_lines = current_lines
                        processed_up_to = actual_total
                    else:
                        matched_gen = None
                        matched_lines = None
                        for gen_num, gen_path in generations:
                            gen_lines = read_file_lines(gen_path)
                            gen_head = get_file_head(gen_lines)
                            if gen_head == prev_head:
                                matched_gen = gen_num
                                matched_lines = gen_lines
                                break

                        if matched_lines is not None:
                            # Concatenate: matched_gen (from last_line) + newer gens + current
                            remaining_in_gen = len(matched_lines) - prev["last_line"]
                            combined = matched_lines[prev["last_line"]:]
                            newer_gens_lines = 0
                            for gen_num, gen_path in generations:
                                if gen_num < matched_gen:
                                    gl = read_file_lines(gen_path)
                                    newer_gens_lines += len(gl)
                                    combined.extend(gl)
                            combined.extend(current_lines)
                            new_lines = combined
                            print(
                                f"    -> matched generation .{matched_gen}, "
                                f"prev_last_line={prev['last_line']}, "
                                f"remaining_in_gen={remaining_in_gen}, "
                                f"newer_gens_lines={newer_gens_lines}, "
                                f"current_lines={len(current_lines)}, "
                                f"total_extracting={len(new_lines)}"
                            )
                        else:
                            new_lines = current_lines
                            print(
                                f"    -> no matching generation, starting fresh, "
                                f"extracting {len(new_lines)} lines"
                            )

                        processed_up_to = len(current_lines)
                else:
                    # No generations or no prev head — simple reset
                    print(
                        f"  {rel_path}: {head_status}, reset (size {prev['last_size']}->{file_size}, "
                        f"lines {prev['last_line']}->{actual_total}), "
                        f"reading from beginning, extracting {actual_total} lines"
                        f"{' (no logrotate generations found)' if not generations else ''}"
                    )
                    new_lines = current_lines
                    processed_up_to = actual_total
        else:
            # --- First time seeing this file ---
            current_lines = read_file_lines(log_file)
            if not current_lines:
                continue
            actual_total = len(current_lines)
            new_lines = current_lines
            processed_up_to = actual_total
            print(f"  {rel_path}: new file, extracting {len(new_lines)} lines")

        if not new_lines:
            continue

        # Cap lines if max limit is set (only for non-generation files)
        if MAX_LINES > 0:
            remaining = MAX_LINES - total_extracted
            if len(new_lines) > remaining:
                new_lines = new_lines[:remaining]
                # For non-rotated files, adjust processed_up_to
                if not generations or prev is None or not prev.get("file_head"):
                    start = prev["last_line"] if prev and file_size >= prev["last_size"] else 0
                    processed_up_to = start + len(new_lines)

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
                "file_head": get_file_head(current_lines),
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


def _extract_incremental(lines: list[str], start_line: int) -> tuple[list[str], int]:
    """Extract lines from start_line onward. Returns (new_lines, processed_up_to)."""
    actual_total = len(lines)
    if start_line >= actual_total:
        return [], actual_total
    return lines[start_line:], actual_total


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <service_name>", file=sys.stderr)
        sys.exit(1)

    service = sys.argv[1]
    extract_service(service)


if __name__ == "__main__":
    main()
