import pandas as pd
import numpy as np
import joblib
import os
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder, LabelEncoder
from sklearn.utils.class_weight import compute_class_weight
from sklearn.utils import shuffle
from xgboost import XGBClassifier
from numpy import hstack
from collections import Counter


# === Konfiguracja ===
output_columns = [
    "kolumna_kpir", "metoda_rozliczenia_podatku", "metoda_rozliczenia_vat",
    "odliczenie_vat", "cel_zakupu", "srodek_trwaly"
]

data = pd.read_csv("dane/dane_ai.csv", encoding='ISO-8859-2', sep=';')
typ_column = data.columns[4]

# === Czyszczenie danych
for col in ['company_id', 'nazwa', typ_column, 'typ_pozycji']:
    data[col] = data[col].astype(str).str.strip()
data = data[data['nazwa'].str.strip().astype(bool)]
data = data[data[typ_column] == 'BOOK']

# === BRAK jako osobna kategoria
for col in output_columns:
    if col in data.columns:
        data[col] = data[col].replace(['', ' ', None], np.nan)
        data[col] = data[col].fillna('BRAK')

# === TF-IDF
vectorizer = TfidfVectorizer(max_features=3000)
X_nazwa = vectorizer.fit_transform(data['nazwa']).toarray()
joblib.dump(vectorizer, f"vectorizer_nazwa.pkl")

encoder_typ = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
X_typ = encoder_typ.fit_transform(data[[typ_column]])
joblib.dump(encoder_typ, f"encoder_typ.pkl")

encoder_poz = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
X_poz = encoder_poz.fit_transform(data[['typ_pozycji']])
joblib.dump(encoder_poz, f"encoder_pozycja.pkl")

le_uid = LabelEncoder()
X_uid = le_uid.fit_transform(data['company_id']).reshape(-1, 1)
joblib.dump(le_uid, f"encoder_uid.pkl")

# === Łączenie cech
X = hstack([X_nazwa, X_typ, X_poz, X_uid])

# === Tworzenie folderów
os.makedirs("modele_xgb", exist_ok=True)
os.makedirs("raporty_xgb", exist_ok=True)

# === Trening dla każdej kolumny
for output_column in output_columns:
    print(f"\n==================== Trening kolumny: {output_column} ====================")

    y_raw = data[output_column]

    # === Stratify jeśli możliwe
    class_counts = y_raw.value_counts()
    stratify_param = y_raw if class_counts.min() > 1 else None

    X_train, X_test, y_train_raw, y_test_raw = train_test_split(
        X, y_raw, test_size=0.3, random_state=42, stratify=stratify_param
    )

    # === Label encoding y
    le_y = LabelEncoder()
    y_train_encoded = le_y.fit_transform(y_train_raw)
    y_test_encoded = le_y.transform(y_test_raw[y_test_raw.isin(le_y.classes_)])
    joblib.dump(le_y, f"modele_xgb/encoder_y_{output_column}.pkl")

    # === Compute class weights manually
    class_labels = np.unique(y_train_encoded)
    class_weights = compute_class_weight(class_weight='balanced', classes=class_labels, y=y_train_encoded)
    class_weight_dict = {i: w for i, w in zip(class_labels, class_weights)}

    # Boost rare classes even more (custom scaling)
    for k in class_weight_dict:
        class_weight_dict[k] *= 1.5  # << BOOST! (tuneable: 1.0 = neutral, 2.0 = stronger)

    # === Create sample weights
    sample_weight = np.array([class_weight_dict[y] for y in y_train_encoded])

    # === Model config
    num_classes = len(class_labels)
    objective_type = 'binary:logistic' if num_classes == 2 else 'multi:softprob'
    eval_metric = 'logloss' if num_classes == 2 else 'mlogloss'

    model = XGBClassifier(
        objective=objective_type,
        eval_metric=eval_metric,
        use_label_encoder=False,
        max_depth=6,
        learning_rate=0.1,
        n_estimators=300,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=1.0,   # L1 regularization (sparse features)
        reg_lambda=1.0,  # L2 regularization (stabilność)
        random_state=42
    )

    model.fit(X_train, y_train_encoded, sample_weight=sample_weight)
    joblib.dump(model, f"modele_xgb/model_{output_column}.pkl")

    # === Ewaluacja
    y_pred = model.predict(X_test[y_test_raw.isin(le_y.classes_)])
    y_pred_labels = le_y.inverse_transform(y_pred)
    y_true_labels = y_test_raw[y_test_raw.isin(le_y.classes_)].to_numpy()

    print(classification_report(y_true_labels, y_pred_labels, digits=3))

    accuracy = accuracy_score(y_true_labels, y_pred_labels)
    report = classification_report(y_true_labels, y_pred_labels, digits=3)

    print(f"Accuracy: {accuracy * 100:.2f}%")
    print(report)

    with open(f"raporty_xgb/raport_{output_column}.txt", "w", encoding="utf-8") as f:
        f.write(f"Accuracy: {accuracy * 100:.2f}%\n\n")
        f.write(report)
