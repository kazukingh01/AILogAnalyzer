FROM ubuntu:24.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends rsync openssh-client && \
    rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY sync.sh /usr/local/bin/sync.sh
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/sync.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
