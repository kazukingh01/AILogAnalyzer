#!/bin/bash
set -euo pipefail

# Link CLAUDE.md to home directory
ln -sf /tools/CLAUDE.md /home/claude/CLAUDE.md

exec sleep infinity
