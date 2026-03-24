#!/usr/bin/env python3
"""Summarize grep output (from search-logs.sh) by deduplicating with
progressive context expansion in a hierarchical (parent-child) structure.

Parses grep -n -C output (filepath:lineno:content), groups matches per file,
masks dates/IDs, then deduplicates:
1. Group by match line (position MID) → base groups
2. Expand context progressively (left then right)
   - If expansion produces 1 type with same count → promote as new base
   - If sub-types <= base_count/5 → adopt (useful differentiation)
   - Otherwise → stop expanding
3. Output as hierarchical tree: base summary, then sub-groups indented

Usage: summarize-logs.py <grep_output_file>
       search-logs.sh /data/work | summarize-logs.py -
"""

import re
import sys
from collections import defaultdict

CONTEXT = 3
MID = CONTEXT  # match line index in context window (0-based)
WINDOW = 2 * CONTEXT + 1  # 11

# Two-tier patterns (matching search-logs.sh)
PATTERN_NOCASE = re.compile(
    r"fatal|exception|critical|panic|emergency|severe|traceback|"
    r"segfault|segmentation fault|out of memory|oom",
    re.IGNORECASE,
)
PATTERN_CASE = re.compile(
    r"\b(?:ERROR|WARN(?:ING)?|ALERT)\b|connection refused|permission denied|"
    r"timed? ?out|\babort(?:ed)?\b|\bfail(?:ed|ure|ing)\b|\bkilled\b"
)
# Note: summarize-logs.py always recognizes WARNING in its matching logic
# so it can handle both --include-warning and default grep output correctly.

# Masking rules (order matters: dates before generic numbers)
MASK_RULES = [
    (re.compile(r"\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}[.,]?\d*\S*"), "<DATE>"),
    (re.compile(r"\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2}"), "<DATE>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<UUID>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<HEX>"),
    (re.compile(r"\b\d+\.\d+"), "<N>"),
    (re.compile(r"\b\d+"), "<N>"),
    (re.compile(r"\S{40,}"), "<LONG>"),
]

# Parse grep output line: filepath:lineno:content or filepath-lineno-content
GREP_LINE_RE = re.compile(r"^(.+?)[:-](\d+)[:-](.*)$")


def is_match(line: str) -> bool:
    return bool(PATTERN_NOCASE.search(line) or PATTERN_CASE.search(line))


def mask(text: str) -> str:
    for pat, repl in MASK_RULES:
        text = pat.sub(repl, text)
    return text


def parse_grep_output(lines: list[str]) -> dict[str, dict[int, str]]:
    """Parse grep output into {filepath: {lineno: content}}."""
    file_lines: dict[str, dict[int, str]] = defaultdict(dict)
    for line in lines:
        line = line.rstrip("\n")
        if line == "--":
            continue
        m = GREP_LINE_RE.match(line)
        if not m:
            continue
        filepath, lineno_str, content = m.group(1), m.group(2), m.group(3)
        file_lines[filepath][int(lineno_str)] = content
    return dict(file_lines)


def build_matches(file_lines: dict[int, str]) -> list[dict]:
    """Find keyword-matching lines, merge nearby matches into one block,
    and build context windows using the first match as representative."""
    match_lines = sorted(
        lineno for lineno, content in file_lines.items() if is_match(content)
    )
    if not match_lines:
        return []

    # Merge nearby matches (within CONTEXT lines) into blocks
    blocks: list[list[int]] = []
    current_block: list[int] = [match_lines[0]]
    for lineno in match_lines[1:]:
        if lineno - current_block[-1] <= CONTEXT:
            current_block.append(lineno)
        else:
            blocks.append(current_block)
            current_block = [lineno]
    blocks.append(current_block)

    # Use first match line of each block as representative
    matches = []
    for block in blocks:
        rep = block[0]
        context = []
        for offset in range(-CONTEXT, CONTEXT + 1):
            target = rep + offset
            context.append(file_lines.get(target, ""))

        matches.append({
            "line_no": rep,
            "context": context,
            "masked": [mask(l) for l in context],
        })

    return matches


def group_by_key(members: list[dict], positions: list[int]) -> dict[str, list[dict]]:
    """Group members by concatenation of masked lines at given positions."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for m in members:
        key = "\n".join(m["masked"][p] for p in positions)
        groups[key].append(m)
    return dict(groups)


def fmt_lines(line_nos: list[int], total: int) -> str:
    s = ",".join(str(n) for n in line_nos[:5])
    if total > 5:
        s += f"...(+{total - 5})"
    return s


def expand_and_build_tree(members: list[dict], base_key: str) -> dict:
    """Expand context for a base group and build hierarchical result.

    Returns a tree node:
      { key, count, total, line_nos, children: [tree_node, ...] }
    Children are only present when expansion produced useful sub-groups.
    """
    base_count = len(members)
    all_line_nos = [m["line_no"] for m in members]

    node = {
        "key": base_key,
        "count": base_count,
        "total": base_count,
        "line_nos": all_line_nos[:5],
        "children": [],
    }

    current = [MID]

    # Try expanding left
    for left in range(MID - 1, -1, -1):
        test = [left] + current
        subs = group_by_key(members, test)
        n_types = len(subs)

        if n_types == 1 and len(next(iter(subs.values()))) == base_count:
            # Consistent context → promote as new base
            current = test
            node["key"] = next(iter(subs.keys()))
        elif n_types <= max(1, base_count // 5):
            # Useful differentiation → adopt and record children
            current = test
        else:
            break

    # Try expanding right
    for right in range(MID + 1, WINDOW):
        test = current + [right]
        subs = group_by_key(members, test)
        n_types = len(subs)

        if n_types == 1 and len(next(iter(subs.values()))) == base_count:
            current = test
            node["key"] = next(iter(subs.keys()))
        elif n_types <= max(1, base_count // 5):
            current = test
        else:
            break

    # Build children from final expanded positions
    final_subs = group_by_key(members, current)
    if len(final_subs) > 1:
        # Multiple sub-groups: record as children
        for sub_key, sub_members in final_subs.items():
            sub_line_nos = [m["line_no"] for m in sub_members]
            node["children"].append({
                "key": sub_key,
                "count": len(sub_members),
                "total": len(sub_members),
                "line_nos": sub_line_nos[:5],
            })
        node["children"].sort(key=lambda x: x["count"], reverse=True)
    else:
        # Single group after expansion: update key to include full context
        only_key = next(iter(final_subs.keys()))
        node["key"] = only_key

    return node


def summarize_matches(matches: list[dict]) -> list[dict]:
    """Deduplicate matches into hierarchical tree nodes."""
    if not matches:
        return []

    # Group by match line only (base)
    base_groups = group_by_key(matches, [MID])

    trees = []
    for base_key, members in base_groups.items():
        tree = expand_and_build_tree(members, base_key)
        trees.append(tree)

    trees.sort(key=lambda x: x["count"], reverse=True)
    return trees


def print_tree(tree: dict, indent: str = "  ") -> None:
    """Print a tree node with optional children."""
    print(f"{indent}[{tree['count']}x] lines:{fmt_lines(tree['line_nos'], tree['total'])}")
    for line in tree["key"].split("\n"):
        print(f"{indent}  | {line}")

    if tree.get("children"):
        for child in tree["children"]:
            print(f"{indent}  [{child['count']}x] lines:{fmt_lines(child['line_nos'], child['total'])}")
            # Show only lines that differ from parent
            parent_lines = tree["key"].split("\n")
            child_lines = child["key"].split("\n")
            for cl in child_lines:
                if cl not in parent_lines:
                    print(f"{indent}    + {cl}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: summarize-logs.py <grep_output_file>", file=sys.stderr)
        print("       search-logs.sh /data/work | summarize-logs.py -", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    if input_path == "-":
        raw_lines = sys.stdin.readlines()
    else:
        with open(input_path, errors="replace") as f:
            raw_lines = f.readlines()

    file_lines = parse_grep_output(raw_lines)

    for filepath in sorted(file_lines.keys()):
        matches = build_matches(file_lines[filepath])
        trees = summarize_matches(matches)
        if not trees:
            continue

        print(f"=== {filepath} ===")
        for tree in trees:
            print_tree(tree)
        print()


if __name__ == "__main__":
    main()
