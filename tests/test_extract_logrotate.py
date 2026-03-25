#!/usr/bin/env python3
"""Tests for logrotate support in extract.py."""

import gzip
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# Add tools dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ai-agent" / "tools"))

import extract


def setup_env(tmp: Path):
    """Set up test directories and patch extract module paths."""
    log_dir = tmp / "logs"
    work_dir = tmp / "work"
    db_path = tmp / "db.sqlite"
    log_dir.mkdir()
    work_dir.mkdir()

    extract.LOG_BASE = str(log_dir)
    extract.WORK_BASE = str(work_dir)
    extract.DB_PATH = str(db_path)
    extract.MAX_LINES = 0

    return log_dir, work_dir, db_path


def init_state(db_path: Path, service: str, filepath: str, last_line: int,
               total_lines: int, last_size: int, file_head: str = ""):
    """Insert a state row into the database."""
    conn = sqlite3.connect(str(db_path))
    extract.init_db(conn)
    conn.execute(
        "INSERT OR REPLACE INTO log_state (service, filepath, last_line, total_lines, last_size, updated_at, file_head) "
        "VALUES (?, ?, ?, ?, ?, 0, ?)",
        (service, filepath, last_line, total_lines, last_size, file_head),
    )
    conn.commit()
    conn.close()


def test_normal_extraction_no_rotation():
    """Normal file (no .gz generations) — should work as before."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        log_dir, work_dir, db_path = setup_env(tmp)

        # Create log file
        lines = [f"line {i}\n" for i in range(100)]
        log_file = log_dir / "app.log"
        log_file.write_text("".join(lines))

        # First extraction — all lines
        extract.extract_service("test")

        state = json.loads((work_dir / "_state.json").read_text())
        assert len(state["files"]) == 1
        assert state["files"][0]["last_line"] == 100
        assert state["files"][0]["file_head"] == "".join(lines[:10])

        out = (work_dir / "app.log").read_text()
        assert out == "".join(lines)

        print("PASS: test_normal_extraction_no_rotation")


def test_normal_incremental():
    """Normal incremental extraction (file grew, no rotation)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        log_dir, work_dir, db_path = setup_env(tmp)

        lines_v1 = [f"line {i}\n" for i in range(50)]
        log_file = log_dir / "app.log"
        log_file.write_text("".join(lines_v1))
        head_text = "".join(lines_v1[:10])

        init_state(db_path, "test", "app.log",
                   last_line=50, total_lines=50,
                   last_size=log_file.stat().st_size, file_head=head_text)

        # Append more lines (head stays the same)
        lines_v2 = [f"new line {i}\n" for i in range(20)]
        log_file.write_text("".join(lines_v1 + lines_v2))

        extract.extract_service("test")

        state = json.loads((work_dir / "_state.json").read_text())
        assert state["files"][0]["last_line"] == 70
        out = (work_dir / "app.log").read_text()
        assert out == "".join(lines_v2)

        print("PASS: test_normal_incremental")


def test_logrotate_detection_and_generation_search():
    """Rotation detected, previous head found in .1.gz → concatenate."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        log_dir, work_dir, db_path = setup_env(tmp)

        # Previous state: app.log had 100 lines, analyzed up to line 80
        prev_lines = [f"old line {i}\n" for i in range(100)]
        prev_head = "".join(prev_lines[:10])

        # After rotation: old content moved to .1.gz, new content in app.log
        new_lines = [f"new line {i}\n" for i in range(30)]

        # Write current app.log (new content after rotation)
        log_file = log_dir / "app.log"
        log_file.write_text("".join(new_lines))

        # Write .1.gz with previous content
        gz_path = log_dir / "app.log.1.gz"
        with gzip.open(gz_path, "wt") as f:
            f.writelines(prev_lines)

        # Set previous state (analyzed up to line 80 of 100)
        # Use a fake last_size larger than current to trigger rotation detection
        init_state(db_path, "test", "app.log",
                   last_line=80, total_lines=100,
                   last_size=999999, file_head=prev_head)

        extract.extract_service("test")

        state = json.loads((work_dir / "_state.json").read_text())
        assert len(state["files"]) == 1
        entry = state["files"][0]
        # State should record current file's info
        assert entry["last_line"] == len(new_lines)
        assert entry["file_head"] == "".join(new_lines[:10])

        # Output should contain: old lines 80-99 + all new lines
        out = (work_dir / "app.log").read_text()
        expected = "".join(prev_lines[80:]) + "".join(new_lines)
        assert out == expected, f"Expected {len(expected)} chars, got {len(out)}"

        print("PASS: test_logrotate_detection_and_generation_search")


def test_logrotate_no_match_starts_fresh():
    """Rotation detected but no generation matches → start fresh."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        log_dir, work_dir, db_path = setup_env(tmp)

        # Previous head that won't match anything
        prev_head = "this head will not match\n" * 10

        new_lines = [f"fresh line {i}\n" for i in range(50)]
        log_file = log_dir / "app.log"
        log_file.write_text("".join(new_lines))

        # .1.gz with different content
        gz_lines = [f"unrelated {i}\n" for i in range(40)]
        gz_path = log_dir / "app.log.1.gz"
        with gzip.open(gz_path, "wt") as f:
            f.writelines(gz_lines)

        init_state(db_path, "test", "app.log",
                   last_line=30, total_lines=40,
                   last_size=999999, file_head=prev_head)

        extract.extract_service("test")

        state = json.loads((work_dir / "_state.json").read_text())
        entry = state["files"][0]
        assert entry["last_line"] == 50

        # Should contain all current lines (fresh start)
        out = (work_dir / "app.log").read_text()
        assert out == "".join(new_lines)

        print("PASS: test_logrotate_no_match_starts_fresh")


def test_logrotate_multi_generation():
    """Multiple rotations: match in .2.gz, combine .2.gz + .1.gz + current."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        log_dir, work_dir, db_path = setup_env(tmp)

        # Original content (was in app.log, now in .2.gz)
        gen2_lines = [f"gen2 line {i}\n" for i in range(100)]
        gen2_head = "".join(gen2_lines[:10])

        # Content that was rotated once (now in .1.gz)
        gen1_lines = [f"gen1 line {i}\n" for i in range(80)]

        # Current content
        current_lines = [f"current line {i}\n" for i in range(40)]

        log_file = log_dir / "app.log"
        log_file.write_text("".join(current_lines))

        with gzip.open(log_dir / "app.log.1.gz", "wt") as f:
            f.writelines(gen1_lines)
        with gzip.open(log_dir / "app.log.2.gz", "wt") as f:
            f.writelines(gen2_lines)

        # Previous state: analyzed gen2 up to line 60
        init_state(db_path, "test", "app.log",
                   last_line=60, total_lines=100,
                   last_size=999999, file_head=gen2_head)

        extract.extract_service("test")

        state = json.loads((work_dir / "_state.json").read_text())
        entry = state["files"][0]
        assert entry["last_line"] == len(current_lines)
        assert entry["file_head"] == "".join(current_lines[:10])

        out = (work_dir / "app.log").read_text()
        # gen2 lines 60-99 + all gen1 + all current
        expected = "".join(gen2_lines[60:]) + "".join(gen1_lines) + "".join(current_lines)
        assert out == expected, f"Mismatch:\nExpected length: {len(expected)}\nGot length: {len(out)}"

        print("PASS: test_logrotate_multi_generation")


def test_gz_files_skipped_in_main_loop():
    """Generation .gz files should not be processed as independent files."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        log_dir, work_dir, db_path = setup_env(tmp)

        lines = [f"line {i}\n" for i in range(10)]
        (log_dir / "app.log").write_text("".join(lines))
        with gzip.open(log_dir / "app.log.1.gz", "wt") as f:
            f.writelines([f"old {i}\n" for i in range(5)])

        extract.extract_service("test")

        state = json.loads((work_dir / "_state.json").read_text())
        # Only app.log should appear, not app.log.1.gz
        filepaths = [e["filepath"] for e in state["files"]]
        assert filepaths == ["app.log"], f"Unexpected files: {filepaths}"
        assert not (work_dir / "app.log.1.gz").exists()

        print("PASS: test_gz_files_skipped_in_main_loop")


def test_first_time_with_generations():
    """First time extraction with .gz files present — only extract current file."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        log_dir, work_dir, db_path = setup_env(tmp)

        current_lines = [f"current {i}\n" for i in range(20)]
        (log_dir / "app.log").write_text("".join(current_lines))

        with gzip.open(log_dir / "app.log.1.gz", "wt") as f:
            f.writelines([f"old {i}\n" for i in range(50)])

        extract.extract_service("test")

        state = json.loads((work_dir / "_state.json").read_text())
        entry = state["files"][0]
        assert entry["last_line"] == 20
        assert entry["file_head"] == "".join(current_lines[:10])

        # Only current content should be extracted
        out = (work_dir / "app.log").read_text()
        assert out == "".join(current_lines)

        print("PASS: test_first_time_with_generations")


if __name__ == "__main__":
    test_normal_extraction_no_rotation()
    test_normal_incremental()
    test_logrotate_detection_and_generation_search()
    test_logrotate_no_match_starts_fresh()
    test_logrotate_multi_generation()
    test_gz_files_skipped_in_main_loop()
    test_first_time_with_generations()
    print("\nAll tests passed!")
