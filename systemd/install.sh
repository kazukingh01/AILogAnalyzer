#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing systemd units..."
cp "${SCRIPT_DIR}"/ailog-*.service "${SCRIPT_DIR}"/ailog-*.timer /etc/systemd/system/

echo "Reloading systemd..."
systemctl daemon-reload

echo "Enabling and starting timers..."
systemctl enable --now ailog-sync-webserver.timer
systemctl enable --now ailog-agent.timer

echo "Done. Check status with: systemctl list-timers ailog-*"
