"""
SQS Consumer — pobiera dokumenty z kolejki i zapisuje je do bazy historii.

Format wiadomości SQS (JSON):
{
    "nazwa":               "Faktura za paliwo 05/2026",
    "typ_pozycji":         "EXPENDITURE",
    "company_id":          "12345",
    "accounting_type":     "kpir",
    "selected_prediction": {
        "kolumna_kpir":                  "OTHER_EXPENSES",
        "metoda_rozliczenia_podatku":    "STD100",
        "metoda_rozliczenia_vat":        "VAT100",
        "odliczenie_vat":                "BRAK",
        "cel_zakupu":                    "BRAK",
        "srodek_trwaly":                 "FALSE"
    }
}

Zmienne środowiskowe:
  SQS_QUEUE_URL              — URL kolejki (wymagany)
  AWS_REGION                 — region AWS (domyślnie: eu-central-1)
  SQS_POLL_INTERVAL_SECONDS  — przerwa między rundami (domyślnie: 3600 = 1h)
  SQS_MAX_MESSAGES_PER_BATCH — max wiadomości na jedno receive_message (1–10, domyślnie: 10)
  SQS_VISIBILITY_TIMEOUT     — sekundy niewidoczności po odebraniu (domyślnie: 60)

Uruchomienie:
  # Daemon (pętla co 1h):
  python -m api.sqs_consumer

  # Jednorazowo (np. z crona):
  python -m api.sqs_consumer --once
"""

import argparse
import json
import logging
import os
import sys
import time
from dotenv import load_dotenv

# Dodaj katalog główny projektu do sys.path (gdy uruchamiany bezpośrednio)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

from api.db import sanitize_company_id, store_invoice  # noqa: E402

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = {"nazwa", "typ_pozycji", "company_id", "accounting_type", "selected_prediction"}


# =============================================================================
# Konfiguracja
# =============================================================================

def _queue_url() -> str:
    url = os.environ.get("SQS_QUEUE_URL", "")
    if not url:
        raise RuntimeError("Zmienna środowiskowa SQS_QUEUE_URL nie jest ustawiona.")
    return url


def _aws_region() -> str:
    return os.environ.get("AWS_REGION", "eu-central-1")


def _poll_interval() -> int:
    return int(os.environ.get("SQS_POLL_INTERVAL_SECONDS", str(60 * 60)))


def _max_messages() -> int:
    return max(1, min(10, int(os.environ.get("SQS_MAX_MESSAGES_PER_BATCH", "10"))))


def _visibility_timeout() -> int:
    return int(os.environ.get("SQS_VISIBILITY_TIMEOUT", "60"))


# =============================================================================
# Parsowanie / walidacja wiadomości
# =============================================================================

def _parse_message(body: str) -> dict | None:
    """Parsuje JSON z treści wiadomości SQS. Zwraca None przy błędzie."""
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Nieprawidłowy JSON: %s — %s", exc, body[:200])
        return None

    if not isinstance(data, dict):
        logger.warning("Treść wiadomości nie jest obiektem JSON — %s", body[:200])
        return None

    missing = _REQUIRED_FIELDS - set(data.keys())
    if missing:
        logger.warning("Brak pól w wiadomości: %s — %s", missing, body[:200])
        return None

    if not isinstance(data.get("selected_prediction"), dict):
        logger.warning("selected_prediction musi być obiektem — %s", body[:200])
        return None

    return data


# =============================================================================
# Przetwarzanie pojedynczej wiadomości
# =============================================================================

def process_one_message(data: dict) -> bool:
    """Zapisuje fakturę do bazy. Zwraca True przy sukcesie."""
    try:
        company_id = sanitize_company_id(data["company_id"])
        booking_id = store_invoice(
            nazwa=str(data["nazwa"]).strip(),
            typ_pozycji=str(data["typ_pozycji"]).strip(),
            company_id=company_id,
            accounting_type=str(data["accounting_type"]).strip().lower(),
            selected_prediction=data["selected_prediction"],
        )
        logger.info(
            "Zapisano fakturę id=%s company=%s nazwa='%.60s'",
            booking_id, company_id, data["nazwa"],
        )
        return True
    except Exception as exc:
        logger.error("Błąd zapisu wiadomości: %s — %s", exc, data)
        return False


# =============================================================================
# Jedna runda pollingu
# =============================================================================

def poll_once(sqs_client) -> tuple[int, int]:
    """
    Pobiera jedną partię wiadomości z SQS i przetwarza je.
    Zwraca (liczba_zapisanych, liczba_błędów).
    """
    try:
        response = sqs_client.receive_message(
            QueueUrl=_queue_url(),
            MaxNumberOfMessages=_max_messages(),
            VisibilityTimeout=_visibility_timeout(),
            WaitTimeSeconds=10,          # long polling — oszczędza koszty
            MessageAttributeNames=["All"],
        )
    except Exception as exc:
        logger.error("Błąd receive_message: %s", exc)
        return 0, 0

    messages = response.get("Messages", [])
    if not messages:
        logger.info("Kolejka pusta.")
        return 0, 0

    saved, failed = 0, 0
    for msg in messages:
        receipt = msg["ReceiptHandle"]
        data = _parse_message(msg.get("Body", ""))

        if data is None:
            # Nieparsowalna wiadomość — usuwamy, żeby nie blokować kolejki (poison pill)
            sqs_client.delete_message(QueueUrl=_queue_url(), ReceiptHandle=receipt)
            failed += 1
            continue

        if process_one_message(data):
            sqs_client.delete_message(QueueUrl=_queue_url(), ReceiptHandle=receipt)
            saved += 1
        else:
            # Nie usuwamy — SQS przywróci po VisibilityTimeout (retry)
            failed += 1

    logger.info("Runda zakończona: %d zapisano, %d błędów.", saved, failed)
    return saved, failed


# =============================================================================
# Tryb daemon (pętla) i tryb --once (cron)
# =============================================================================

def _build_sqs_client():
    try:
        import boto3
    except ImportError as exc:
        raise ImportError(
            "Brak pakietu boto3. Zainstaluj: pip install boto3"
        ) from exc
    return boto3.client("sqs", region_name=_aws_region())


def run_once() -> tuple[int, int]:
    """Jedna runda — przydatna do wywołania z crona lub testów."""
    sqs = _build_sqs_client()
    return poll_once(sqs)


def run_forever() -> None:
    """Pętla daemon: poll → sleep(interval) → poll → ..."""
    interval = _poll_interval()
    logger.info(
        "SQS Consumer uruchomiony. Kolejka=%s Interwał=%ds",
        _queue_url(), interval,
    )
    sqs = _build_sqs_client()
    while True:
        logger.info("Polling SQS...")
        try:
            poll_once(sqs)
        except Exception as exc:
            logger.exception("Nieoczekiwany błąd: %s", exc)
        logger.info("Czekam %d sekund do następnej rundy.", interval)
        time.sleep(interval)


# =============================================================================
# Entrypoint
# =============================================================================

def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def main() -> None:
    _setup_logging()
    parser = argparse.ArgumentParser(description="SQS Consumer — historia faktur")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Wykonaj jedną rundę i zakończ (tryb cron). Bez flagi działa jako daemon.",
    )
    args = parser.parse_args()

    if args.once:
        saved, failed = run_once()
        logger.info("Tryb --once zakończony: %d zapisano, %d błędów.", saved, failed)
    else:
        run_forever()


if __name__ == "__main__":
    main()
