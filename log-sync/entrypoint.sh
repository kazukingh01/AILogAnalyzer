#!/bin/bash
set -euo pipefail

# SSH key setup
mkdir -p /root/.ssh
cp /run/secrets/ssh_private_key /root/.ssh/id_rsa
chmod 600 /root/.ssh/id_rsa

# Extract host and port for ssh-keyscan
HOST=$(echo "${RSYNC_SRC}" | cut -d@ -f2 | cut -d: -f1)
PORT="${SSH_PORT:-22}"
ssh-keyscan -p "${PORT}" "${HOST}" >> /root/.ssh/known_hosts 2>/dev/null

# Create SSH_ASKPASS helper for passphrase automation
cat > /usr/local/bin/ssh-askpass.sh << 'SCRIPT'
#!/bin/bash
cat /run/secrets/ssh_passphrase
SCRIPT
chmod +x /usr/local/bin/ssh-askpass.sh

exec /usr/local/bin/sync.sh
