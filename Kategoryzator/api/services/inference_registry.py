import os
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.exceptions import InconsistentVersionWarning
from sklearn.preprocessing import OneHotEncoder
from tensorflow.keras.models import load_model

warnings.filterwarnings("ignore", category=InconsistentVersionWarning)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


def resolve_path(*parts: str) -> str:
    return str(BASE_DIR.joinpath(*parts))


DATA_FILES = {
    "kpir": resolve_path("dane", "dane_ai.csv"),
    "advance": resolve_path("dane", "dane_ai_ryczalt.csv"),
}

KERAS_DIRS = {
    "kpir": resolve_path("KPIR_kerras"),
    "advance": resolve_path("ADVANCED_kerras"),
}
XGB_DIRS = {
    "kpir": resolve_path("KPIR_xgboost"),
    "advance": resolve_path("ADVANCED_xgboost"),
}

OUTPUT_COLUMNS = {
    "kpir": [
        "kolumna_kpir",
        "metoda_rozliczenia_podatku",
        "metoda_rozliczenia_vat",
        "odliczenie_vat",
        "cel_zakupu",
        "srodek_trwaly",
    ],
    "advance": [
        "metoda_rozliczenia_podatku",
        "metoda_rozliczenia_vat",
        "odliczenie_vat",
        "cel_zakupu",
        "srodek_trwaly",
    ],
}

CANONICAL_COLUMNS = {
    "metoda_rozliczenia_podatku": ["metoda_rozliczenia_podatku", "medota_rozliczenia_podatku"],
}


def resolve_candidates(column_name: str):
    return CANONICAL_COLUMNS.get(column_name, [column_name])


try:
    VECTORIZER = joblib.load(resolve_path("vectorizer_nazwa_nn.pkl"))
except Exception:
    VECTORIZER = joblib.load(resolve_path("vectorizer_nazwa.pkl"))


def get_num_classes(enc) -> int | None:
    if hasattr(enc, "categories_"):
        return len(enc.categories_[0])
    if hasattr(enc, "classes_"):
        return len(enc.classes_)
    return None


def get_label_from_encoder(enc, class_index: int):
    if hasattr(enc, "categories_"):
        categories = enc.categories_[0]
        if 0 <= class_index < len(categories):
            return categories[class_index]
    elif hasattr(enc, "classes_"):
        classes = enc.classes_
        if 0 <= class_index < len(classes):
            return classes[class_index]
    return f"class_{class_index}"


def synthetic_label(idx: int) -> str:
    return f"class_{idx}"


def pick_encoder(enc_list, prefer_classes: int | None, allow_more: bool = True):
    candidates = []
    for enc in enc_list:
        if enc is None:
            continue
        n_classes = get_num_classes(enc)
        if n_classes is None or n_classes <= 0:
            continue
        candidates.append((enc, n_classes))
    if not candidates:
        return None

    if prefer_classes is not None:
        for enc, n_classes in candidates:
            if n_classes == prefer_classes:
                return enc
        if allow_more:
            for enc, n_classes in candidates:
                if n_classes > prefer_classes:
                    return enc
    return candidates[0][0]


def preprocess_data_for_keras(csv_path: str, columns: list):
    if not os.path.exists(csv_path):
        return None

    data = pd.read_csv(csv_path, encoding="ISO-8859-2", sep=";")
    if "medota_rozliczenia_podatku" in data.columns and "metoda_rozliczenia_podatku" not in data.columns:
        data = data.rename(columns={"medota_rozliczenia_podatku": "metoda_rozliczenia_podatku"})
    typ_column = data.columns[4]

    for col in ["company_id", "nazwa", typ_column, "typ_pozycji"]:
        data[col] = data[col].astype(str).str.strip()
    data = data[data["nazwa"].str.strip().astype(bool)]
    data = data[data[typ_column].isin({"BOOK", "ADVANCED"})]
    data = data[pd.to_numeric(data["company_id"], errors="coerce").notnull()]
    data["company_id"] = data["company_id"].astype(float).astype(int).astype(str)

    company_ids, _ = np.unique(data["company_id"], return_inverse=True)

    encoder_typ_keras = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    encoder_typ_keras.fit(data[[typ_column]])

    encoder_pozycja_keras = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    encoder_pozycja_keras.fit(data[["typ_pozycji"]])

    encoders_y_keras = {}
    for col in columns:
        enc_y = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
        if col in data.columns:
            enc_y.fit(data[[col]])
        else:
            enc_y.fit(pd.DataFrame(["__dummy__"], columns=[col]))
        encoders_y_keras[col] = enc_y

    return {
        "data": data,
        "typ_column": typ_column,
        "company_ids": company_ids,
        "encoder_typ_keras": encoder_typ_keras,
        "encoder_pozycja_keras": encoder_pozycja_keras,
        "encoders_y_keras": encoders_y_keras,
    }


def load_xgb_bundle(base_dir: str, columns: list, profile: str):
    bundle = {"models": {}, "encoders_y": {}}
    if not os.path.isdir(base_dir):
        return bundle

    encoder_variants = {
        "enc_typ": ["encoder_typ.pkl", "encoder_typ_ryczalt.pkl"] if profile == "advance" else ["encoder_typ.pkl"],
        "enc_poz": ["encoder_pozycja.pkl", "encoder_pozycja_ryczalt.pkl"] if profile == "advance" else ["encoder_pozycja.pkl"],
        "enc_uid": ["encoder_uid.pkl", "encoder_uid_ryczalt.pkl"] if profile == "advance" else ["encoder_uid.pkl"],
    }

    for key, variants in encoder_variants.items():
        for name in variants:
            path = os.path.join(base_dir, name)
            if os.path.exists(path):
                bundle[key] = joblib.load(path)
                break

    for col in columns:
        col_variants = resolve_candidates(col)
        model_variants = []
        encoder_variants = []
        for var in col_variants:
            model_variants.append(f"model_{var}.pkl")
            encoder_variants.append(f"encoder_y_{var}.pkl")
            if profile == "advance":
                model_variants.append(f"model_{var}_advance.pkl")

        model_path = next((os.path.join(base_dir, name) for name in model_variants if os.path.exists(os.path.join(base_dir, name))), None)
        encoder_path = next((os.path.join(base_dir, name) for name in encoder_variants if os.path.exists(os.path.join(base_dir, name))), None)

        if model_path and encoder_path:
            bundle["models"][col] = joblib.load(model_path)
            bundle["encoders_y"][col] = joblib.load(encoder_path)

    return bundle


def load_keras_bundle(base_dir: str, columns: list, profile: str):
    bundle = {"models": {}, "encoders_y": {}}
    if not os.path.isdir(base_dir):
        return bundle
    for col in columns:
        col_variants = resolve_candidates(col)
        model_variants = []
        encoder_variants = []
        for var in col_variants:
            model_variants.append(f"model_{var}.keras")
            encoder_variants.append(f"encoder_y_{var}.pkl")
            if profile == "advance":
                model_variants.append(f"model_{var}_advance.keras")

        model_path = next((os.path.join(base_dir, name) for name in model_variants if os.path.exists(os.path.join(base_dir, name))), None)
        encoder_path = next((os.path.join(base_dir, name) for name in encoder_variants if os.path.exists(os.path.join(base_dir, name))), None)

        if model_path:
            bundle["models"][col] = load_model(model_path)
        if encoder_path:
            bundle["encoders_y"][col] = joblib.load(encoder_path)
    return bundle


def merge_bundles(primary: dict, fallback: dict):
    if primary is None and fallback is None:
        return None
    if primary is None:
        return fallback
    if fallback is None:
        return primary

    merged = {}
    keys = set(primary.keys()) | set(fallback.keys())
    for key in keys:
        primary_value = primary.get(key)
        fallback_value = fallback.get(key)
        if isinstance(primary_value, dict) and isinstance(fallback_value, dict):
            merged[key] = merge_bundles(primary_value, fallback_value)
        else:
            merged[key] = primary_value if primary_value is not None else fallback_value
    return merged


def build_registry():
    cols_kpir = OUTPUT_COLUMNS["kpir"]
    cols_adv = OUTPUT_COLUMNS["advance"]

    data_kpir = preprocess_data_for_keras(DATA_FILES["kpir"], cols_kpir)
    data_adv_primary = preprocess_data_for_keras(DATA_FILES["advance"], cols_adv)
    data_advance = merge_bundles(data_adv_primary, data_kpir)

    xgb_kpir = load_xgb_bundle(XGB_DIRS["kpir"], cols_kpir, "kpir")
    xgb_adv_primary = load_xgb_bundle(XGB_DIRS["advance"], cols_adv, "advance")
    xgb_advance = merge_bundles(xgb_adv_primary, xgb_kpir)

    keras_kpir = load_keras_bundle(KERAS_DIRS["kpir"], cols_kpir, "kpir")
    keras_adv_primary = load_keras_bundle(KERAS_DIRS["advance"], cols_adv, "advance")
    keras_advance = merge_bundles(keras_adv_primary, keras_kpir)

    return {
        "kpir": {
            "columns": cols_kpir,
            "data": data_kpir,
            "xgb": xgb_kpir,
            "keras": keras_kpir,
        },
        "advance": {
            "columns": cols_adv,
            "data": data_advance,
            "xgb": xgb_advance,
            "keras": keras_advance,
        },
    }


def validate_registry(registry: dict):
    errors = []
    for profile, payload in registry.items():
        columns = payload.get("columns", [])
        xgb_models = payload.get("xgb", {}).get("models", {})
        keras_models = payload.get("keras", {}).get("models", {})

        for col in columns:
            if col not in xgb_models:
                errors.append(f"[{profile}] Brak modelu XGBoost dla kolumny: {col}")
            if col not in keras_models:
                errors.append(f"[{profile}] Brak modelu Keras dla kolumny: {col}")

    if errors:
        raise RuntimeError("Niekompletny zestaw modeli:\n" + "\n".join(errors))
