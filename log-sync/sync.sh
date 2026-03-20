#!/bin/bash
set -euo pipefail

if [ -x /usr/local/bin/ssh-askpass.sh ]; then
  export SSH_ASKPASS=/usr/local/bin/ssh-askpass.sh
  export SSH_ASKPASS_REQUIRE=force
fi

PORT="${SSH_PORT:-22}"
DEST="/data/logs/${RSYNC_DEST}"

mkdir -p "${DEST}"

echo "[$(date -Iseconds)] Starting rsync: ${RSYNC_SRC} -> ${DEST}"

rsync -avz --delete \
  -e "ssh -i /root/.ssh/id_rsa -p ${PORT}" \
  "${RSYNC_SRC}" "${DEST}/"

echo "[$(date -Iseconds)] Sync complete"
