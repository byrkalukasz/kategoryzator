from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api import db
from api.services.inference_service import ACCOUNTING_REGISTRY, run_inference
from api.services.log_service import append_log

app = FastAPI(title="Kategoryzator API", version="2.0.0")


class PredictPayload(BaseModel):
    nazwa: str
    typ_pozycji: str
    company_id: str | int | float
    accounting_type: str


class PredictLogPayload(BaseModel):
    nazwa: str
    typ_pozycji: str
    company_id: str | int | float
    accounting_type: str


class ConfirmBookingPayload(BaseModel):
    nazwa: str
    typ_pozycji: str
    company_id: str | int | float
    accounting_type: str
    selected_prediction: dict


class CompanyConfigPayload(BaseModel):
    company_id: str | int | float
    confidence_exact: float
    confidence_ai: float
    llm_enabled: bool | None = None


@app.post("/predict")
def predict(payload: PredictPayload):
    status, response_payload = run_inference(payload.model_dump())
    return JSONResponse(content=response_payload, status_code=status)


@app.post("/predict_log")
def predict_log(payload: PredictLogPayload):
    json_data = payload.model_dump()
    status, response_payload = run_inference(json_data)
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "request": {
            "nazwa": (json_data.get("nazwa") or ""),
            "typ_pozycji": (json_data.get("typ_pozycji") or ""),
            "company_id": (json_data.get("company_id") or ""),
            "accounting_type": (json_data.get("accounting_type") or ""),
            "raw": json_data,
        },
        "response": response_payload,
        "status": status,
    }
    append_log(log_entry)
    return JSONResponse(content=response_payload, status_code=status)


@app.post("/bookkeeping/confirm")
def confirm_booking(payload: ConfirmBookingPayload):
    json_data = payload.model_dump()
    nazwa = (json_data.get("nazwa") or "").strip()
    typ_pozycji = (json_data.get("typ_pozycji") or "").strip()
    company_id_raw = json_data.get("company_id")
    accounting_type = (json_data.get("accounting_type") or "").strip().lower()
    selected_prediction = json_data.get("selected_prediction") or {}

    if not nazwa or not typ_pozycji or company_id_raw is None or not accounting_type:
        return JSONResponse(
            content={"error": "Brak wymaganych pól: nazwa, typ_pozycji, company_id, accounting_type"},
            status_code=400,
        )

    if accounting_type not in ACCOUNTING_REGISTRY:
        return JSONResponse(
            content={"error": f"Nieobsługiwany accounting_type: {accounting_type}. Dozwolone: kpir, advance"},
            status_code=400,
        )

    if not isinstance(selected_prediction, dict) or not selected_prediction:
        return JSONResponse(
            content={"error": "Pole selected_prediction musi być niepustym obiektem."},
            status_code=400,
        )

    company_id = db.sanitize_company_id(company_id_raw)
    booking_id = db.store_invoice(
        nazwa=nazwa,
        typ_pozycji=typ_pozycji,
        company_id=company_id,
        accounting_type=accounting_type,
        selected_prediction=selected_prediction,
    )

    return JSONResponse(
        content={
            "status": "saved",
            "booking_id": booking_id,
            "company_id": company_id,
            "accounting_type": accounting_type,
        },
        status_code=201,
    )


@app.get("/bookkeeping/history")
def get_history(
    company_id: str | None = None,
    accounting_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    result = db.list_history(
        company_id=company_id,
        accounting_type=accounting_type,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(content=result, status_code=200)


@app.delete("/bookkeeping/history/{booking_id}")
def delete_booking(booking_id: int):
    deleted = db.delete_invoice(booking_id)
    if not deleted:
        return JSONResponse(
            content={"error": f"Booking o id={booking_id} nie istnieje."},
            status_code=404,
        )
    return JSONResponse(
        content={"status": "deleted", "booking_id": booking_id},
        status_code=200,
    )


@app.put("/bookkeeping/company-config")
def set_company_config(payload: CompanyConfigPayload):
    company_id = db.sanitize_company_id(payload.company_id)
    try:
        config = db.upsert_company_config(
            company_id=company_id,
            confidence_exact=payload.confidence_exact,
            confidence_ai=payload.confidence_ai,
            llm_enabled=payload.llm_enabled,
        )
    except ValueError as exc:
        return JSONResponse(content={"error": str(exc)}, status_code=400)

    return JSONResponse(content={"status": "saved", "config": config}, status_code=200)


@app.get("/bookkeeping/company-config/{company_id}")
def get_company_config(company_id: str):
    config = db.get_company_config(company_id)
    return JSONResponse(content={"config": config}, status_code=200)


@app.get("/bookkeeping/llm-usage/{company_id}")
def get_company_llm_usage(company_id: str, usage_month: str | None = None):
    usage = db.get_llm_usage(company_id=company_id, usage_month=usage_month)
    return JSONResponse(content={"usage": usage}, status_code=200)


@app.get("/bookkeeping/llm-usage-report")
def get_llm_usage_report(usage_month: str | None = None):
    summary = db.get_llm_usage_report_summary(usage_month=usage_month)
    return JSONResponse(content={"summary": summary}, status_code=200)


@app.get("/bookkeeping/llm-usage-clients")
def get_llm_usage_clients(
    usage_month: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    result = db.list_llm_usage_clients(
        usage_month=usage_month,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(content=result, status_code=200)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
