"""
Testy jednostkowe dla api.sqs_consumer.

Strategia:
  - Pełna izolacja od AWS: boto3.client zastąpiony mockiem.
  - Pełna izolacja od modeli ML: importujemy tylko moduły db i sqs_consumer.
  - Każdy test korzysta z tymczasowej, niezależnej bazy SQLite.
"""

import importlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Ustaw tymczasową bazę ZANIM moduły zostaną zaimportowane przez test runner
# ---------------------------------------------------------------------------
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ.setdefault("BOOKED_DB_PATH", _TMP_DB.name)
os.environ.setdefault("SKIP_REGISTRY_VALIDATION", "1")

# Upewnij się, że projekt jest w sys.path
_PROJECT = os.path.dirname(os.path.dirname(__file__))
if _PROJECT not in sys.path:
    sys.path.insert(0, _PROJECT)

import api.db as db                          # noqa: E402
from api.sqs_consumer import (               # noqa: E402
    _parse_message,
    process_one_message,
    poll_once,
)

# ---------------------------------------------------------------------------
# Przykładowe dane
# ---------------------------------------------------------------------------

VALID_MSG = {
    "nazwa": "Faktura za paliwo 05/2026",
    "typ_pozycji": "EXPENDITURE",
    "company_id": "99999",
    "accounting_type": "kpir",
    "selected_prediction": {
        "kolumna_kpir": "OTHER_EXPENSES",
        "metoda_rozliczenia_podatku": "STD100",
        "metoda_rozliczenia_vat": "VAT100",
        "odliczenie_vat": "BRAK",
        "cel_zakupu": "BRAK",
        "srodek_trwaly": "FALSE",
    },
}

VALID_MSG_JSON = json.dumps(VALID_MSG, ensure_ascii=False)


def _make_sqs_msg(body: str, receipt: str = "rcpt-001") -> dict:
    return {"Body": body, "ReceiptHandle": receipt}


# ===========================================================================
# Testy parsowania wiadomości
# ===========================================================================

class TestParseMessage(unittest.TestCase):
    def test_valid_message_returns_dict(self):
        result = _parse_message(VALID_MSG_JSON)
        self.assertIsNotNone(result)
        self.assertEqual(result["accounting_type"], "kpir")

    def test_invalid_json_returns_none(self):
        result = _parse_message("{invalid json}")
        self.assertIsNone(result)

    def test_missing_required_field_returns_none(self):
        incomplete = {k: v for k, v in VALID_MSG.items() if k != "selected_prediction"}
        result = _parse_message(json.dumps(incomplete))
        self.assertIsNone(result)

    def test_missing_nazwa_returns_none(self):
        bad = {k: v for k, v in VALID_MSG.items() if k != "nazwa"}
        result = _parse_message(json.dumps(bad))
        self.assertIsNone(result)

    def test_selected_prediction_not_dict_returns_none(self):
        bad = {**VALID_MSG, "selected_prediction": "string_instead_of_dict"}
        result = _parse_message(json.dumps(bad))
        self.assertIsNone(result)

    def test_empty_string_returns_none(self):
        self.assertIsNone(_parse_message(""))

    def test_null_json_returns_none(self):
        self.assertIsNone(_parse_message("null"))


# ===========================================================================
# Testy process_one_message
# ===========================================================================

class TestProcessOneMessage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def test_valid_message_is_stored(self):
        result = process_one_message(VALID_MSG)
        self.assertTrue(result)

        # Weryfikacja, że rekord trafił do bazy
        history = db.list_history(
            company_id="99999",
            accounting_type="kpir",
        )
        self.assertGreater(history["total"], 0)
        first_item = history["items"][0]
        self.assertEqual(first_item["nazwa"], "Faktura za paliwo 05/2026")

    def test_invalid_message_returns_false(self):
        """Brakujące pole 'nazwa' — store_invoice może rzucić wyjątek."""
        bad = {**VALID_MSG, "nazwa": ""}
        # Pusty string zostanie zaakceptowany przez store_invoice (dozwolone),
        # więc testujemy scenariusz z brakującym kluczem (KeyError w process_one_message)
        bad_no_key = {k: v for k, v in VALID_MSG.items() if k != "nazwa"}
        result = process_one_message(bad_no_key)
        self.assertFalse(result)


# ===========================================================================
# Testy poll_once (z zamockowanym klientem SQS)
# ===========================================================================

class TestPollOnce(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def _make_sqs(self, messages: list[dict]) -> MagicMock:
        """Tworzy mock klienta SQS zwracającego podane wiadomości."""
        sqs = MagicMock()
        sqs.receive_message.return_value = {"Messages": messages}
        sqs.delete_message.return_value = {}
        return sqs

    @patch("api.sqs_consumer._queue_url", return_value="https://sqs.test/queue/test")
    def test_empty_queue_returns_zeros(self, _mock_url):
        sqs = self._make_sqs([])
        saved, failed = poll_once(sqs)
        self.assertEqual(saved, 0)
        self.assertEqual(failed, 0)

    @patch("api.sqs_consumer._queue_url", return_value="https://sqs.test/queue/test")
    def test_valid_message_is_saved_and_deleted(self, _mock_url):
        sqs = self._make_sqs([_make_sqs_msg(VALID_MSG_JSON, "rcpt-valid-001")])
        saved, failed = poll_once(sqs)
        self.assertEqual(saved, 1)
        self.assertEqual(failed, 0)
        # Sprawdź, że delete_message zostało wywołane z właściwym ReceiptHandle
        sqs.delete_message.assert_called_once_with(
            QueueUrl="https://sqs.test/queue/test",
            ReceiptHandle="rcpt-valid-001",
        )

    @patch("api.sqs_consumer._queue_url", return_value="https://sqs.test/queue/test")
    def test_invalid_json_counts_as_failed_and_deleted(self, _mock_url):
        """Poison pill — nieparsowalna wiadomość powinna być usunięta (nie blokować kolejki)."""
        sqs = self._make_sqs([_make_sqs_msg("{bad", "rcpt-poison-001")])
        saved, failed = poll_once(sqs)
        self.assertEqual(saved, 0)
        self.assertEqual(failed, 1)
        sqs.delete_message.assert_called_once()

    @patch("api.sqs_consumer._queue_url", return_value="https://sqs.test/queue/test")
    def test_multiple_messages(self, _mock_url):
        msgs = [
            _make_sqs_msg(VALID_MSG_JSON, f"rcpt-multi-{i}")
            for i in range(3)
        ]
        sqs = self._make_sqs(msgs)
        saved, failed = poll_once(sqs)
        self.assertEqual(saved, 3)
        self.assertEqual(failed, 0)
        self.assertEqual(sqs.delete_message.call_count, 3)

    @patch("api.sqs_consumer._queue_url", return_value="https://sqs.test/queue/test")
    def test_receive_message_exception_returns_zeros(self, _mock_url):
        sqs = MagicMock()
        sqs.receive_message.side_effect = Exception("Connection refused")
        saved, failed = poll_once(sqs)
        self.assertEqual(saved, 0)
        self.assertEqual(failed, 0)


# ===========================================================================
# Sprzątanie
# ===========================================================================

def teardown_module():
    try:
        os.unlink(_TMP_DB.name)
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    unittest.main()
