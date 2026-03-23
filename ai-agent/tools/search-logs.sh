#!/bin/bash
set -euo pipefail

# Search extracted log files for errors/warnings with surrounding context.
# Usage: search-logs.sh <directory> [context_lines] [pattern]

DIR="${1:?Usage: search-logs.sh <dir> [context_lines] [pattern]}"
CONTEXT="${2:-100}"
PATTERN="${3:-error|warning|fatal|exception|critical}"

if [ ! -d "${DIR}" ]; then
  echo "Directory not found: ${DIR}" >&2
  exit 1
fi

# Exclude _state.json from search
grep -r -i -n -C "${CONTEXT}" -E "${PATTERN}" "${DIR}" \
  --exclude="_state.json" \
  2>/dev/null || echo "No matches found for pattern: ${PATTERN}"
