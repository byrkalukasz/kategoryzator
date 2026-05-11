import argparse
import json
import os
import random

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
from tensorflow.keras.initializers import lecun_normal
from tensorflow.keras.layers import BatchNormalization, Concatenate, Dense, Dropout, Embedding, Flatten, Input
from tensorflow.keras.models import Model
from tensorflow.keras.optimizers import Adam

OUTPUT_COLUMNS = [
    "kolumna_kpir",
    "metoda_rozliczenia_podatku",
    "metoda_rozliczenia_vat",
    "odliczenie_vat",
    "cel_zakupu",
    "srodek_trwaly",
]


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)


def load_and_clean_data(csv_path: str) -> tuple[pd.DataFrame, str]:
    data = pd.read_csv(csv_path, encoding="ISO-8859-2", sep=";")
    typ_column = data.columns[4]

    for col in ["company_id", "nazwa", typ_column, "typ_pozycji"]:
        data[col] = data[col].astype(str).str.strip()

    data = data[data["nazwa"].str.strip().astype(bool)]
    data = data[data[typ_column] == "BOOK"]

    if "odliczenie_vat" in data.columns:
        data["odliczenie_vat"] = data["odliczenie_vat"].replace(["", " ", None], np.nan)
        data["odliczenie_vat"] = data["odliczenie_vat"].fillna("BRAK")

    if "cel_zakupu" in data.columns:
        data["cel_zakupu"] = data["cel_zakupu"].replace(["", " ", None], np.nan)
        data["cel_zakupu"] = data["cel_zakupu"].fillna("BRAK")

    return data.reset_index(drop=True), typ_column


def prepare_features(
    data: pd.DataFrame,
    typ_column: str,
    output_column: str,
    test_size: float,
    seed: int,
):
    if output_column not in data.columns:
        raise ValueError(f"Brak kolumny wyjściowej: {output_column}")

    data = data.copy()
    data[output_column] = data[output_column].fillna("BRAK")

    try:
        train_data, test_data = train_test_split(
            data,
            test_size=test_size,
            random_state=seed,
            stratify=data[output_column],
        )
    except ValueError as exc:
        if "least populated class" not in str(exc):
            raise
        print(
            f"[WARN] Kolumna '{output_column}': za mało próbek w rzadkich klasach, "
            "używam split bez stratify."
        )
        train_data, test_data = train_test_split(
            data,
            test_size=test_size,
            random_state=seed,
            stratify=None,
        )
    train_data = train_data.reset_index(drop=True)
    test_data = test_data.reset_index(drop=True)

    # Twarda sanitacja tekstu pod TF-IDF (ochrona przed NaN/None/"nan")
    train_data["nazwa"] = train_data["nazwa"].fillna("").astype(str).str.strip()
    test_data["nazwa"] = test_data["nazwa"].fillna("").astype(str).str.strip()
    train_data = train_data[~train_data["nazwa"].isin({"", "nan", "None", "none", "NaN"})]
    test_data = test_data[~test_data["nazwa"].isin({"", "nan", "None", "none", "NaN"})]

    # Ujednolicenie company_id (ochrona przed mieszanką typów str/float)
    train_data["company_id"] = train_data["company_id"].fillna("").astype(str).str.strip()
    test_data["company_id"] = test_data["company_id"].fillna("").astype(str).str.strip()
    train_data = train_data[~train_data["company_id"].isin({"", "nan", "None", "none", "NaN"})]
    test_data = test_data[~test_data["company_id"].isin({"", "nan", "None", "none", "NaN"})]

    if train_data.empty or test_data.empty:
        raise ValueError(
            f"Po czyszczeniu kolumn 'nazwa'/'company_id' brakuje danych train/test dla kolumny: {output_column}."
        )

    vectorizer = TfidfVectorizer(max_features=3000)
    x_train_nazwa = vectorizer.fit_transform(train_data["nazwa"]).toarray()
    x_test_nazwa = vectorizer.transform(test_data["nazwa"]).toarray()

    encoder_typ = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    x_train_typ = encoder_typ.fit_transform(train_data[[typ_column]])
    x_test_typ = encoder_typ.transform(test_data[[typ_column]])

    encoder_pozycja = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    x_train_poz = encoder_pozycja.fit_transform(train_data[["typ_pozycji"]])
    x_test_poz = encoder_pozycja.transform(test_data[["typ_pozycji"]])

    user_ids_train = np.unique(train_data["company_id"])
    user_id_map = {uid: idx + 1 for idx, uid in enumerate(user_ids_train)}
    x_train_uid = np.array([user_id_map.get(uid, 0) for uid in train_data["company_id"]], dtype=np.int32)
    x_test_uid = np.array([user_id_map.get(uid, 0) for uid in test_data["company_id"]], dtype=np.int32)
    num_users = len(user_ids_train) + 1

    train_classes = set(train_data[output_column].astype(str))
    test_class_mask = test_data[output_column].astype(str).isin(train_classes)
    if not bool(test_class_mask.all()):
        dropped = int((~test_class_mask).sum())
        print(
            f"[WARN] Kolumna '{output_column}': pomijam {dropped} rekordów testu z klasami niewidzianymi w train."
        )
        keep_idx = test_class_mask.to_numpy()
        test_data = test_data.loc[test_class_mask].reset_index(drop=True)
        x_test_nazwa = x_test_nazwa[keep_idx]
        x_test_typ = x_test_typ[keep_idx]
        x_test_poz = x_test_poz[keep_idx]
        x_test_uid = x_test_uid[keep_idx]

    if len(test_data) == 0:
        raise ValueError(
            f"Po filtracji klas testowych brak danych walidacyjnych dla kolumny: {output_column}."
        )

    encoder_y = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    y_train = encoder_y.fit_transform(train_data[[output_column]])
    y_test = encoder_y.transform(test_data[[output_column]])

    return {
        "vectorizer": vectorizer,
        "encoder_y": encoder_y,
        "x_train": {
            "input_nazwa": x_train_nazwa,
            "input_typ": x_train_typ,
            "input_pozycja": x_train_poz,
            "input_user": x_train_uid.reshape(-1, 1),
        },
        "x_test": {
            "input_nazwa": x_test_nazwa,
            "input_typ": x_test_typ,
            "input_pozycja": x_test_poz,
            "input_user": x_test_uid.reshape(-1, 1),
        },
        "y_train": y_train,
        "y_test": y_test,
        "num_users": num_users,
    }


def build_model(hparams: dict, train_bundle: dict) -> Model:
    x_train = train_bundle["x_train"]
    y_train = train_bundle["y_train"]

    input_nazwa = Input(shape=(x_train["input_nazwa"].shape[1],), name="input_nazwa")
    input_typ = Input(shape=(x_train["input_typ"].shape[1],), name="input_typ")
    input_pozycja = Input(shape=(x_train["input_pozycja"].shape[1],), name="input_pozycja")
    input_user = Input(shape=(1,), dtype="int32", name="input_user")

    embed_user = Embedding(input_dim=train_bundle["num_users"], output_dim=hparams["embedding_dim"])(input_user)
    embed_user_flat = Flatten()(embed_user)

    concat = Concatenate()([input_nazwa, input_typ, input_pozycja, embed_user_flat])

    if hparams["activation"] == "selu":
        x = Dense(hparams["units_1"], activation="selu", kernel_initializer=lecun_normal())(concat)
    else:
        x = Dense(hparams["units_1"], activation="relu")(concat)

    if hparams["batch_norm"]:
        x = BatchNormalization()(x)

    x = Dropout(hparams["dropout_1"])(x)

    if hparams["activation"] == "selu":
        x = Dense(hparams["units_2"], activation="selu", kernel_initializer=lecun_normal())(x)
    else:
        x = Dense(hparams["units_2"], activation="relu")(x)

    x = Dropout(hparams["dropout_2"])(x)

    output = Dense(y_train.shape[1], activation="softmax")(x)

    model = Model(
        inputs={
            "input_nazwa": input_nazwa,
            "input_typ": input_typ,
            "input_pozycja": input_pozycja,
            "input_user": input_user,
        },
        outputs=output,
    )

    model.compile(
        optimizer=Adam(learning_rate=hparams["learning_rate"]),
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def make_datasets(train_bundle: dict, batch_size: int):
    x_train = train_bundle["x_train"]
    x_test = train_bundle["x_test"]
    y_train = train_bundle["y_train"]
    y_test = train_bundle["y_test"]

    train_dataset = (
        tf.data.Dataset.from_tensor_slices((x_train, y_train))
        .shuffle(len(y_train), reshuffle_each_iteration=True)
        .batch(batch_size)
        .cache()
        .prefetch(tf.data.AUTOTUNE)
    )

    val_dataset = (
        tf.data.Dataset.from_tensor_slices((x_test, y_test))
        .batch(batch_size)
        .cache()
        .prefetch(tf.data.AUTOTUNE)
    )

    return train_dataset, val_dataset


def sample_hparams(rng: np.random.Generator) -> dict:
    return {
        "units_1": int(rng.choice([64, 128, 256])),
        "units_2": int(rng.choice([32, 64, 128])),
        "dropout_1": float(rng.choice([0.1, 0.2, 0.3, 0.4, 0.5])),
        "dropout_2": float(rng.choice([0.0, 0.1, 0.2, 0.3, 0.4])),
        "embedding_dim": int(rng.choice([8, 16, 32])),
        "learning_rate": float(rng.choice([1e-4, 3e-4, 1e-3, 3e-3])),
        "batch_size": int(rng.choice([16, 32, 64])),
        "batch_norm": bool(rng.choice([True, False])),
        "activation": str(rng.choice(["selu", "relu"])),
    }


def run_search(train_bundle: dict, trials: int, epochs: int, seed: int):
    rng = np.random.default_rng(seed)
    all_results = []
    best = None

    for trial_idx in range(1, trials + 1):
        tf.keras.backend.clear_session()
        hparams = sample_hparams(rng)

        model = build_model(hparams, train_bundle)
        train_dataset, val_dataset = make_datasets(train_bundle, hparams["batch_size"])

        callbacks = [
            EarlyStopping(monitor="val_accuracy", patience=10, min_delta=0.001, restore_best_weights=True),
            ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=3),
        ]

        history = model.fit(
            train_dataset,
            validation_data=val_dataset,
            epochs=epochs,
            callbacks=callbacks,
            verbose=0,
        )

        pred = model.predict(val_dataset, verbose=0)
        y_pred = np.argmax(pred, axis=1)
        y_true = np.argmax(train_bundle["y_test"], axis=1)

        macro_f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
        val_acc = float(max(history.history.get("val_accuracy", [0.0])))

        result = {
            "trial": trial_idx,
            "macro_f1": macro_f1,
            "val_accuracy": val_acc,
            "hparams": hparams,
        }
        all_results.append(result)

        is_better = best is None or (macro_f1 > best["macro_f1"]) or (
            macro_f1 == best["macro_f1"] and val_acc > best["val_accuracy"]
        )
        if is_better:
            best = result

        print(
            f"[Trial {trial_idx:02d}/{trials}] macro_f1={macro_f1:.4f} "
            f"val_acc={val_acc:.4f} hparams={hparams}"
        )

    return best, all_results


def train_final_model(train_bundle: dict, hparams: dict, output_column: str, epochs: int):
    tf.keras.backend.clear_session()
    model = build_model(hparams, train_bundle)
    train_dataset, val_dataset = make_datasets(train_bundle, hparams["batch_size"])

    callbacks = [
        EarlyStopping(monitor="val_accuracy", patience=15, min_delta=0.001, restore_best_weights=True),
        ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=3),
    ]

    history = model.fit(
        train_dataset,
        validation_data=val_dataset,
        epochs=epochs,
        callbacks=callbacks,
        verbose=0,
    )

    pred = model.predict(val_dataset, verbose=0)
    y_pred = np.argmax(pred, axis=1)
    y_true = np.argmax(train_bundle["y_test"], axis=1)

    print("\n=== Final model report ===")
    print(classification_report(y_true, y_pred, zero_division=0))

    model_path = f"model_{output_column}.keras"
    model.save(model_path)
    print(f"Zapisano model: {model_path}")

    return history


def parse_args():
    parser = argparse.ArgumentParser(description="Random-search hiperparametrów dla modelu Keras")
    parser.add_argument("--csv-path", default="dane/dane_ai.csv")
    parser.add_argument("--output-column", default="cel_zakupu", help="Nazwa kolumny lub 'all'")
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--test-size", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-best", action="store_true")
    return parser.parse_args()


def run_for_output_column(args, data: pd.DataFrame, typ_column: str, output_column: str):
    print(f"\n==================== Tuning dla kolumny: {output_column} ====================")

    train_bundle = prepare_features(
        data=data,
        typ_column=typ_column,
        output_column=output_column,
        test_size=args.test_size,
        seed=args.seed,
    )

    vectorizer_path = f"vectorizer_nazwa_nn_{output_column}.pkl"
    joblib.dump(train_bundle["vectorizer"], vectorizer_path)
    print(f"Zapisano vectorizer: {vectorizer_path}")

    best, all_results = run_search(
        train_bundle=train_bundle,
        trials=args.trials,
        epochs=args.epochs,
        seed=args.seed,
    )

    print("\n=== Najlepsza konfiguracja ===")
    print(json.dumps(best, ensure_ascii=False, indent=2))

    results_path = f"tuning_results_{output_column}.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"Zapisano historię tuningu: {results_path}")

    if args.train_best:
        train_final_model(
            train_bundle=train_bundle,
            hparams=best["hparams"],
            output_column=output_column,
            epochs=args.epochs,
        )

    return {
        "output_column": output_column,
        "best_macro_f1": best["macro_f1"],
        "best_val_accuracy": best["val_accuracy"],
        "best_hparams": best["hparams"],
        "results_file": results_path,
        "vectorizer_file": vectorizer_path,
    }


def main():
    args = parse_args()
    set_seed(args.seed)

    data, typ_column = load_and_clean_data(args.csv_path)

    if args.output_column == "all":
        available_columns = [col for col in OUTPUT_COLUMNS if col in data.columns]
        if not available_columns:
            raise ValueError("Brak wspieranych kolumn wyjściowych w danych.")

        summary = []
        for output_column in available_columns:
            summary.append(run_for_output_column(args, data, typ_column, output_column))

        summary_path = "tuning_summary_all_columns.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        print("\n=== Podsumowanie wszystkich kolumn ===")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"Zapisano raport zbiorczy: {summary_path}")
    else:
        run_for_output_column(args, data, typ_column, args.output_column)


if __name__ == "__main__":
    main()
