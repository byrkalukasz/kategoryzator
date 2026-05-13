import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import tensorflow as tf
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense, Dropout, BatchNormalization, Embedding, Flatten, Concatenate
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
from tensorflow.keras.initializers import lecun_normal
from tensorflow.keras.optimizers import Adam
import joblib
import os

# === Wczytaj dane ===
data = pd.read_csv("dane/dane_ai.csv", encoding='ISO-8859-2', sep=';')
typ_column = data.columns[4]

# === Czyszczenie ===
for col in ['company_id', 'nazwa', typ_column, 'typ_pozycji']:
    data[col] = data[col].astype(str).str.strip()
data = data[data['nazwa'].str.strip().astype(bool)]
data = data[data[typ_column] == 'BOOK']

if 'odliczenie_vat' in data.columns:
    data['odliczenie_vat'] = data['odliczenie_vat'].replace(['', ' ', None], np.nan)
    data['odliczenie_vat'] = data['odliczenie_vat'].fillna('BRAK')  # lub 'BRAK', jeśli wolisz

if 'cel_zakupu' in data.columns:
    data['cel_zakupu'] = data['cel_zakupu'].replace(['', ' ', None], np.nan)
    data['cel_zakupu'] = data['cel_zakupu'].fillna('BRAK')
# === Listy kolumn wyjściowych ===
output_columns = [
    "kolumna_kpir","metoda_rozliczenia_podatku", "metoda_rozliczenia_vat",
    "odliczenie_vat", "cel_zakupu", "srodek_trwaly"
]

# === Split train/test przed fitowaniem feature engineering (bez leakage) ===
train_data, test_data = train_test_split(data, test_size=0.3, random_state=42)
train_data = train_data.reset_index(drop=True)
test_data = test_data.reset_index(drop=True)

# Twarda sanitacja pod TF-IDF i mapowanie userów
train_data['nazwa'] = train_data['nazwa'].fillna('').astype(str).str.strip()
test_data['nazwa'] = test_data['nazwa'].fillna('').astype(str).str.strip()
train_data['company_id'] = train_data['company_id'].fillna('').astype(str).str.strip()
test_data['company_id'] = test_data['company_id'].fillna('').astype(str).str.strip()

invalid_values = {'', 'nan', 'None', 'none', 'NaN'}
train_data = train_data[
    ~train_data['nazwa'].isin(invalid_values) & ~train_data['company_id'].isin(invalid_values)
].reset_index(drop=True)
test_data = test_data[
    ~test_data['nazwa'].isin(invalid_values) & ~test_data['company_id'].isin(invalid_values)
].reset_index(drop=True)

if train_data.empty or test_data.empty:
    raise ValueError("Po czyszczeniu kolumn 'nazwa'/'company_id' brak danych train/test.")

# === Kodowanie wejść na train, transform na test ===
vectorizer = TfidfVectorizer(max_features=3000)
X_train_nazwa = vectorizer.fit_transform(train_data['nazwa']).toarray()
X_test_nazwa = vectorizer.transform(test_data['nazwa']).toarray()
joblib.dump(vectorizer, "vectorizer_nazwa_nn.pkl")

encoder_typ = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
X_train_typ = encoder_typ.fit_transform(train_data[[typ_column]])
X_test_typ = encoder_typ.transform(test_data[[typ_column]])

encoder_pozycja = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
X_train_poz = encoder_pozycja.fit_transform(train_data[['typ_pozycji']])
X_test_poz = encoder_pozycja.transform(test_data[['typ_pozycji']])

user_ids_train = np.unique(train_data['company_id'])
user_id_map = {uid: idx + 1 for idx, uid in enumerate(user_ids_train)}
X_train_uid = np.array([user_id_map.get(uid, 0) for uid in train_data['company_id']], dtype=np.int32)
X_test_uid = np.array([user_id_map.get(uid, 0) for uid in test_data['company_id']], dtype=np.int32)
num_users = len(user_ids_train) + 1

# === Tworzenie folderów wyjściowych ===
os.makedirs("KPIR_kerras", exist_ok=True)
os.makedirs("plots", exist_ok=True)

# === Pętla po kolumnach ===
for output_column in output_columns:
    print(f"\n==================== Trenowanie dla kolumny: {output_column} ====================")

    train_data[output_column] = train_data[output_column].fillna("BRAK")
    test_data[output_column] = test_data[output_column].fillna("BRAK")
    encoder_y = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
    y_train = encoder_y.fit_transform(train_data[[output_column]])
    y_test = encoder_y.transform(test_data[[output_column]])

    if y_train.shape[1] < 2:
        print(f"  ⚠️  Pomijam '{output_column}' — tylko 1 klasa w danych treningowych.")
        continue

    # === MODELE ===
    input_nazwa = Input(shape=(X_train_nazwa.shape[1],), name="input_nazwa")
    input_typ = Input(shape=(X_train_typ.shape[1],), name="input_typ")
    input_pozycja = Input(shape=(X_train_poz.shape[1],), name="input_pozycja")
    input_user = Input(shape=(1,), dtype='int32', name="input_user")

    embed_user = Embedding(input_dim=num_users, output_dim=32)(input_user)
    embed_user_flat = Flatten()(embed_user)

    concat = Concatenate()([input_nazwa, input_typ, input_pozycja, embed_user_flat])


#---Budowanie sieci neuronowej per kolumna--

    if output_column in ['kolumna_kpir']:
        x = Dense(128, activation='selu', kernel_initializer=lecun_normal())(concat)
        x = Dropout(0.3)(x)
        x = Dense(32)(x)
        x = Dropout(0.0)(x)
    elif output_column in ['srodek_trwaly']:
        x = Dense(64, activation='selu', kernel_initializer=lecun_normal())(concat)
        x = Dropout(0.4)(x)
        x = Dense(128)(x)
        x = Dropout(0.2)(x)
    elif output_column in ['cel_zakupu']:
        x = Dense(64, activation='relu', kernel_initializer=lecun_normal())(concat)
        x = Dropout(0.1)(x)
        x = Dense(128)(x)
        x = Dropout(0.4)(x)
    elif output_column in ['metoda_rozliczenia_podatku']:
        x = Dense(64, activation='selu', kernel_initializer=lecun_normal())(concat)
        x = Dropout(0.5)(x)
        x = Dense(64,)(x)
        x = Dropout(0.4)(x)
    elif output_column in ['metoda_rozliczenia_vat']:
        x = Dense(128, activation='relu', kernel_initializer=lecun_normal())(concat)
        x = Dropout(0.5)(x)
        x = Dense(128)(x)
        x = Dropout(0.1)(x)
    elif output_column in ['odliczenie_vat']:
        x = Dense(64, activation='selu', kernel_initializer=lecun_normal())(concat)
        x = Dropout(0.4)(x)
        x = Dense(128)(x)
        x = Dropout(0.2)(x)

##Wspólne
    output = Dense(y_train.shape[1], activation='softmax')(x)
    model = Model(inputs={
        "input_nazwa": input_nazwa,
        "input_typ": input_typ,
        "input_pozycja": input_pozycja,
        "input_user": input_user
    }, outputs=output)

##To ma być zalezne od kolumny
    if output_column in ['kolumna_kpir']:
        model.compile(optimizer=Adam(learning_rate=0.001), loss='categorical_crossentropy', metrics=['accuracy'])

        callbacks = [
            EarlyStopping(monitor='val_accuracy', patience=20, min_delta=0.001, restore_best_weights=True),
            ModelCheckpoint(f"KPIR_kerras/model_{output_column}.keras", save_best_only=True),
            ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3)
        ]

        train_dataset = tf.data.Dataset.from_tensor_slices((
            {
                "input_nazwa": X_train_nazwa,
                "input_typ": X_train_typ,
                "input_pozycja": X_train_poz,
                "input_user": X_train_uid.reshape(-1, 1)
            },
            y_train
        )).shuffle(len(X_train_nazwa), reshuffle_each_iteration=True).batch(64).cache().prefetch(tf.data.AUTOTUNE)
    
        val_dataset = tf.data.Dataset.from_tensor_slices((
        {
            "input_nazwa": X_test_nazwa,
            "input_typ": X_test_typ,
            "input_pozycja": X_test_poz,
            "input_user": X_test_uid.reshape(-1, 1)
        },
        y_test
        )).batch(64).cache().prefetch(tf.data.AUTOTUNE)
    
    elif output_column in ['srodek_trwaly']:
        model.compile(optimizer=Adam(learning_rate=0.003), loss='categorical_crossentropy', metrics=['accuracy'])

        callbacks = [
            EarlyStopping(monitor='val_accuracy', patience=20, min_delta=0.001, restore_best_weights=True),
            ModelCheckpoint(f"KPIR_kerras/model_{output_column}.keras", save_best_only=True),
            ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3)
        ]

        train_dataset = tf.data.Dataset.from_tensor_slices((
            {
                "input_nazwa": X_train_nazwa,
                "input_typ": X_train_typ,
                "input_pozycja": X_train_poz,
                "input_user": X_train_uid.reshape(-1, 1)
            },
            y_train
        )).shuffle(len(X_train_nazwa), reshuffle_each_iteration=True).batch(16).cache().prefetch(tf.data.AUTOTUNE)
        
        val_dataset = tf.data.Dataset.from_tensor_slices((
        {
            "input_nazwa": X_test_nazwa,
            "input_typ": X_test_typ,
            "input_pozycja": X_test_poz,
            "input_user": X_test_uid.reshape(-1, 1)
        },
        y_test
        )).batch(16).cache().prefetch(tf.data.AUTOTUNE)
    
    elif output_column in ['cel_zakupu']:
        model.compile(optimizer=Adam(learning_rate=0.003), loss='categorical_crossentropy', metrics=['accuracy'])

        callbacks = [
            EarlyStopping(monitor='val_accuracy', patience=20, min_delta=0.001, restore_best_weights=True),
            ModelCheckpoint(f"KPIR_kerras/model_{output_column}.keras", save_best_only=True),
            ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3)
        ]

        train_dataset = tf.data.Dataset.from_tensor_slices((
            {
                "input_nazwa": X_train_nazwa,
                "input_typ": X_train_typ,
                "input_pozycja": X_train_poz,
                "input_user": X_train_uid.reshape(-1, 1)
            },
            y_train
        )).shuffle(len(X_train_nazwa), reshuffle_each_iteration=True).batch(64).cache().prefetch(tf.data.AUTOTUNE)
    
        val_dataset = tf.data.Dataset.from_tensor_slices((
        {
            "input_nazwa": X_test_nazwa,
            "input_typ": X_test_typ,
            "input_pozycja": X_test_poz,
            "input_user": X_test_uid.reshape(-1, 1)
        },
        y_test
        )).batch(64).cache().prefetch(tf.data.AUTOTUNE)
    
    elif output_column in ['metoda_rozliczenia_podatku']:
        model.compile(optimizer=Adam(learning_rate=0.001), loss='categorical_crossentropy', metrics=['accuracy'])

        callbacks = [
            EarlyStopping(monitor='val_accuracy', patience=20, min_delta=0.001, restore_best_weights=True),
            ModelCheckpoint(f"KPIR_kerras/model_{output_column}.keras", save_best_only=True),
            ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3)
        ]

        train_dataset = tf.data.Dataset.from_tensor_slices((
            {
                "input_nazwa": X_train_nazwa,
                "input_typ": X_train_typ,
                "input_pozycja": X_train_poz,
                "input_user": X_train_uid.reshape(-1, 1)
            },
            y_train
        )).shuffle(len(X_train_nazwa), reshuffle_each_iteration=True).batch(32).cache().prefetch(tf.data.AUTOTUNE)
        
        val_dataset = tf.data.Dataset.from_tensor_slices((
        {
            "input_nazwa": X_test_nazwa,
            "input_typ": X_test_typ,
            "input_pozycja": X_test_poz,
            "input_user": X_test_uid.reshape(-1, 1)
        },
        y_test
        )).batch(32).cache().prefetch(tf.data.AUTOTUNE)
    
    elif output_column in ['metoda_rozliczenia_vat']:
        model.compile(optimizer=Adam(learning_rate=0.001), loss='categorical_crossentropy', metrics=['accuracy'])

        callbacks = [
            EarlyStopping(monitor='val_accuracy', patience=20, min_delta=0.001, restore_best_weights=True),
            ModelCheckpoint(f"KPIR_kerras/model_{output_column}.keras", save_best_only=True),
            ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3)
        ]

        train_dataset = tf.data.Dataset.from_tensor_slices((
            {
                "input_nazwa": X_train_nazwa,
                "input_typ": X_train_typ,
                "input_pozycja": X_train_poz,
                "input_user": X_train_uid.reshape(-1, 1)
            },
            y_train
        )).shuffle(len(X_train_nazwa), reshuffle_each_iteration=True).batch(64).cache().prefetch(tf.data.AUTOTUNE)

        val_dataset = tf.data.Dataset.from_tensor_slices((
        {
            "input_nazwa": X_test_nazwa,
            "input_typ": X_test_typ,
            "input_pozycja": X_test_poz,
            "input_user": X_test_uid.reshape(-1, 1)
        },
        y_test
    )).batch(64).cache().prefetch(tf.data.AUTOTUNE)
        
    elif output_column in ['odliczenie_vat']:
        model.compile(optimizer=Adam(learning_rate=0.001), loss='categorical_crossentropy', metrics=['accuracy'])

        callbacks = [
            EarlyStopping(monitor='val_accuracy', patience=20, min_delta=0.001, restore_best_weights=True),
            ModelCheckpoint(f"KPIR_kerras/model_{output_column}.keras", save_best_only=True),
            ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3)
        ]

        train_dataset = tf.data.Dataset.from_tensor_slices((
            {
                "input_nazwa": X_train_nazwa,
                "input_typ": X_train_typ,
                "input_pozycja": X_train_poz,
                "input_user": X_train_uid.reshape(-1, 1)
            },
            y_train
        )).shuffle(len(X_train_nazwa), reshuffle_each_iteration=True).batch(16).cache().prefetch(tf.data.AUTOTUNE)

        val_dataset = tf.data.Dataset.from_tensor_slices((
        {
            "input_nazwa": X_test_nazwa,
            "input_typ": X_test_typ,
            "input_pozycja": X_test_poz,
            "input_user": X_test_uid.reshape(-1, 1)
        },
        y_test
    )).batch(16).cache().prefetch(tf.data.AUTOTUNE)
        
##To już wespólne
    history = model.fit(
        train_dataset,
        validation_data=val_dataset,
        epochs=300,
        callbacks=callbacks,
        verbose=0
    )

    # === Ewaluacja ===
    pred = model.predict(val_dataset)
    y_pred = np.argmax(pred, axis=1)
    y_true = np.argmax(y_test, axis=1)
    print("Classification report:")
    labels_used = np.unique(y_true)
    class_names = [str(c) for c in encoder_y.categories_[0][labels_used]]
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
