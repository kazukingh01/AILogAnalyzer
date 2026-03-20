#!/bin/bash
set -euo pipefail

WEBHOOK_URL="${DISCORD_WEBHOOK_URL:?DISCORD_WEBHOOK_URL is not set}"
MESSAGE="${1:?Usage: notify-discord.sh <message>}"

# Truncate to Discord's 2000 char limit (leave room for formatting)
if [ ${#MESSAGE} -gt 1990 ]; then
  MESSAGE="${MESSAGE:0:1987}..."
fi

# Use jq for safe JSON escaping
PAYLOAD=$(jq -n --arg content "${MESSAGE}" '{"content": $content}')

curl -s -o /dev/null -w "%{http_code}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" \
  "${WEBHOOK_URL}" | {
  read -r HTTP_CODE
  if [ "${HTTP_CODE}" -ge 400 ]; then
    echo "[$(date -Iseconds)] Discord webhook failed with HTTP ${HTTP_CODE}" >&2
    exit 1
  fi
  echo "[$(date -Iseconds)] Discord notification sent (HTTP ${HTTP_CODE})"
}
