import os

from api import db
from api import llm_client
from api.services.inference_policy import (
    build_ai_escalation_payload,
    build_final_prediction,
    predictions_have_errors,
)
from api.services.inference_predictors import predict_keras, predict_xgb
from api.services.inference_registry import (
    VECTORIZER,
    build_registry,
    validate_registry,
)


ACCOUNTING_REGISTRY = build_registry()
if os.environ.get("SKIP_REGISTRY_VALIDATION", "0") != "1":
    validate_registry(ACCOUNTING_REGISTRY)
db.init_db()


def run_inference(json_data: dict):
    """Rdzen logiki predykcji. Zwraca (status_code, response_dict)."""
    try:
        nazwa = (json_data.get("nazwa") or "").strip()
        typ_pozycji = (json_data.get("typ_pozycji") or "").strip()
        company_id_raw = json_data.get("company_id")
        accounting_type = (json_data.get("accounting_type") or "").strip().lower()

        if not nazwa or not typ_pozycji or company_id_raw is None or not accounting_type:
            return 400, {"error": "Brak wymaganych pol: nazwa, typ_pozycji, company_id, accounting_type"}

        if accounting_type not in ACCOUNTING_REGISTRY:
            return 400, {"error": f"Nieobslugiwany accounting_type: {accounting_type}. Dozwolone: kpir, advance"}

        bundle = ACCOUNTING_REGISTRY[accounting_type]
        columns = bundle.get("columns", [])
        typ_value = "BOOK" if accounting_type == "kpir" else "ADVANCED"

        company_id = db.sanitize_company_id(company_id_raw)

        company_cfg = db.get_company_config(company_id)
        confidence_exact = float(company_cfg["confidence_exact"])
        confidence_ai = float(company_cfg["confidence_ai"])

        top_similar = db.find_similar_candidates(
            nazwa=nazwa,
            typ_pozycji=typ_pozycji,
            company_id=company_id,
            accounting_type=accounting_type,
            limit=3,
        )
        best_match = top_similar[0] if top_similar else None

        if best_match is not None and float(best_match.get("similarity", 0.0)) >= confidence_exact:
            return 200, {
                "decision": "historical_match",
                "final_prediction": best_match["selected_prediction"],
                "matched_invoice": {
                    "id": best_match["id"],
                    "created_at": best_match["created_at"],
                    "nazwa": best_match["nazwa"],
                    "similarity": best_match["similarity"],
                },
                "company_config": company_cfg,
            }

        X_nazwa = VECTORIZER.transform([nazwa]).toarray()

        result_xgb, xgb_has_errors = predict_xgb(
            bundle=bundle,
            columns=columns,
            X_nazwa=X_nazwa,
            typ_value=typ_value,
            typ_pozycji=typ_pozycji,
            company_id=company_id,
        )
        result_keras, keras_has_errors = predict_keras(
            bundle=bundle,
            columns=columns,
            X_nazwa=X_nazwa,
            typ_value=typ_value,
            typ_pozycji=typ_pozycji,
            company_id=company_id,
        )

        if xgb_has_errors or keras_has_errors or predictions_have_errors(result_xgb) or predictions_have_errors(result_keras):
            return 503, {
                "decision": "model_error",
                "suggestions": {
                    "xgboost": result_xgb,
                    "keras": result_keras,
                },
            }

        best_similarity = float(best_match.get("similarity", 0.0)) if best_match else 0.0
        if best_similarity < confidence_ai:
            escalation_payload = build_ai_escalation_payload(
                nazwa=nazwa,
                typ_pozycji=typ_pozycji,
                company_id=company_id,
                accounting_type=accounting_type,
                thresholds={
                    "confidence_exact": confidence_exact,
                    "confidence_ai": confidence_ai,
                    "best_similarity": round(best_similarity, 4),
                },
                similar_candidates=top_similar,
                result_xgb=result_xgb,
                result_keras=result_keras,
            )

            llm_enabled_for_company = bool(company_cfg.get("llm_enabled", False))
            if llm_enabled_for_company and llm_client.is_enabled():
                try:
                    llm_result = llm_client.request_bedrock(escalation_payload)
                    usage = llm_result.get("usage", {}) if isinstance(llm_result, dict) else {}
                    db.register_llm_usage(
                        company_id=company_id,
                        input_tokens=int(usage.get("input_tokens", 0) or 0),
                        output_tokens=int(usage.get("output_tokens", 0) or 0),
                        total_tokens=int(usage.get("total_tokens", 0) or 0),
                        request_count=1,
                    )
                    return 200, {
                        "decision": "llm_fallback_used",
                        "message": "Niska pewnosc - wykonano fallback request do LLM (AWS Bedrock).",
                        "llm_result": llm_result,
                        "escalation": escalation_payload,
                    }
                except Exception as exc:
                    escalation_payload["llm_error"] = str(exc)
                    escalation_payload["message"] = (
                        "Niska pewnosc i blad wywolania LLM. Zwracam dane do recznej decyzji."
                    )

            return 200, escalation_payload

        final_payload = build_final_prediction(result_xgb, result_keras)
        final_payload["company_config"] = company_cfg
        final_payload["matched_invoice"] = (
            {
                "id": best_match["id"],
                "created_at": best_match["created_at"],
                "nazwa": best_match["nazwa"],
                "similarity": best_match["similarity"],
            }
            if best_match is not None
            else None
        )
        return 200, final_payload

    except Exception as exc:
        return 500, {"error": str(exc)}
