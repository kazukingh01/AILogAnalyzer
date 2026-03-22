#!/bin/bash
set -euo pipefail
python3 /tools/status.py "${SERVICE_NAME:-}" "$@"
