# -*- coding: utf-8 -*-
"""Dane treściowe raportu – oddzielone od logiki generowania."""

TITLE       = "KATEGORYZATOR"
SUBTITLE    = "System Automatycznej Kategoryzacji Dokumentów Księgowych"
REPORT_HEADING = "Raport Końcowy Projektu"

INFO_META = [
    ("Projekt:",    "Kategoryzator – ML-powered kategoryzacja faktur"),
    ("Wersja:",     "2.0.0"),
    ("Data:",       "Maj 2026"),
    ("Technologie:","Python · TensorFlow/Keras · XGBoost · FastAPI · AWS Bedrock · Docker"),
    ("Profile:",    "KPIR (Księga Przychodów i Rozchodów) + ADVANCED (Ryczałt)"),
]

TOC_ITEMS = [
    "1. Streszczenie wykonawcze",
    "2. Cel i kontekst biznesowy projektu",
    "3. Architektura systemu",
    "4. Dane treningowe",
    "5. Metodologia i Feature Engineering",
    "6. Modele uczenia maszynowego",
    "   6.1 Keras – sieci neuronowe",
    "   6.2 XGBoost – gradient boosting",
    "   6.3 Hyperparameter Tuning",
    "7. Wyniki i metryki modeli",
    "   7.1 Wyniki XGBoost (KPIR)",
    "   7.2 Wyniki Keras (KPIR)",
    "   7.3 Wyniki ADVANCED (Ryczałt)",
    "8. Wykresy z trenowania",
    "9. Architektura API",
    "   9.1 Endpointy REST",
    "   9.2 Flow decyzyjny",
    "   9.3 Fallback LLM (AWS Bedrock)",
    "   9.4 Historia księgowań (SQLite)",
    "10. Infrastruktura i wdrożenie",
    "11. Testy integracyjne",
    "12. Przypadki testowe (do uzupełnienia)",
    "13. Wnioski końcowe",
    "14. Rekomendacje i dalszy rozwój",
]

SEC_EXEC_SUMMARY = [
    (
        "Kategoryzator to system automatycznej klasyfikacji dokumentów księgowych, "
        "zbudowany na potrzeby platformy Symfonia. System wykorzystuje techniki uczenia "
        "maszynowego (sieci neuronowe Keras oraz gradient boosting XGBoost) do przypisywania "
        "faktur kosztowych i przychodowych do właściwych kategorii podatkowych. "
        "Zadaniem systemu jest wspomaganie i automatyzacja pracy księgowego poprzez "
        "propozycje kategoryzacji dla każdego nowego dokumentu."
    ),
    (
        "Projekt dostarcza kompletne rozwiązanie produkcyjne obejmujące: trening i ewaluację "
        "modeli ML, REST API (FastAPI) z logiką wielostopniowej decyzji, integrację z "
        "historią księgowań (SQLite + FTS5), mechanizm fallback do dużych modeli językowych "
        "(LLM) przez AWS Bedrock, konteneryzację Docker oraz konsumenta kolejki SQS."
    ),
]

EXEC_BULLETS = [
    ("Accuracy XGBoost:",   "od 79.7% (metoda_rozliczenia_vat) do 99.8% (srodek_trwaly)"),
    ("Accuracy Keras:",     "od ~80% (metoda_rozliczenia_podatku) do ~99.8% (srodek_trwaly)"),
    ("Ensemble:",           "Podwójne potwierdzenie (XGBoost + Keras); rozbieżność kieruje do weryfikacji"),
    ("LLM Fallback:",       "AWS Bedrock przy niskiej pewności historycznej i gdy firma włączyła LLM"),
    ("Wdrożenie:",          "Docker, AWS EC2/ECS, opcjonalnie SQS consumer"),
]

SEC_BUSINESS = (
    "Każda firma prowadząca działalność gospodarczą w Polsce jest zobowiązana do "
    "prawidłowego klasyfikowania dokumentów księgowych – faktur zakupu i sprzedaży – "
    "zgodnie z właściwym reżimem podatkowym. W praktyce oznacza to konieczność "
    "przypisania do każdego dokumentu kilku atrybutów jednocześnie:"
)

ATTRS = [
    "kolumna_kpir – przynależność do właściwej kolumny Księgi Przychodów i Rozchodów",
    "metoda_rozliczenia_podatku – sposób odliczenia kosztu (STD100, STD75, STD20, STD0 ...)",
    "metoda_rozliczenia_vat – metoda rozliczenia podatku VAT (VAT100, VAT50, VAT50NETTO ...)",
    "odliczenie_vat – szczegółowe odliczenie VAT zgodnie z art. ustawy o VAT",
    "cel_zakupu – cel dla jakiego zakup jest dokonany (TAXED_SALE, EXEMPT_SALE ...)",
    "srodek_trwaly – czy dokument dotyczy środka trwałego (PRAWDA / FALSE)",
]

SEC_BUSINESS_2 = (
    "Ręczna klasyfikacja jest czasochłonna, podatna na błędy i wymaga wiedzy "
    "specjalistycznej. Kategoryzator rozwiązuje ten problem poprzez automatyczne "
    "przewidywanie kategorii na podstawie: nazwy dokumentu, typu pozycji "
    "(EXPENDITURE / INCOME) oraz identyfikatora firmy – personalizacja per klient. "
    "Biznesowe korzyści to skrócenie czasu księgowania, redukcja błędów klasyfikacji, "
    "pełna audytowalność decyzji AI oraz możliwość doskonalenia systemu przez "
    "mechanizm feedbacku (endpoint /bookkeeping/confirm)."
)

ARCH_ITEMS = [
    ("Warstwa danych treningowych",
     "Pliki CSV (dane_ai.csv – KPIR, dane_ai_ryczalt.csv – ADVANCED) zawierające "
     "historyczne dokumenty z poprawnymi kategoriami."),
    ("Warstwa ML (trening)",
     "Skrypty Python w katalogu training/ realizujące pełny pipeline: czyszczenie danych, "
     "feature engineering, trening modeli Keras i XGBoost, zapis modeli i enkoderów."),
    ("Warstwa predykcji (inference)",
     "Moduły api/services/ ładujące wytrenowane artefakty i realizujące predykcję online."),
    ("Warstwa API",
     "FastAPI (api/app.py) – REST API z endpointami do predykcji, zarządzania historią, "
     "konfiguracji per firma i raportowania LLM."),
    ("Warstwa historii",
     "SQLite z FTS5 – przechowuje potwierdzone przez księgowego kategoryzacje; "
     "używana do exact-match lookup przed uruchomieniem modeli ML."),
    ("Warstwa LLM (fallback)",
     "AWS Bedrock (Converse API) – wywołany gdy pewność historyczna jest zbyt niska "
     "i firma wyraziła zgodę na użycie LLM."),
    ("Infrastruktura",
     "Docker + AWS EC2/ECS; opcjonalny SQS consumer do asynchronicznego przetwarzania."),
]

FLOW_STEPS = [
    ("Krok 1", "API przyjmuje request: nazwa, typ_pozycji, company_id, accounting_type", "—"),
    ("Krok 2", "Pobrana jest konfiguracja firmy (progi pewności, flaga llm_enabled)", "—"),
    ("Krok 3", "Szukanie podobnej faktury w historii SQLite (FTS5 + cosine similarity)", "—"),
    ("Krok 4", "similarity ≥ confidence_exact → zwrot historycznego wyniku", "historical_match"),
    ("Krok 5", "Brak dopasowania → uruchomienie XGBoost i Keras równolegle", "—"),
    ("Krok 6", "Modele zgodne → zwrot predykcji", "model_consensus"),
    ("Krok 7", "Modele rozbieżne → obie podpowiedzi do wyboru", "manual_review_required"),
    ("Krok 8", "similarity < confidence_ai → opcjonalny LLM fallback", "ai_assist_required"),
    ("Krok 9", "Księgowy potwierdza → zapis do historii SQLite", "saved"),
]

KPIR_COLS = [
    ("document_id",               "Unikalny identyfikator dokumentu"),
    ("nazwa",                     "Oryginalna nazwa dokumentu/faktury – główna cecha wejściowa"),
    ("typ_pozycji",               "Typ dokumentu: EXPENDITURE (koszt) lub INCOME (przychód)"),
    ("company_id",                "Identyfikator firmy – personalizacja modelu"),
    ("typ",                       "Typ transakcji; filtr: BOOK (tylko rzeczywiste księgowania)"),
    ("kolumna_kpir",              "Cel 1: kolumna KPiR (OTHER_EXPENSES, PURCHASE_OF_TRADING_GOODS, …)"),
    ("metoda_rozliczenia_podatku","Cel 2: metoda podatkowa (STD100, STD75, STD20, STD0, …)"),
    ("metoda_rozliczenia_vat",    "Cel 3: metoda VAT (VAT100, VAT50, VAT50NETTO, VAT0, …)"),
    ("odliczenie_vat",            "Cel 4: szczegółowe odliczenie VAT (DEDUCTION_VAT_S_*)"),
    ("cel_zakupu",                "Cel 5: cel zakupu (TAXED_SALE, EXEMPT_SALE, TAXED_AND_EXEMPT_SALE)"),
    ("srodek_trwaly",             "Cel 6: środek trwały (PRAWDA / FALSE)"),
]

SEC_DATA_2 = (
    "Dane dla reżimu ryczałtowego zawierają te same cechy wejściowe, lecz bez kolumny "
    "kolumna_kpir (nieaplikowalne dla ryczałtu). Uwaga: w danych występuje literówka "
    "medota_rozliczenia_podatku (zamiast metoda_...) – obsługiwana przez alias w kodzie."
)

SEC_DATA_SPLIT = (
    "Dane dzielone są w stosunku 70%/30% (train/test) ze stałym ziarnem losowości "
    "(random_state=42) w celu zapewnienia reprodukowalności wyników. "
    "Feature engineering (TF-IDF, OneHotEncoder) fitowany jest wyłącznie na zbiorze "
    "treningowym, co eliminuje wyciek danych (data leakage)."
)

FE_ITEMS = [
    ("TF-IDF (nazwa dokumentu)",
     "Wektoryzacja tekstu nazwy faktury przy użyciu TF-IDF z max_features=3000. "
     "Oddaje semantykę opisu transakcji – kluczowy sygnał dla klasyfikatora. "
     "Zapisywany jako vectorizer_nazwa_nn.pkl (Keras) i vectorizer_nazwa.pkl (XGBoost)."),
    ("OneHotEncoder (typ transakcji)",
     "Binarny wektor dla kolumny typ (BOOK/ADVANCED) – informacja o reżimie ewidencji."),
    ("OneHotEncoder (typ_pozycji)",
     "Binarny wektor dla EXPENDITURE/INCOME – kluczowy sygnał dla kolumny KPiR."),
    ("User Embedding / LabelEncoder (company_id)",
     "Keras: Embedding(dim=32) mapuje identyfikator firmy na gęsty wektor – "
     "model uczy się preferencji per klient. "
     "XGBoost: LabelEncoder przekształca company_id na liczbę całkowitą."),
]

SEC_FE_EXTRA = (
    "Obsługa niezbalansowanych klas: XGBoost używa compute_class_weight('balanced') "
    "z dodatkowym mnożnikiem 1.5× dla klas rzadkich. Keras stosuje EarlyStopping "
    "z monitorowaniem val_accuracy (patience=20–60) i ReduceLROnPlateau."
)

SEC_ENSEMBLE = (
    "Projekt stosuje strategię ensemble: każda predykcja wykonywana jest przez "
    "dwa niezależne modele (XGBoost i Keras). Zgodność obu daje wysoką pewność; "
    "rozbieżność sygnalizuje konieczność weryfikacji przez człowieka lub LLM."
)

KERAS_ARCH = [
    ("Input nazwy",       "Dense, TF-IDF (3000 cech)"),
    ("Input typ",         "OneHot encoded"),
    ("Input pozycja",     "OneHot encoded"),
    ("Input user",        "Embedding(num_users, dim=32) → Flatten"),
    ("Concat",            "Concatenate wszystkich wejść"),
    ("Hidden layers",     "2 warstwy Dense (64–256 neuronów) z Dropout (0.1–0.5), aktywacja SELU / ReLU"),
    ("Output",            "Dense(n_klas, activation='softmax')"),
    ("Optymalizator",     "Adam (lr=0.001–0.003)"),
    ("Loss",              "categorical_crossentropy"),
    ("Callbacks",         "EarlyStopping + ModelCheckpoint + ReduceLROnPlateau"),
]

XGB_PARAMS = [
    ("max_depth",        "6"),
    ("learning_rate",    "0.1"),
    ("n_estimators",     "300"),
    ("subsample",        "0.8"),
    ("colsample_bytree", "0.8"),
    ("reg_alpha (L1)",   "1.0"),
    ("reg_lambda (L2)",  "1.0"),
    ("objective",        "multi:softprob / binary:logistic"),
    ("sample_weight",    "balanced + boost ×1.5"),
]

TUNING_DATA = [
    ("macro_f1",              "0.913"),
    ("val_accuracy",          "98.16%"),
    ("units_1 / units_2",     "64 / 128"),
    ("dropout_1 / dropout_2", "0.4 / 0.2"),
    ("embedding_dim",         "16"),
    ("learning_rate",         "0.003"),
    ("batch_size",            "16"),
    ("activation",            "SELU"),
    ("batch_norm",            "False"),
]

XGB_RESULTS = [
    ("kolumna_kpir",               "Kolumna KPiR",               "85.24%", "0.863", "0.686", "0.877"),
    ("metoda_rozliczenia_podatku", "Metoda rozliczenia podatku", "79.87%", "0.835", "0.417", "0.911"),
    ("metoda_rozliczenia_vat",     "Metoda rozliczenia VAT",     "79.71%", "0.838", "0.437", "0.921"),
    ("odliczenie_vat",             "Odliczenie VAT",             "95.82%", "0.972", "0.255", "0.988"),
    ("cel_zakupu",                 "Cel zakupu",                 "93.48%", "0.941", "0.677", "0.954"),
    ("srodek_trwaly",              "Srodek trwaly",              "99.82%", "0.998", "0.738", "0.999"),
]

KERAS_RESULTS = [
    ("kolumna_kpir",               "Kolumna KPiR",               "~91%",   "Dobra konwergencja, val_accuracy stabilna"),
    ("metoda_rozliczenia_podatku", "Metoda rozliczenia podatku", "~80%",   "Klasy STD75 i STD20 wymagaja wiecej danych"),
    ("metoda_rozliczenia_vat",     "Metoda rozliczenia VAT",     "~80%",   "VAT100 dominuje, pozostale klasy rzadkie"),
    ("odliczenie_vat",             "Odliczenie VAT",             "~96%",   "BRAK dominuje; klasy minutarne trudne"),
    ("cel_zakupu",                 "Cel zakupu",                 "~93%",   "BRAK dominuje, TAXED_SALE rozpoznawany"),
    ("srodek_trwaly",              "Srodek trwaly",              "~99.8%", "Klasa PRAWDA rzadka; bardzo imbalanced"),
]

PLOT_FILES = {
    "kolumna_kpir":                ("Kolumna KPiR",
                                    "accuracy_kolumna_kpir.png", "loss_kolumna_kpir.png"),
    "metoda_rozliczenia_podatku":   ("Metoda rozliczenia podatku",
                                    "accuracy_metoda_rozliczenia_podatku.png",
                                    "loss_metoda_rozliczenia_podatku.png"),
    "metoda_rozliczenia_vat":       ("Metoda rozliczenia VAT",
                                    "accuracy_metoda_rozliczenia_vat.png",
                                    "loss_metoda_rozliczenia_vat.png"),
    "odliczenie_vat":               ("Odliczenie VAT",
                                    "accuracy_odliczenie_vat.png", "loss_odliczenie_vat.png"),
    "cel_zakupu":                   ("Cel zakupu",
                                    "accuracy_cel_zakupu.png", "loss_cel_zakupu.png"),
    "srodek_trwaly":                ("Srodek trwaly",
                                    "accuracy_srodek_trwaly.png", "loss_srodek_trwaly.png"),
}

ENDPOINTS = [
    ("POST",   "/predict",                        "Predykcja kategorii; logika full-flow"),
    ("POST",   "/predict_log",                    "Predykcja z zapisem logu do pliku JSON"),
    ("POST",   "/bookkeeping/confirm",            "Zapis potwierdzonej kategoryzacji do historii"),
    ("GET",    "/bookkeeping/history",            "Przegladanie historii (paginacja)"),
    ("DELETE", "/bookkeeping/history/{id}",       "Usuniecie wpisu z historii"),
    ("PUT",    "/bookkeeping/company-config",     "Ustawienie progow i flagi LLM per firma"),
    ("GET",    "/bookkeeping/company-config/{id}","Pobranie konfiguracji firmy"),
    ("GET",    "/bookkeeping/llm-usage/{id}",     "Uzycie LLM per firma (tokeny, koszty)"),
    ("GET",    "/bookkeeping/llm-usage-report",   "Raport zbiorczy uzycia LLM"),
    ("GET",    "/bookkeeping/llm-usage-clients",  "Lista firm z uzyciem LLM"),
    ("GET",    "/health",                         "Healthcheck (status: ok)"),
]

PREDICT_FIELDS = [
    ("nazwa",          "str",              "Nazwa dokumentu/faktury – glowna cecha modelu"),
    ("typ_pozycji",    "str",              "EXPENDITURE lub INCOME"),
    ("company_id",     "str|int|float",   "Identyfikator firmy (personalizacja)"),
    ("accounting_type","str",              "kpir lub advance"),
]

INFRA_ITEMS = [
    ("Docker",      "scripts/run_docker.sh: build + run :8000 + health check /health"),
    ("AWS EC2/ECS", "Produkcja: .env.aws.example, uvicorn 0.0.0.0:8000"),
    ("SQS Consumer","scripts/run_sqs_consumer.sh – cron lub ciagly"),
    ("ENV (klucz)", "BOOKED_DB_PATH, DEFAULT_CONFIDENCE_*, LLM_BEDROCK_MODEL_ID, SQS_QUEUE_URL"),
]

TEST_FILES = [
    ("test_api_integration.py",
     "Smoke-testy API: /health, walidacja wejsc, predict dla nowej firmy, confirm + historical_match"),
    ("test_db_llm_usage.py",
     "Testy warstwy DB: rejestracja uzycia LLM, agregacja monthly, raporty, upsert konfiguracji"),
    ("test_llm_client.py",
     "Testy klienta LLM: is_enabled() z roznymi zmiennymi env, request_bedrock gdy disabled"),
    ("test_llm_contracts.py",
     "Kontrakty LLM: struktura payload escalation, build_final_prediction consensus/rozbiez."),
    ("test_similarity_performance.py",
     "Testy wydajnosciowe wyszukiwania podobienstwa: czas odpowiedzi, poprawnosc dopasowania"),
    ("test_sqs_consumer.py",
     "Testy consumera SQS: przetwarzanie wiadomosci, obsluga bledow"),
]

MOCK_CASES = [
    ("TC-001", "Faktura telefoniczna – znany klient, wysoka similarity",
     "Abonament tel. Orange 05/2026",      "historical_match",               "[DO UZUP.]", "[DO UZUP.]", "[DO UZUP.]", ""),
    ("TC-002", "Zakup paliwa – klient KPIR",
     "Faktura paliwo BP 04/2026",           "model_consensus",                "[DO UZUP.]", "[DO UZUP.]", "[DO UZUP.]", ""),
    ("TC-003", "Wynagrodzenie pracownika",
     "Lista plac kwiecien 2026",            "model_consensus (SALARIES)",     "[DO UZUP.]", "[DO UZUP.]", "[DO UZUP.]", ""),
    ("TC-004", "Zakup srodka trwalego – laptop",
     "Dell XPS 15 – laptop sluzbowy",       "srodek_trwaly: PRAWDA",          "[DO UZUP.]", "[DO UZUP.]", "[DO UZUP.]", ""),
    ("TC-005", "Nowy klient – brak historii",
     "Pierwsza faktura TEST_CO_001",        "model_consensus / manual_review", "[DO UZUP.]", "[DO UZUP.]", "[DO UZUP.]", ""),
    ("TC-006", "Rozbiez. modeli – przypadek graniczny",
     "Faktura mieszana (towar+usluga)",     "manual_review_required",         "[DO UZUP.]", "[DO UZUP.]", "[DO UZUP.]", ""),
    ("TC-007", "LLM fallback enabled",
     "Niezident. usluga zagraniczna",       "llm_fallback_used",              "[DO UZUP.]", "[DO UZUP.]", "[DO UZUP.]", "LLM_FALLBACK=1"),
    ("TC-008", "Confirm + ponowna predykcja",
     "Zaksiegowana faktura ponownie",       "historical_match po confirm",    "[DO UZUP.]", "[DO UZUP.]", "[DO UZUP.]", ""),
    ("TC-009", "Profil ADVANCED (ryczalt)",
     "Abonament hosting AWS 05/2026",       "model_consensus (ADVANCED)",     "[DO UZUP.]", "[DO UZUP.]", "[DO UZUP.]", "advance"),
    ("TC-010", "Walidacja – pusta nazwa",
     "(puste)",                             "HTTP 400",                       "[DO UZUP.]", "[DO UZUP.]", "[DO UZUP.]", ""),
]

TC_HEADERS = ["ID", "Scenariusz", "Wejscie (nazwa)", "Oczekiwana decyzja",
              "Faktyczna decyzja", "Wynik predykcji", "Status", "Uwagi"]

CONCLUSIONS = [
    ("Skutecznosc modeli ML",
     "Modele osiagaja wysoka dokladnosc dla klas dominujacych (srodek_trwaly ~99.8%, "
     "cel_zakupu ~93.5%, kolumna_kpir ~85-91%). Klasy rzadkie wymagaja dalszego zbierania "
     "danych lub technik oversampling (SMOTE), co jest naturalnym ograniczeniem "
     "przy imbalanced datasets."),
    ("Strategia ensemble",
     "Polaczenie XGBoost i Keras w architekturze dual-model podwyzszawa niezawodnosc "
     "predykcji. Konsensus modeli jest silnym sygnalem jakosci decyzji; "
     "rozbiez. automatycznie eskaluje do czlowieka lub LLM."),
    ("Personalizacja per firma",
     "Mechanizm User Embedding (Keras) i LabelEncoder (XGBoost) w polaczeniu "
     "z historia SQLite per firma tworzy efektywny system personalizacji. "
     "Im dluzej firma korzysta z systemu, tym wiecej dopasovan pochodzi z historii "
     "(historical_match), redukujac obciazenie modeli ML."),
    ("Skalowalnosc architektury",
     "Architektura REST API + Docker + SQS umozliwia skalowanie synchroniczne (HTTP) "
     "jak i asynchroniczne (kolejka). Separacja treningu od serwowania pozwala "
     "na niezalezne aktualizacje modeli bez przerw w dzialaniu API."),
    ("LLM jako siatka bezpieczenstwa",
     "AWS Bedrock stanowi ostatnia linie obrony dla przypadkow granicznych. "
     "System rejestruje tokeny i koszty per firma, co umozliwia kontrole kosztow "
     "i selektywne wlaczanie LLM dla wybranych klientow."),
    ("Gotowosc produkcyjna",
     "Docker, FastAPI, testy integracyjne, healthcheck, runbooki AWS – projekt "
     "spelnia wymagania produkcyjne klasy enterprise."),
]

RECOMMENDATIONS = [
    "Rozbudowa zbioru danych dla klas rzadkich – SMOTE / aktywne uczenie",
    "Embeddingi semantyczne (BERT / sentence-transformers) zamiast TF-IDF",
    "Automatyczny feedback loop – re-trening po potwierdzeniach /bookkeeping/confirm",
    "Monitoring driftu danych (Evidently AI) + alerty na degradacje accuracy",
    "Multi-tenant fine-tuning – oddzielne modele dla duzych firm",
    "Rozszerzenie profili: pelna ksiegowosc (KH), inne rezimy podatkowe",
]

FINAL_NOTE = (
    "Projekt Kategoryzator stanowi dojrzale, produkcyjne rozwiazanie klasy enterprise "
    "dla automatyzacji procesow ksiegowych w ekosystemie Symfonia."
)

ADVANCED_SUMMARY = [
    ("metoda_rozliczenia_podatku", "Analogiczna do KPIR; alias medota -> metoda"),
    ("metoda_rozliczenia_vat",     "VAT100 dominuje; VAT50/VAT50NETTO wymagaja dowazania"),
    ("odliczenie_vat",             "Silnie imbalanced – BRAK ~99%; klasy DEDUCTION_VAT_S_* rzadkie"),
    ("cel_zakupu",                 "BRAK dominuje; tuning poprawil macro F1 do 0.913"),
    ("srodek_trwaly",              "PRAWDA ekstremalna rzadkosc; accuracy ~99.8%"),
]
