import numpy as np
import pandas as pd

from api.services.inference_registry import (
    get_label_from_encoder,
    get_num_classes,
    pick_encoder,
    synthetic_label,
)


def predict_xgb(
    bundle: dict,
    columns: list[str],
    X_nazwa,
    typ_value: str,
    typ_pozycji: str,
    company_id: str,
):
    result_xgb = {}
    xgb_has_errors = False
    try:
        enc_typ_xgb = bundle["xgb"].get("enc_typ")
        enc_poz_xgb = bundle["xgb"].get("enc_poz")
        enc_uid_xgb = bundle["xgb"].get("enc_uid")

        if enc_typ_xgb is None or enc_poz_xgb is None:
            raise RuntimeError("Brak encoderow wejsciowych XGBoost (enc_typ/enc_poz).")

        X_typ_xgb = enc_typ_xgb.transform(
            pd.DataFrame([[typ_value]], columns=[enc_typ_xgb.feature_names_in_[0]])
        )
        X_poz_xgb = enc_poz_xgb.transform(
            pd.DataFrame([[typ_pozycji]], columns=["typ_pozycji"])
        )

        if enc_uid_xgb is not None and company_id in getattr(enc_uid_xgb, "classes_", []):
            uid_encoded = enc_uid_xgb.transform([company_id]).reshape(1, -1)
        else:
            uid_encoded = np.array([[0]])

        X_combined_xgb = np.hstack([X_nazwa, X_typ_xgb, X_poz_xgb, uid_encoded])

        for col in columns:
            model = bundle["xgb"].get("models", {}).get(col)
            encoder_y = bundle["xgb"].get("encoders_y", {}).get(col)
            if model is None or encoder_y is None:
                result_xgb[col] = "model_not_found"
                xgb_has_errors = True
                continue

            y_pred = model.predict(X_combined_xgb)
            label = encoder_y.inverse_transform(y_pred)[0]
            result_xgb[col] = label

    except Exception as exc:
        result_xgb["error"] = f"Blad XGBoost: {str(exc)}"
        xgb_has_errors = True

    return result_xgb, xgb_has_errors


def predict_keras(
    bundle: dict,
    columns: list[str],
    X_nazwa,
    typ_value: str,
    typ_pozycji: str,
    company_id: str,
):
    result_keras = {}
    keras_has_errors = False
    try:
        data_bundle = bundle.get("data")
        keras_bundle = bundle.get("keras")

        if data_bundle is None:
            raise RuntimeError("Brak data bundle dla profilu.")

        typ_column = data_bundle["typ_column"]
        company_ids = data_bundle["company_ids"]
        encoder_typ_keras = data_bundle["encoder_typ_keras"]
        encoder_pozycja_keras = data_bundle["encoder_pozycja_keras"]

        if isinstance(company_ids, np.ndarray) and company_ids.size > 0:
            match_idx = np.where(company_ids == company_id)[0]
            company_idx = int(match_idx[0]) if match_idx.size > 0 else 0
        else:
            company_idx = 0

        X_typ_keras = encoder_typ_keras.transform(pd.DataFrame([[typ_value]], columns=[typ_column]))
        X_poz_keras = encoder_pozycja_keras.transform(pd.DataFrame([[typ_pozycji]], columns=["typ_pozycji"]))

        for col in columns:
            model = (keras_bundle or {}).get("models", {}).get(col) if keras_bundle else None
            if model is None:
                result_keras[col] = "model_not_found"
                keras_has_errors = True
                continue

            n_out = int(model.output_shape[-1])

            enc_candidates = [
                (keras_bundle or {}).get("encoders_y", {}).get(col) if keras_bundle else None,
                bundle.get("xgb", {}).get("encoders_y", {}).get(col),
                data_bundle["encoders_y_keras"].get(col),
            ]

            prefer = 2 if n_out == 1 else n_out
            enc_y = pick_encoder(enc_candidates, prefer_classes=prefer, allow_more=True)

            inputs_dict = {
                "input_nazwa": X_nazwa,
                "input_typ": X_typ_keras,
                "input_pozycja": X_poz_keras,
                "input_user": np.array([[company_idx]]),
            }

            pred = model.predict(inputs_dict, verbose=0)
            flat = np.ravel(pred)

            if n_out == 1:
                prob1 = float(flat[0])
                class_index = 1 if prob1 >= 0.5 else 0

                if enc_y is None:
                    result_keras[col] = synthetic_label(class_index)
                else:
                    n_classes = get_num_classes(enc_y) or 0
                    if n_classes < 2:
                        result_keras[col] = synthetic_label(class_index)
                    else:
                        result_keras[col] = get_label_from_encoder(enc_y, class_index)
            else:
                class_index = int(np.argmax(flat))
                if enc_y is None:
                    result_keras[col] = synthetic_label(class_index)
                else:
                    n_classes = get_num_classes(enc_y) or 0
                    if class_index >= n_classes:
                        result_keras[col] = synthetic_label(class_index)
                    else:
                        result_keras[col] = get_label_from_encoder(enc_y, class_index)

    except Exception as exc:
        result_keras["error"] = f"Blad Keras: {str(exc)}"
        keras_has_errors = True

    return result_keras, keras_has_errors
