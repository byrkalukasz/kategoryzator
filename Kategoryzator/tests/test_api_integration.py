import importlib
import os
import tempfile
import unittest

from fastapi.testclient import TestClient
import api.db as db


class APISmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["SKIP_REGISTRY_VALIDATION"] = "1"
        cls.temp_db = tempfile.NamedTemporaryFile(prefix="booked_invoices_", suffix=".db", delete=False)
        cls.temp_db.close()
        os.environ["BOOKED_DB_PATH"] = cls.temp_db.name
        app_module = importlib.import_module("api.app")
        cls.client = TestClient(app_module.app)

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls.temp_db.name)
        except OSError:
            pass

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_predict_validation_error(self):
        response = self.client.post(
            "/predict",
            json={
                "nazwa": "",
                "typ_pozycji": "EXPENDITURE",
                "company_id": "123",
                "accounting_type": "kpir",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_predict_unseen_company_not_blocked(self):
        response = self.client.post(
            "/predict",
            json={
                "nazwa": "Nowa faktura testowa klienta bez historii",
                "typ_pozycji": "EXPENDITURE",
                "company_id": "new-company-999999",
                "accounting_type": "kpir",
            },
        )
        # Akceptujemy 200 (normalny flow) lub 503 (problem modeli),
        # ale nie mozemy blokowac klienta z powodu braku danych uczacych.
        self.assertIn(response.status_code, (200, 503))
        body = response.json()
        self.assertIn("decision", body)

    def test_bookkeeping_confirm_and_historical_match(self):
        confirmed = self.client.post(
            "/bookkeeping/confirm",
            json={
                "nazwa": "Abonament telefoniczny Orange 05/2026",
                "typ_pozycji": "EXPENDITURE",
                "company_id": "123",
                "accounting_type": "kpir",
                "selected_prediction": {
                    "kolumna_kpir": "OTHER_EXPENSES",
                    "metoda_rozliczenia_podatku": "STD100",
                },
            },
        )
        self.assertEqual(confirmed.status_code, 201)
        self.assertEqual(confirmed.json().get("status"), "saved")
        self._booking_id = confirmed.json().get("booking_id")

        predicted = self.client.post(
            "/predict",
            json={
                "nazwa": "abonament telefoniczny orange 05/2026",
                "typ_pozycji": "EXPENDITURE",
                "company_id": "123",
                "accounting_type": "kpir",
            },
        )
        self.assertEqual(predicted.status_code, 200)
        body = predicted.json()
        self.assertEqual(body.get("decision"), "historical_match")
        self.assertIn("final_prediction", body)
        self.assertEqual(body["final_prediction"].get("kolumna_kpir"), "OTHER_EXPENSES")

    def test_history_list_and_filter(self):
        self.client.post(
            "/bookkeeping/confirm",
            json={
                "nazwa": "Paliwo Shell 05/2026",
                "typ_pozycji": "EXPENDITURE",
                "company_id": "999",
                "accounting_type": "kpir",
                "selected_prediction": {"kolumna_kpir": "OTHER_EXPENSES"},
            },
        )

        res_all = self.client.get("/bookkeeping/history")
        self.assertEqual(res_all.status_code, 200)
        body = res_all.json()
        self.assertIn("total", body)
        self.assertGreaterEqual(body["total"], 1)
        self.assertIn("items", body)

        res_filtered = self.client.get("/bookkeeping/history?company_id=999&accounting_type=kpir")
        self.assertEqual(res_filtered.status_code, 200)
        items = res_filtered.json()["items"]
        self.assertTrue(all(i["company_id"] == "999" for i in items))

    def test_history_delete(self):
        confirm = self.client.post(
            "/bookkeeping/confirm",
            json={
                "nazwa": "Faktura do usuniecia",
                "typ_pozycji": "EXPENDITURE",
                "company_id": "777",
                "accounting_type": "kpir",
                "selected_prediction": {"kolumna_kpir": "OTHER_EXPENSES"},
            },
        )
        booking_id = confirm.json()["booking_id"]

        res_del = self.client.delete(f"/bookkeeping/history/{booking_id}")
        self.assertEqual(res_del.status_code, 200)
        self.assertEqual(res_del.json()["status"], "deleted")

        res_del_again = self.client.delete(f"/bookkeeping/history/{booking_id}")
        self.assertEqual(res_del_again.status_code, 404)

    def test_company_config_set_and_get(self):
        set_res = self.client.put(
            "/bookkeeping/company-config",
            json={
                "company_id": "321",
                "confidence_exact": 0.97,
                "confidence_ai": 0.81,
                "llm_enabled": True,
            },
        )
        self.assertEqual(set_res.status_code, 200)
        self.assertEqual(set_res.json()["status"], "saved")

        get_res = self.client.get("/bookkeeping/company-config/321")
        self.assertEqual(get_res.status_code, 200)
        cfg = get_res.json()["config"]
        self.assertEqual(cfg["company_id"], "321")
        self.assertAlmostEqual(cfg["confidence_exact"], 0.97, places=3)
        self.assertAlmostEqual(cfg["confidence_ai"], 0.81, places=3)
        self.assertTrue(cfg["llm_enabled"])
        self.assertEqual(cfg["source"], "company")

    def test_llm_usage_endpoint_default_zeros(self):
        res = self.client.get("/bookkeeping/llm-usage/321")
        self.assertEqual(res.status_code, 200)
        usage = res.json()["usage"]
        self.assertEqual(usage["company_id"], "321")
        self.assertEqual(usage["requests_count"], 0)
        self.assertEqual(usage["input_tokens"], 0)
        self.assertEqual(usage["output_tokens"], 0)
        self.assertEqual(usage["total_tokens"], 0)

    def test_llm_usage_report_and_clients_list(self):
        db.register_llm_usage(
            company_id="c1",
            input_tokens=120,
            output_tokens=30,
            total_tokens=150,
            usage_month="2026-05",
        )
        db.register_llm_usage(
            company_id="c2",
            input_tokens=60,
            output_tokens=40,
            total_tokens=100,
            usage_month="2026-05",
        )

        res_summary = self.client.get("/bookkeeping/llm-usage-report?usage_month=2026-05")
        self.assertEqual(res_summary.status_code, 200)
        summary = res_summary.json()["summary"]
        self.assertEqual(summary["usage_month"], "2026-05")
        self.assertEqual(summary["total_clients"], 2)
        self.assertEqual(summary["requests_count"], 2)
        self.assertEqual(summary["input_tokens"], 180)
        self.assertEqual(summary["output_tokens"], 70)
        self.assertEqual(summary["total_tokens"], 250)

        res_clients = self.client.get("/bookkeeping/llm-usage-clients?usage_month=2026-05&limit=10&offset=0")
        self.assertEqual(res_clients.status_code, 200)
        body = res_clients.json()
        self.assertEqual(body["usage_month"], "2026-05")
        self.assertEqual(body["total_clients"], 2)
        self.assertEqual(len(body["items"]), 2)
        # sortowanie malejaco po total_tokens: c1 (150) powinno byc pierwsze
        self.assertEqual(body["items"][0]["company_id"], "c1")

    def test_ai_assist_when_similarity_below_company_threshold(self):
        self.client.post(
            "/bookkeeping/confirm",
            json={
                "nazwa": "Serwis opon i wywazanie kol 2026",
                "typ_pozycji": "EXPENDITURE",
                "company_id": "700",
                "accounting_type": "kpir",
                "selected_prediction": {
                    "kolumna_kpir": "OTHER_EXPENSES",
                    "metoda_rozliczenia_podatku": "STD100",
                },
            },
        )

        self.client.put(
            "/bookkeeping/company-config",
            json={
                "company_id": "700",
                "confidence_exact": 0.99,
                "confidence_ai": 0.95,
            },
        )

        predicted = self.client.post(
            "/predict",
            json={
                "nazwa": "Usluga prawna analiza umow 2026",
                "typ_pozycji": "EXPENDITURE",
                "company_id": "700",
                "accounting_type": "kpir",
            },
        )
        self.assertEqual(predicted.status_code, 200)
        body = predicted.json()
        self.assertEqual(body.get("decision"), "ai_assist_required")
        self.assertIn("top_similar_from_history", body)
        self.assertIn("suggestions", body)
        self.assertIn("ai_hint_request", body)


if __name__ == "__main__":
    unittest.main()
