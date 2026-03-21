FROM alpine:3.21

RUN apk add --no-cache rsync openssh-client bash

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY sync.sh /usr/local/bin/sync.sh
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/sync.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
