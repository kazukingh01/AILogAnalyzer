# secrets/

Place the following files here (all git-ignored):

- `ssh_private_key_a` — SSH private key for service A rsync access
- `ssh_private_key_b` — SSH private key for service B rsync access

Note: SSH passphrase and Discord webhook URL are configured via environment variables (see `.env.example`).
