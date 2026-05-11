import json
import os
from typing import Any


def _to_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_enabled() -> bool:
    return _to_bool(os.environ.get("LLM_FALLBACK_ENABLED", "0"))


def _region() -> str:
    return os.environ.get("LLM_AWS_REGION") or os.environ.get("AWS_REGION", "eu-central-1")


def _model_id() -> str:
    model_id = os.environ.get("LLM_BEDROCK_MODEL_ID", "").strip()
    if not model_id:
        raise RuntimeError("LLM_BEDROCK_MODEL_ID nie jest ustawiony.")
    return model_id


def _max_tokens() -> int:
    return int(os.environ.get("LLM_MAX_TOKENS", "800"))


def _temperature() -> float:
    return float(os.environ.get("LLM_TEMPERATURE", "0.1"))


def _timeout_seconds() -> int:
    return int(os.environ.get("LLM_TIMEOUT_SECONDS", "20"))


def _system_prompt() -> str:
    return (
        "Jestes ekspertem ksiegowym. Zwracaj JSON z kluczem final_prediction "
        "i confidence (0..1). Uwzglednij podpowiedzi z historii, xgboost i keras."
    )


def _user_prompt(ai_payload: dict[str, Any]) -> str:
    return (
        "Na podstawie danych wejsciowych zaproponuj finalne kategorie i poziom pewnosci.\n"
        "Dane:\n"
        f"{json.dumps(ai_payload, ensure_ascii=False)}"
    )


def request_bedrock(ai_payload: dict[str, Any]) -> dict[str, Any]:
    """Wywoluje AWS Bedrock (Converse API) i zwraca odpowiedz LLM."""
    if not is_enabled():
        return {
            "called": False,
            "enabled": False,
            "reason": "LLM_FALLBACK_ENABLED=0",
        }

    import boto3
    from botocore.config import Config

    config = Config(connect_timeout=_timeout_seconds(), read_timeout=_timeout_seconds(), retries={"max_attempts": 2})
    client = boto3.client("bedrock-runtime", region_name=_region(), config=config)

    response = client.converse(
        modelId=_model_id(),
        system=[{"text": _system_prompt()}],
        messages=[
            {
                "role": "user",
                "content": [{"text": _user_prompt(ai_payload)}],
            }
        ],
        inferenceConfig={
            "maxTokens": _max_tokens(),
            "temperature": _temperature(),
        },
    )

    output_text = ""
    output = response.get("output", {})
    message = output.get("message", {})
    for item in message.get("content", []):
        text = item.get("text")
        if text:
            output_text += text

    usage = response.get("usage", {}) or {}
    input_tokens = int(usage.get("inputTokens", 0) or 0)
    output_tokens = int(usage.get("outputTokens", 0) or 0)
    total_tokens = int(usage.get("totalTokens", input_tokens + output_tokens) or 0)

    return {
        "called": True,
        "enabled": True,
        "provider": "aws-bedrock",
        "region": _region(),
        "model_id": _model_id(),
        "output_text": output_text.strip(),
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
    }
