#!/usr/bin/env bash
# run_sqs_consumer.sh
#
# Uruchomienie konsumera SQS dla historii faktur.
#
# Użycie:
#   ./scripts/run_sqs_consumer.sh           # daemon (pętla co SQS_POLL_INTERVAL_SECONDS)
#   ./scripts/run_sqs_consumer.sh --once    # jednorazowo (np. z crona)
#
# Przykładowy wpis cron (co godzinę):
#   0 * * * * /ścieżka/do/projektu/scripts/run_sqs_consumer.sh --once >> /var/log/sqs_consumer.log 2>&1
#
# Wymagane zmienne środowiskowe:
#   SQS_QUEUE_URL  — URL kolejki SQS
#   AWS_REGION     — region AWS (domyślnie: eu-central-1)
#   AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY  lub rola IAM na instancji

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Aktywuj virtualenv (jeśli istnieje)
VENV_PYTHON="${PROJECT_DIR}/.kategoryzator/bin/python"
if [[ -x "${VENV_PYTHON}" ]]; then
    PYTHON="${VENV_PYTHON}"
else
    PYTHON="$(command -v python3)"
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting SQS consumer (python: ${PYTHON})"

cd "${PROJECT_DIR}"

if [[ -f "${PROJECT_DIR}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_DIR}/.env"
    set +a
fi

exec "${PYTHON}" -m api.sqs_consumer "$@"
