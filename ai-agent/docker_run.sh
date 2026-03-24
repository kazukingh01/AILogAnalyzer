#!/bin/bash
set -euo pipefail

DELETE=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --delete) DELETE=true; shift ;;
    -*) echo "Unknown option: $1" >&2; exit 1 ;;
    *) SERVICENAME="$1"; shift ;;
  esac
done

SERVICENAME="${SERVICENAME:?Usage: $0 [--delete] <service_name>}"

# Validate service name (alphanumeric, hyphens, underscores only)
if [[ ! "${SERVICENAME}" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "Invalid service name: '${SERVICENAME}' (allowed: [a-zA-Z0-9_-]+)" >&2
  exit 1
fi

SHARE_DIR="${SHARE_DIR:-./share}"
CONTAINER_NAME="ailog-agent-${SERVICENAME}"
IMAGE_NAME="ailog-agent"

if [ "${DELETE}" = true ]; then
  echo "Removing container: ${CONTAINER_NAME}"
  docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true
  echo "Removing image: ${IMAGE_NAME}"
  docker rmi "${IMAGE_NAME}" 2>/dev/null || true
  echo "Removing data: db, knowledge, work for ${SERVICENAME}"
  rm -rf "${SHARE_DIR}/db/${SERVICENAME}" "${SHARE_DIR}/knowledge/${SERVICENAME}.md"
  rm -rf "${SHARE_DIR}/work/${SERVICENAME}"
fi

docker build -t "${IMAGE_NAME}" ./ai-agent

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Ensure single files exist before mounting
KNOWLEDGE_FILE="${SHARE_DIR}/knowledge/${SERVICENAME}.md"
DB_DIR="${SHARE_DIR}/db/${SERVICENAME}"
mkdir -p "$(dirname "${KNOWLEDGE_FILE}")" "${DB_DIR}" "${SHARE_DIR}/work/${SERVICENAME}"
if [ ! -f "${KNOWLEDGE_FILE}" ]; then
  cp "${SCRIPT_DIR}/tools/knowledge_template.md" "${KNOWLEDGE_FILE}"
fi

docker run -d --name "${CONTAINER_NAME}" \
  -e "SERVICE_NAME=${SERVICENAME}" \
  --env-file .env \
  -v "${SCRIPT_DIR}/tools:/tools:ro" \
  -v "${SHARE_DIR}/logs/${SERVICENAME}:/data/logs/:ro" \
  -v "${SHARE_DIR}/work/${SERVICENAME}:/data/work/" \
  -v "${KNOWLEDGE_FILE}:/data/knowledge/knowledge.md" \
  -v "${DB_DIR}:/data/db/" \
  "${IMAGE_NAME}"

# Fix ownership of mounted volumes to match container's claude user
CLAUDE_UID=$(docker exec "${CONTAINER_NAME}" id -u claude)
CLAUDE_GID=$(docker exec "${CONTAINER_NAME}" id -g claude)
docker exec -u root "${CONTAINER_NAME}" chown -R "${CLAUDE_UID}:${CLAUDE_GID}" /data/work /data/knowledge/knowledge.md /data/db

docker exec -it -u claude "${CONTAINER_NAME}" claude --dangerously-skip-permissions
