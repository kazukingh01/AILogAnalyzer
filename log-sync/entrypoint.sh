#!/bin/bash
set -euo pipefail

# SSH key setup
mkdir -p /root/.ssh
SSH_KEY_FILE="${SSH_KEY_FILE:-/run/secrets/ssh_private_key}"
cp "${SSH_KEY_FILE}" /root/.ssh/id_rsa
chmod 600 /root/.ssh/id_rsa

# Extract host and port for ssh-keyscan
HOST=$(echo "${RSYNC_SRC}" | cut -d@ -f2 | cut -d: -f1)
PORT="${SSH_PORT:-22}"
ssh-keyscan -p "${PORT}" "${HOST}" >> /root/.ssh/known_hosts 2>/dev/null

# Read passphrase from secrets file or environment variable
if [ -n "${SSH_PASSPHRASE_FILE:-}" ] && [ -f "${SSH_PASSPHRASE_FILE}" ]; then
  SSH_PASSPHRASE=$(cat "${SSH_PASSPHRASE_FILE}")
fi

# Create SSH_ASKPASS helper only if passphrase is provided
if [ -n "${SSH_PASSPHRASE:-}" ]; then
  printf '%s\n' "${SSH_PASSPHRASE}" > /usr/local/bin/.ssh_passphrase
  chmod 600 /usr/local/bin/.ssh_passphrase
  cat > /usr/local/bin/ssh-askpass.sh << 'SCRIPT'
#!/bin/bash
cat /usr/local/bin/.ssh_passphrase
SCRIPT
  chmod +x /usr/local/bin/ssh-askpass.sh
fi

exec /usr/local/bin/sync.sh
