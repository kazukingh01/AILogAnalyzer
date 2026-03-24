#!/bin/bash
set -euo pipefail

# Wrapper script for systemd to run ai-agent analysis.
# Called by ailog-agent-*.service with EnvironmentFile loaded.
# Usage: run-agent.sh <service_name> <max_lines>

SERVICE_NAME="${1:?Usage: run-agent.sh <service_name> <max_lines>}"
MAX_LINES="${2:?Usage: run-agent.sh <service_name> <max_lines>}"

ARGS="--max-lines ${MAX_LINES}"
if [ -n "${DISCORD_MENTION:-}" ]; then
  ARGS="${ARGS} --mention ${DISCORD_MENTION}"
fi

exec /usr/bin/docker exec -t "ailog-agent-${SERVICE_NAME}" /tools/analyze.sh ${ARGS}
