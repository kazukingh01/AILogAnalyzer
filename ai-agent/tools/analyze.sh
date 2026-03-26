#!/bin/bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:?SERVICE_NAME is not set}"

LOG_FILE="/data/work/analyze.log"
STREAM_LOG="/data/work/claude_stream.jsonl"
mkdir -p "$(dirname "${LOG_FILE}")"

# Clear logs from previous run
: > "${LOG_FILE}"
: > "${STREAM_LOG}"

log() {
  local msg="[$(date -Iseconds)] $*"
  echo "${msg}"
  echo "${msg}" >> "${LOG_FILE}"
}

log "Starting analysis for service: ${SERVICE_NAME}"

# Parse arguments
usage() {
  echo "Usage: analyze.sh --max-lines <N> [--mention <mention>] [--pattern <glob>]" >&2
  exit 1
}

MAX_EXTRACT_LINES=""
MENTION=""
LOG_FILE_PATTERN=""

while [ $# -gt 0 ]; do
  case "$1" in
    --max-lines) MAX_EXTRACT_LINES="${2:?--max-lines requires a value}"; shift 2 ;;
    --mention)   MENTION="${2:?--mention requires a value}"; shift 2 ;;
    --pattern)   LOG_FILE_PATTERN="${2:?--pattern requires a value}"; shift 2 ;;
    *)           usage ;;
  esac
done

if [ -z "${MAX_EXTRACT_LINES}" ]; then
  usage
fi

log "Args: max_lines=${MAX_EXTRACT_LINES}, mention=$(if [ -n "${MENTION}" ]; then echo "xxxx${MENTION: -4}"; else echo none; fi), pattern=${LOG_FILE_PATTERN:-'(all)'}"

# 1. Extract unanalyzed log portions
export MAX_EXTRACT_LINES
export LOG_FILE_PATTERN="${LOG_FILE_PATTERN:-*.log}"

log "Step 1: Extracting unanalyzed logs (max_lines: ${MAX_EXTRACT_LINES})"
python3 /tools/extract.py "${SERVICE_NAME}" 2>&1 | tee -a "${LOG_FILE}" || {
  log "extract.py failed"
  exit 1
}

# Check if there are any extracted files from _state.json
WORK_DIR="/data/work"
FILE_COUNT=$(python3 -c "import json; print(len(json.load(open('${WORK_DIR}/_state.json'))['files']))" 2>/dev/null || echo 0)

if [ "${FILE_COUNT}" -eq 0 ]; then
  log "No new logs to analyze"
  /tools/notify-discord.sh "[${SERVICE_NAME}] 新規ログなし。異常なし。" || log "Discord notification failed (ignored)"
  python3 /tools/commit.py "${SERVICE_NAME}" 2>&1 | tee -a "${LOG_FILE}"
  exit 0
fi

# 2. Pre-scan for errors/warnings
SEARCH_RESULT="/data/work/_search_result.txt"
log "Step 2: Pre-scanning logs with search-logs.sh + summarize-logs.py"
/tools/search-logs.sh "${WORK_DIR}" 2>/dev/null | python3 /tools/summarize-logs.py - > "${SEARCH_RESULT}" 2>&1 || true
log "Search result: $(wc -l < "${SEARCH_RESULT}") lines"

# 3. Run Claude analysis
log "Step 3: Running Claude analysis (${FILE_COUNT} files)"
claude -p "Analyze the log files for service '${SERVICE_NAME}'. Follow the instructions in CLAUDE.md." \
  --model sonnet \
  --dangerously-skip-permissions \
  --max-turns 30 \
  --output-format stream-json \
  --verbose \
  > "${STREAM_LOG}" || {
  log "AI analysis failed for ${SERVICE_NAME}"
  /tools/notify-discord.sh "ERROR: AI analysis failed for ${SERVICE_NAME}" || true
  exit 1
}

# Extract final result and usage from stream
# Use slurp to get the last "result" record as a whole (not last line)
RESULT=$(jq -s -r '[.[] | select(.type == "result")] | last | .result' "${STREAM_LOG}" 2>/dev/null)
if [ -z "${RESULT}" ] || [ "${RESULT}" = "null" ]; then
  RESULT=$(jq -s -r '[.[] | select(.message?.role == "assistant") | .message.content[]? | select(.type == "text") | .text] | last' "${STREAM_LOG}" 2>/dev/null)
fi

# Extract only content after "=== REPORT ===" marker
if echo "${RESULT}" | grep -q "=== REPORT ==="; then
  RESULT=$(echo "${RESULT}" | sed -n '/=== REPORT ===/,$ p' | tail -n +2)
fi

# Log cost and token usage
COST_DETAIL=$(jq -r 'select(.type == "result") | {cost_usd: .total_cost_usd, turns: .num_turns, duration_ms: .duration_ms, session_id: .session_id}' "${STREAM_LOG}" 2>/dev/null | tail -1)
log "Usage: ${COST_DETAIL}"

# 4. Send report to Discord (mention if issues detected)
log "Step 4: Sending report to Discord"
DISCORD_MSG="${RESULT}"
if [ -n "${MENTION}" ] && ! echo "${RESULT}" | head -n 1 | grep -q '^\[OK\]'; then
  DISCORD_MSG="${MENTION} ${RESULT}"
fi
/tools/notify-discord.sh "${DISCORD_MSG}" || log "Discord notification failed (ignored)"

# 5. Commit state (only on success — failed analysis will retry next run)
log "Step 5: Committing state"
python3 /tools/commit.py "${SERVICE_NAME}" 2>&1 | tee -a "${LOG_FILE}"

# 6. Send analysis progress to Discord
log "Step 6: Sending progress to Discord"
STATUS=$(python3 /tools/status.py "${SERVICE_NAME}" 2>&1) || true
/tools/notify-discord.sh "[${SERVICE_NAME}] 解析進捗:
\`\`\`
${STATUS}
\`\`\`" || log "Discord progress notification failed (ignored)"

log "Done"
