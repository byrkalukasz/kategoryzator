#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="categoryzer-app"
CONTAINER_NAME="categoryzer-app-local"
PORT="8000"
ENV_FILE="${ENV_FILE:-.env}"

echo "[1/3] Building image ${IMAGE_NAME}..."
docker build -t "${IMAGE_NAME}" .

echo "[2/3] Starting container ${CONTAINER_NAME} on port ${PORT}..."
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
ENV_ARGS=()
if [[ -f "${ENV_FILE}" ]]; then
  ENV_ARGS+=(--env-file "${ENV_FILE}")
  echo "Using env file: ${ENV_FILE}"
fi
docker run -d --name "${CONTAINER_NAME}" \
  -p "${PORT}:${PORT}" \
  -v "$(pwd)/logs:/app/logs" \
  "${ENV_ARGS[@]}" \
  "${IMAGE_NAME}" >/dev/null

echo "[3/3] Health check..."
for i in {1..30}; do
  status=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${PORT}/health" || true)
  if [[ "${status}" == "200" ]]; then
    echo "Healthy: http://localhost:${PORT}/health"
    exit 0
  fi
  sleep 1
done

echo "Container did not become healthy in time."
docker logs "${CONTAINER_NAME}" | tail -n 100
exit 1
