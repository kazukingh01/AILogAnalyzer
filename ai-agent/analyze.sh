#!/bin/bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:?SERVICE_NAME is not set}"

echo "[$(date -Iseconds)] Starting analysis for service: ${SERVICE_NAME}"

# 1. Extract unanalyzed log portions
python3 /usr/local/bin/extract.py "${SERVICE_NAME}" || {
  echo "[$(date -Iseconds)] extract.py failed" >&2
  exit 1
}

# Check if there are any extracted files (excluding _state.json)
WORK_DIR="/data/work/${SERVICE_NAME}"
FILE_COUNT=$(find "${WORK_DIR}" -type f ! -name "_state.json" 2>/dev/null | wc -l)

if [ "${FILE_COUNT}" -eq 0 ]; then
  echo "[$(date -Iseconds)] No new logs to analyze"
  /usr/local/bin/notify-discord.sh "[${SERVICE_NAME}] 新規ログなし。異常なし。"
  python3 /usr/local/bin/commit.py "${SERVICE_NAME}"
  exit 0
fi

# 2. Run Claude analysis
PROMPT="Analyze the log files for service '${SERVICE_NAME}'. Follow the instructions in CLAUDE.md."

RESULT=$(claude -p "${PROMPT}" \
  --dangerously-skip-permissions \
  --max-turns 15 \
  --output-format text \
  2>&1) || {
  ERROR_MSG="AI analysis failed for ${SERVICE_NAME}: ${RESULT}"
  echo "[$(date -Iseconds)] ${ERROR_MSG}" >&2
  /usr/local/bin/notify-discord.sh "ERROR: ${ERROR_MSG}"
  exit 1
}

# 3. Send report to Discord
echo "[$(date -Iseconds)] Analysis complete, sending to Discord"
/usr/local/bin/notify-discord.sh "[${SERVICE_NAME}] ${RESULT}"

# 4. Commit state (only on success — failed analysis will retry next run)
python3 /usr/local/bin/commit.py "${SERVICE_NAME}"

echo "[$(date -Iseconds)] Done"
