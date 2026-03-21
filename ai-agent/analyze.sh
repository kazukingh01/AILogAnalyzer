#!/bin/bash
set -euo pipefail

LOG_BASE_DIR="${LOG_BASE_DIR:-/data/logs}"

PROMPT="Analyze the log files under ${LOG_BASE_DIR}. Focus on files changed within the last 24 hours. Identify errors, warnings, and anomalous patterns. Provide a concise summary within 1900 characters."

echo "[$(date -Iseconds)] Starting AI log analysis"

RESULT=$(claude -p "${PROMPT}" \
  --dangerously-skip-permissions \
  --max-turns 10 \
  --output-format text \
  2>&1) || {
  ERROR_MSG="AI analysis failed: ${RESULT}"
  echo "[$(date -Iseconds)] ${ERROR_MSG}" >&2
  /usr/local/bin/notify-discord.sh "ERROR: ${ERROR_MSG}"
  exit 1
}

echo "[$(date -Iseconds)] Analysis complete, sending to Discord"
/usr/local/bin/notify-discord.sh "${RESULT}"
echo "[$(date -Iseconds)] Done"
