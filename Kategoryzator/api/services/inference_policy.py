def predictions_have_errors(payload: dict) -> bool:
    if "error" in payload:
        return True
    for value in payload.values():
        if value == "model_not_found":
            return True
    return False


def build_final_prediction(result_xgb: dict, result_keras: dict):
    if result_xgb == result_keras:
        return {
            "decision": "model_consensus",
            "final_prediction": result_xgb,
            "suggestions": {
                "xgboost": result_xgb,
                "keras": result_keras,
            },
        }

    return {
        "decision": "manual_review_required",
        "message": "Predykcje modeli sa rozbiezne. Wybor pozostaje po stronie ksiegowego.",
        "suggestions": {
            "xgboost": result_xgb,
            "keras": result_keras,
        },
    }


def build_ai_escalation_payload(
    nazwa: str,
    typ_pozycji: str,
    company_id: str,
    accounting_type: str,
    thresholds: dict,
    similar_candidates: list[dict],
    result_xgb: dict,
    result_keras: dict,
):
    return {
        "decision": "ai_assist_required",
        "message": "Niska pewnosc dopasowania historii. Przekaz dane do AI z podpowiedziami.",
        "thresholds": thresholds,
        "top_similar_from_history": [
            {
                "id": item.get("id"),
                "created_at": item.get("created_at"),
                "nazwa": item.get("nazwa"),
                "similarity": item.get("similarity"),
                "selected_prediction": item.get("selected_prediction"),
            }
            for item in similar_candidates
        ],
        "suggestions": {
            "xgboost": result_xgb,
            "keras": result_keras,
        },
        "ai_hint_request": {
            "input": {
                "nazwa": nazwa,
                "typ_pozycji": typ_pozycji,
                "company_id": company_id,
                "accounting_type": accounting_type,
            },
            "possible_category_candidates": {
                "from_history_top3": [
                    item.get("selected_prediction")
                    for item in similar_candidates
                ],
                "from_xgboost": result_xgb,
                "from_keras": result_keras,
            },
        },
    }
