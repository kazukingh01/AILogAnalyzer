#!/bin/bash
set -euo pipefail

# Dynamically create and register a systemd timer for an ai-agent service.
# Usage: register-agent.sh <service_name> [--max-lines N] [--interval <calendar>]
# DISCORD_MENTION is read from .env

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"

SERVICE_NAME=""
MAX_LINES=0
INTERVAL="*-*-* 0/1:00:00"
PATTERN="*.log"

while [ $# -gt 0 ]; do
  case "$1" in
    --max-lines) MAX_LINES="$2"; shift 2 ;;
    --interval)  INTERVAL="$2"; shift 2 ;;
    --pattern)   PATTERN="$2"; shift 2 ;;
    -*)          echo "Unknown option: $1" >&2; exit 1 ;;
    *)           SERVICE_NAME="$1"; shift ;;
  esac
done

if [ -z "${SERVICE_NAME}" ]; then
  echo "Usage: register-agent.sh <service_name> [--max-lines N] [--interval <calendar>] [--pattern <glob>]" >&2
  echo "" >&2
  echo "Options:" >&2
  echo "  --max-lines N      Max lines to extract (default: 0 = unlimited)" >&2
  echo "  --interval <cal>   systemd OnCalendar expression (default: '*-*-* 0/1:00:00' = every 1h)" >&2
  echo "  --pattern <glob>   File pattern to extract (default: '*.log')" >&2
  echo "" >&2
  echo "DISCORD_MENTION is read from .env (e.g. DISCORD_MENTION=<@123456789>)" >&2
  exit 1
fi

UNIT_NAME="ailog-agent-${SERVICE_NAME}"

echo "Creating ${UNIT_NAME}.service ..."
cat > "/etc/systemd/system/${UNIT_NAME}.service" <<EOF
[Unit]
Description=AILogAnalyzer - AI agent log analysis (${SERVICE_NAME})
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
EnvironmentFile=${PROJECT_DIR}/.env
ExecStart=${PROJECT_DIR}/systemd/run-agent.sh ${SERVICE_NAME} ${MAX_LINES} ${PATTERN}
TimeoutStartSec=600
EOF

echo "Creating ${UNIT_NAME}.timer ..."
cat > "/etc/systemd/system/${UNIT_NAME}.timer" <<EOF
[Unit]
Description=Run AI log analysis for ${SERVICE_NAME} every ${INTERVAL}

[Timer]
OnCalendar=${INTERVAL}
Persistent=true
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now "${UNIT_NAME}.timer"

echo "Registered: ${UNIT_NAME}.timer (interval: ${INTERVAL})"
echo "Check status: systemctl list-timers ${UNIT_NAME}*"
