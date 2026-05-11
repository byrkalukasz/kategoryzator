import json
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


def _resolve_path(*parts: str) -> str:
    return str(BASE_DIR.joinpath(*parts))


PREDICT_LOG_PATH = os.environ.get("PREDICT_LOG_PATH", _resolve_path("logs", "predictions.jsonl"))
if not os.path.isabs(PREDICT_LOG_PATH):
    PREDICT_LOG_PATH = _resolve_path(PREDICT_LOG_PATH)


def append_log(entry: dict):
    """Log na stdout (docker logs) i jednoczesnie do pliku JSONL."""
    try:
        line = json.dumps(entry, ensure_ascii=False)
        print(line, flush=True)
        log_dir = os.path.dirname(PREDICT_LOG_PATH) or "."
        os.makedirs(log_dir, exist_ok=True)
        with open(PREDICT_LOG_PATH, "a", encoding="utf-8") as file:
            file.write(line + "\n")
    except Exception as exc:
        print(f"[LOG ERROR] {exc}", flush=True)
