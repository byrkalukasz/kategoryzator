import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import tensorflow as tf
import os
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense, Dropout, BatchNormalization, Embedding, Flatten, Concatenate
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
from tensorflow.keras.initializers import lecun_normal
from sklearn.utils.multiclass import unique_labels
from sklearn.utils.class_weight import compute_class_weight
import joblib

# === Wczytaj dane ===
data = pd.read_csv("dane/dane_ai_ryczalt.csv", encoding='ISO-8859-2', sep=';')
typ_column = data.columns[4]

# === Czyszczenie ===
for col in ['company_id', 'nazwa', typ_column, 'typ_pozycji']:
    data[col] = data[col].astype(str).str.strip()
data = data[data['nazwa'].str.strip().astype(bool)]
data = data[data[typ_column] == 'ADVANCED']

if 'odliczenie_vat' in data.columns:
    data['odliczenie_vat'] = data['odliczenie_vat'].replace(['', ' ', None], np.nan)
    data['odliczenie_vat'] = data['odliczenie_vat'].fillna('BRAK')  

if 'medota_rozliczenia_podatku' in data.columns and 'metoda_rozliczenia_podatku' not in data.columns:
    data = data.rename(columns={'medota_rozliczenia_podatku': 'metoda_rozliczenia_podatku'})

if 'cel_zakupu' in data.columns:
    data['cel_zakupu'] = data['cel_zakupu'].replace(['', ' ', None], np.nan)
    data['cel_zakupu'] = data['cel_zakupu'].fillna('BRAK')

# === Listy kolumn wyjściowych ===
output_columns = [
    "metoda_rozliczenia_podatku", "metoda_rozliczenia_vat",
    "odliczenie_vat", "cel_zakupu", "srodek_trwaly"
]
# === Kodowanie wejść wspólne dla wszystkich modeli ===
vectorizer = TfidfVectorizer(max_features=3000)
X_nazwa = vectorizer.fit_transform(data['nazwa']).toarray()
joblib.dump(vectorizer, "vectorizer_nazwa_nn.pkl")

encoder_typ = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
X_typ = encoder_typ.fit_transform(data[[typ_column]])

encoder_pozycja = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
X_pozycja = encoder_pozycja.fit_transform(data[['typ_pozycji']])

user_ids, user_id_index = np.unique(data['company_id'], return_inverse=True)
num_users = len(user_ids)

# === Pętla po kolumnach ===
for output_column in output_columns:
    print(f"\n==================== Trenowanie dla kolumny: {output_column} ====================")

    data[output_column] = data[output_column].fillna("BRAK")
    encoder_y = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
    y = encoder_y.fit_transform(data[[output_column]])

    X_train_nazwa, X_test_nazwa, \
    X_train_typ, X_test_typ, \
    X_train_poz, X_test_poz, \
    X_train_uid, X_test_uid, \
    y_train, y_test = train_test_split(
        X_nazwa, X_typ, X_pozycja, user_id_index, y, test_size=0.3, random_state=42
    )

    # === MODELE ===
    input_nazwa = Input(shape=(X_train_nazwa.shape[1],), name="input_nazwa")
    input_typ = Input(shape=(X_train_typ.shape[1],), name="input_typ")
    input_pozycja = Input(shape=(X_train_poz.shape[1],), name="input_pozycja")
    input_user = Input(shape=(1,), dtype='int32', name="input_user")

    embed_user = Embedding(input_dim=num_users, output_dim=16)(input_user)
    embed_user_flat = Flatten()(embed_user)

    concat = Concatenate()([input_nazwa, input_typ, input_pozycja, embed_user_flat])

    if output_column in ['srodek_trwaly','cel_zakupu']:
        x = Dense(128, activation='selu', kernel_initializer=lecun_normal())(concat)
        x = Dropout(0.2)(x)
        x = Dense(64)(x)
    elif output_column in ['metoda_rozliczenia_podatku', 'metoda_rozliczenia_vat']:
        x = Dense(128, activation='selu', kernel_initializer=lecun_normal())(concat)
        x = BatchNormalization()(x)
        x = Dropout(0.8)(x)
        x = Dense(64, activation='selu')(x)
        x = Dropout(0.5)(x)
    else:
        x = Dense(128, activation='selu', kernel_initializer=lecun_normal())(concat)
        x = BatchNormalization()(x)
        x = Dropout(0.9)(x)
        x = Dense(64, activation='selu')(x)
        x = Dropout(0.8)(x)

    output = Dense(y_train.shape[1], activation='softmax')(x)
    model = Model(inputs={
        "input_nazwa": input_nazwa,
        "input_typ": input_typ,
        "input_pozycja": input_pozycja,
        "input_user": input_user
    }, outputs=output)

    model.compile(optimizer='adam', loss='categorical_crossentropy', metrics=['accuracy'])

    callbacks = [
        EarlyStopping(monitor='val_accuracy', patience=60, min_delta=0.001, restore_best_weights=True),
        ModelCheckpoint(f"model_{output_column}_advance.keras", save_best_only=True),
        ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=5)
    ]

    # === tf.data.Dataset zamiast numpy ===
    train_dataset = tf.data.Dataset.from_tensor_slices((
        {
            "input_nazwa": X_train_nazwa,
            "input_typ": X_train_typ,
            "input_pozycja": X_train_poz,
            "input_user": X_train_uid.reshape(-1, 1)
        },
        y_train
    )).batch(8).prefetch(tf.data.AUTOTUNE)

    val_dataset = tf.data.Dataset.from_tensor_slices((
        {
            "input_nazwa": X_test_nazwa,
            "input_typ": X_test_typ,
            "input_pozycja": X_test_poz,
            "input_user": X_test_uid.reshape(-1, 1)
        },
        y_test
    )).batch(8).prefetch(tf.data.AUTOTUNE)

    # === FIT ===
    history = model.fit(
        train_dataset,
        validation_data=val_dataset,
        epochs=1000,
        callbacks=callbacks,
        verbose=0
    )

    if output_column == 'metoda_rozliczenia_podatku':
        model.save("model_medota_rozliczenia_podatku_advance.keras")

    # === Ewaluacja ===
    pred = model.predict(val_dataset)
    y_pred = np.argmax(pred, axis=1)
    y_true = np.argmax(y_test, axis=1)
    print("\n📊 Classification report:")
    labels_used = np.unique(y_true)
    class_names = encoder_y.categories_[0][labels_used]
    print(classification_report(y_true, y_pred, labels=labels_used, target_names=class_names))

    # === Wykresy ===
    plt.figure(figsize=(10, 4))
    plt.plot(history.history['accuracy'], label='Train Accuracy')
    plt.plot(history.history['val_accuracy'], label='Val Accuracy')
    plt.title(f"Dokładność - {output_column}")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(f"plots/accuracy_{output_column}.png")
    plt.close()

    plt.figure(figsize=(10, 4))
    plt.plot(history.history['loss'], label='Train Loss')
    plt.plot(history.history['val_loss'], label='Val Loss')
    plt.title(f"Strata - {output_column}")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(f"plots/loss_{output_column}.png")
    plt.close()
