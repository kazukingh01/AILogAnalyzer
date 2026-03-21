#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing systemd units..."
cp "${SCRIPT_DIR}"/ailog-*.service "${SCRIPT_DIR}"/ailog-*.timer /etc/systemd/system/

echo "Reloading systemd..."
systemctl daemon-reload

echo "Enabling and starting timers..."
systemctl enable --now ailog-sync-webserver.timer

# Enable ai-agent timers per service (add more as needed)
# Usage: systemctl enable --now ailog-agent@service-a.timer
echo ""
echo "To enable ai-agent for a service, run:"
echo "  systemctl enable --now ailog-agent@<service-name>.timer"
echo ""
echo "Example:"
echo "  systemctl enable --now ailog-agent@service-a.timer"
echo "  systemctl enable --now ailog-agent@service-b.timer"
echo ""
echo "Check status with: systemctl list-timers ailog-*"
