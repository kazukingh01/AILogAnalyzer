FROM ubuntu:24.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      curl jq git ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash claude

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY analyze.sh /usr/local/bin/analyze.sh
COPY notify-discord.sh /usr/local/bin/notify-discord.sh
COPY CLAUDE.md /home/claude/CLAUDE.md
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/analyze.sh /usr/local/bin/notify-discord.sh && \
    chown claude:claude /home/claude/CLAUDE.md

USER claude
WORKDIR /home/claude

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
