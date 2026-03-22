FROM ubuntu:24.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      curl jq git ca-certificates sudo python3 && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user with sudo privileges
RUN useradd -m -s /bin/bash claude \
    && echo 'claude ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/claude

# Set up claude settings for all permissions
RUN mkdir -p /home/claude/.claude && \
    echo '{"permissions":{"allow":["*"],"deny":[]}}' > /home/claude/.claude/settings.json && \
    chown -R claude:claude /home/claude/.claude

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV PATH="/tools:${PATH}"

USER claude
WORKDIR /home/claude

RUN git config --global user.email "claude@example.com" \
    && git config --global user.name "Claude"

RUN echo 'export PATH="/tools:$PATH"' >> /home/claude/.bashrc && \
    echo 'alias claude="claude --dangerously-skip-permissions"' >> /home/claude/.bashrc

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
