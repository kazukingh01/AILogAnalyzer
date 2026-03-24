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

RESPONSE=$(mktemp)
HTTP_CODE=$(curl -s -o "${RESPONSE}" -w "%{http_code}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" \
  "${WEBHOOK_URL}")

if [ "${HTTP_CODE}" -ge 400 ]; then
  BODY=$(cat "${RESPONSE}")
  echo "[$(date -Iseconds)] Discord webhook failed: HTTP ${HTTP_CODE} body=${BODY} msg_length=${#MESSAGE}" >&2
  rm -f "${RESPONSE}"
  exit 1
fi

echo "[$(date -Iseconds)] Discord notification sent (HTTP ${HTTP_CODE})"
rm -f "${RESPONSE}"
