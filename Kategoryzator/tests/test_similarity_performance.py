import os
import tempfile
import time
import unittest

import api.db as db


class TestSimilarityPerformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._env_backup = dict(os.environ)
        cls.temp_db = tempfile.NamedTemporaryFile(prefix="perf_booked_", suffix=".db", delete=False)
        cls.temp_db.close()
        os.environ["BOOKED_DB_PATH"] = cls.temp_db.name
        db.init_db()

        # Przygotuj sensowny wolumen danych do testu szybkosci podobienstwa.
        for idx in range(180):
            db.store_invoice(
                nazwa=f"Faktura testowa uslugi numer {idx} za miesiac 2026",
                typ_pozycji="EXPENDITURE",
                company_id="perf-company",
                accounting_type="kpir",
                selected_prediction={"kolumna_kpir": "OTHER_EXPENSES"},
            )

    @classmethod
    def tearDownClass(cls):
        os.environ.clear()
        os.environ.update(cls._env_backup)
        try:
            os.unlink(cls.temp_db.name)
        except OSError:
            pass

    def test_find_similar_candidates_latency(self):
        start = time.perf_counter()
        result = db.find_similar_candidates(
            nazwa="Faktura testowa uslugi numer 123 za miesiac 2026",
            typ_pozycji="EXPENDITURE",
            company_id="perf-company",
            accounting_type="kpir",
            limit=3,
        )
        elapsed = time.perf_counter() - start

        self.assertGreaterEqual(len(result), 1)
        # Budzet czasowy umiarkowany, by test nie byl flakey na wolniejszym CI.
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
