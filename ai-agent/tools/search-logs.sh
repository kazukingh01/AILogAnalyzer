#!/bin/bash
set -euo pipefail

# Search extracted log files for errors/warnings with surrounding context.
# Two-tier grep: case-insensitive for high-confidence keywords,
# case-sensitive with word boundaries for noisy keywords.
# Usage: search-logs.sh <directory> [context_lines]

DIR="${1:?Usage: search-logs.sh <dir> [context_lines]}"
CONTEXT="${2:-10}"

if [ ! -d "${DIR}" ]; then
  echo "Directory not found: ${DIR}" >&2
  exit 1
fi

EXCLUDE="--exclude=_state.json --exclude=_search_result.txt"

# Tier 1: High-confidence keywords (case-insensitive)
PATTERN_NOCASE="fatal|exception|critical|panic|emergency|severe|traceback|segfault|segmentation fault|out of memory|oom"

# Tier 2: Case-sensitive with word boundaries to avoid matching variable names
PATTERN_BOUNDARY="\b(ERROR|WARN(ING)?|ALERT)\b|connection refused|permission denied|timed? ?out|\babort(ed)?\b|\bfail(ed|ure|ing)\b|\bkilled\b"

{
  grep -r -i -n -C "${CONTEXT}" -E "${PATTERN_NOCASE}" "${DIR}" ${EXCLUDE} 2>/dev/null || true
  grep -r -n -C "${CONTEXT}" -E "${PATTERN_BOUNDARY}" "${DIR}" ${EXCLUDE} 2>/dev/null || true
} | sort -t: -k1,1 -k2,2n | uniq

# Exit 0 even if no matches (empty output = no issues)
exit 0
