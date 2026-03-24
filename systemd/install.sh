#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"

echo "Installing systemd units (WorkingDirectory=${PROJECT_DIR})..."
for f in "${SCRIPT_DIR}"/ailog-sync.service "${SCRIPT_DIR}"/ailog-sync.timer; do
  sed "s|WorkingDirectory=.*|WorkingDirectory=${PROJECT_DIR}|" "$f" > "/etc/systemd/system/$(basename "$f")"
done

echo "Reloading systemd..."
systemctl daemon-reload

echo "Enabling and starting timers..."
systemctl enable --now ailog-sync.timer
