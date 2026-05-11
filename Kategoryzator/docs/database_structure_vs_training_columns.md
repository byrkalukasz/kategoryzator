# Struktura bazy i porownanie do kolumn uczenia

Ten dokument opisuje aktualna strukture SQLite oraz mapowanie do kolumn wykorzystywanych w uczeniu modeli.

## 1) Struktura bazy danych

Baza tworzona jest w warstwie DB aplikacji.

Zrodlo definicji: [api/db.py](api/db.py)

### Tabela: booked_invoices

Cel: historia zaksięgowanych dokumentow i dane do podobienstwa.

Kolumny:
- id: INTEGER, PK, AUTOINCREMENT
- created_at: TEXT, UTC ISO
- company_id: TEXT
- accounting_type: TEXT, profil ksiegowy (kpir albo advance)
- typ_pozycji: TEXT
- nazwa: TEXT, oryginalna nazwa dokumentu
- nazwa_normalized: TEXT, wersja znormalizowana do wyszukiwania
- embedding_json: TEXT, embedding nazwy (wektor serializowany do JSON)
- selected_prediction_json: TEXT, finalna wybrana kategoria jako JSON

Indeksy i FTS:
- idx_booked_lookup na company_id, accounting_type, typ_pozycji
- idx_booked_created_at na created_at DESC
- booked_invoices_fts: FTS5 po nazwa_normalized
- Triggery FTS: booked_ai, booked_ad, booked_au

### Tabela: company_prediction_config

Cel: konfiguracja per firma.

Kolumny:
- id: INTEGER, PK, AUTOINCREMENT
- company_id: TEXT, UNIQUE
- confidence_exact: REAL
- confidence_ai: REAL
- llm_enabled: INTEGER (0 albo 1)

### Tabela: llm_usage_monthly

Cel: miesieczna agregacja kosztow i usage LLM per firma.

Kolumny:
- id: INTEGER, PK, AUTOINCREMENT
- company_id: TEXT
- usage_month: TEXT, format YYYY-MM
- requests_count: INTEGER
- input_tokens: INTEGER
- output_tokens: INTEGER
- total_tokens: INTEGER
- last_request_at: TEXT

Ograniczenia:
- UNIQUE(company_id, usage_month)

## 2) Kolumny danych uczenia

Zrodla:
- [dane/dane_ai.csv](dane/dane_ai.csv)
- [dane/dane_ai_ryczalt.csv](dane/dane_ai_ryczalt.csv)
- Rejestr kolumn API: [api/app.py](api/app.py)

### KPIR: dane_ai.csv

Naglowek:
- document_id
- nazwa
- typ_pozycji
- company_id
- typ
- kolumna_kpir
- metoda_rozliczenia_podatku
- metoda_rozliczenia_vat
- odliczenie_vat
- cel_zakupu
- srodek_trwaly

### ADVANCED: dane_ai_ryczalt.csv

Naglowek:
- document_id
- nazwa
- typ_pozycji
- company_id
- typ
- medota_rozliczenia_podatku
- metoda_rozliczenia_vat
- odliczenie_vat
- cel_zakupu
- srodek_trwaly

Uwaga:
- W ADVANCED wystepuje literowka medota_rozliczenia_podatku.
- W API jest alias kanoniczny do metoda_rozliczenia_podatku.

## 3) Porownanie 1:1 baza vs uczenie

### Wejscia (features)

- nazwa (uczenie) -> nazwa i nazwa_normalized oraz embedding_json (baza)
- typ_pozycji (uczenie) -> typ_pozycji (baza)
- company_id (uczenie) -> company_id (baza)
- typ (uczenie: BOOK albo ADVANCED) -> accounting_type (baza: kpir albo advance)

Komentarz:
- typ i accounting_type sa semantycznie powiazane, ale nie identyczne wartosciowo.
- W warstwie inferencji jest mapowanie: kpir -> BOOK, advance -> ADVANCED.

### Wyjscia (targety)

Przechowywane w bazie jako jeden JSON:
- selected_prediction_json

Mapowane targety:
- KPIR:
  - kolumna_kpir
  - metoda_rozliczenia_podatku
  - metoda_rozliczenia_vat
  - odliczenie_vat
  - cel_zakupu
  - srodek_trwaly
- ADVANCED:
  - metoda_rozliczenia_podatku (alias dla medota_rozliczenia_podatku)
  - metoda_rozliczenia_vat
  - odliczenie_vat
  - cel_zakupu
  - srodek_trwaly

## 4) Czego nie ma w bazie wzgledem treningu

- document_id z CSV nie jest zapisywany do historii.
- typ z CSV nie jest przechowywany 1:1, jest reprezentowany przez accounting_type.

## 5) Czego jest wiecej w bazie wzgledem treningu

- created_at
- nazwa_normalized
- embedding_json
- konfiguracja per firma (progi i llm_enabled)
- miesieczne usage LLM (requests i tokens)

## 6) Wnioski praktyczne

- Baza jest zoptymalizowana pod runtime i audyt decyzji, nie jest kopia tabel treningowych.
- Wejscia i targety potrzebne do inferencji sa pokryte.
- Dla spojnosc raportowa mozna rozważyć dodanie opcjonalnego source_document_id do historii, jesli potrzebny jest trace do dokumentu z ERP.
