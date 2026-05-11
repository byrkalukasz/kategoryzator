import os
import tempfile
import unittest


class TestDbLlmUsage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._env_backup = dict(os.environ)
        cls.temp_db = tempfile.NamedTemporaryFile(prefix="llm_usage_", suffix=".db", delete=False)
        cls.temp_db.close()
        os.environ["BOOKED_DB_PATH"] = cls.temp_db.name

        from api import db

        cls.db = db
        cls.db.init_db()

    @classmethod
    def tearDownClass(cls):
        os.environ.clear()
        os.environ.update(cls._env_backup)
        try:
            os.unlink(cls.temp_db.name)
        except OSError:
            pass

    def test_register_llm_usage_accumulates_monthly(self):
        month = "2026-05"
        self.db.register_llm_usage(
            company_id="555",
            input_tokens=100,
            output_tokens=30,
            total_tokens=130,
            request_count=1,
            usage_month=month,
        )
        self.db.register_llm_usage(
            company_id="555",
            input_tokens=50,
            output_tokens=20,
            total_tokens=70,
            request_count=1,
            usage_month=month,
        )

        usage = self.db.get_llm_usage("555", usage_month=month)
        self.assertEqual(usage["requests_count"], 2)
        self.assertEqual(usage["input_tokens"], 150)
        self.assertEqual(usage["output_tokens"], 50)
        self.assertEqual(usage["total_tokens"], 200)

    def test_get_llm_usage_returns_zero_when_missing(self):
        usage = self.db.get_llm_usage("404", usage_month="2026-05")
        self.assertEqual(usage["requests_count"], 0)
        self.assertEqual(usage["input_tokens"], 0)
        self.assertEqual(usage["output_tokens"], 0)
        self.assertEqual(usage["total_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
