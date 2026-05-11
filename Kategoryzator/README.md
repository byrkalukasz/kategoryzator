# Kategoryzator

Porzadkowana wersja projektu z API na FastAPI oraz spojnym runbookiem kontenera.

## Struktura katalogow

- `api/app.py` - glowna aplikacja API (FastAPI)
- `categoryzer_api.py` - kompatybilny wrapper uruchomieniowy
- `training/` - skrypty treningowe (KPIR/ADVANCED, Keras/XGBoost, tuning)
- `scripts/run_docker.sh` - build + start kontenera + walidacja `/health`
- `appStart` - kompatybilny wrapper do `scripts/run_docker.sh`
- `Dockerfile` - obraz produkcyjny aplikacji
- `req.txt` - zaleznosci Pythona
- `dane/` - dane treningowe
- `KPIR_kerras/`, `ADVANCED_kerras/` - modele Keras
- `KPIR_xgboost/`, `ADVANCED_xgboost/` - modele i encodery XGBoost
- `logs/` - logi predykcji
- `plots/`, `raporty_xgb/` - artefakty treningowe
- `tests/` - testy integracyjne API

## Dokumentacja bazy vs uczenie

- Szczegolowe porownanie: [docs/database_structure_vs_training_columns.md](docs/database_structure_vs_training_columns.md)

## Flow decyzji (DB + modele)

1. API najpierw szuka podobnej, wczesniej zaksięgowanej faktury w bazie SQLite.
2. Jesli znajdzie podobna fakture, zwraca historyczny wynik.
3. Jesli nie znajdzie, uruchamia Keras i XGBoost.
4. Gdy modele sa zgodne, zwraca wspolny wynik.
5. Gdy modele sa rozbiezne, zwraca obie podpowiedzi do wyboru przez ksiegowego.

### Endpoint potwierdzenia księgowania

- `POST /bookkeeping/confirm` zapisuje recznie wybrany wynik do bazy historii.

Przyklad payload:

```json
{
  "nazwa": "Abonament telefoniczny Orange 05/2026",
  "typ_pozycji": "EXPENDITURE",
  "company_id": "123",
  "accounting_type": "kpir",
  "selected_prediction": {
    "kolumna_kpir": "OTHER_EXPENSES",
    "metoda_rozliczenia_podatku": "STD100"
  }
}
```

## Uruchomienie lokalne (Docker)

```bash
./scripts/run_docker.sh
```

Skrypt:
1. Buduje obraz.
2. Uruchamia kontener na porcie `8000`.
3. Sprawdza endpoint `http://localhost:8000/health`.

## Uruchomienie API bez Dockera

```bash
/home/servicedesk/Documents/api-ai/Kategoryzator/.kategoryzator/bin/python categoryzer_api.py
```

## Konfiguracja .env

W repo jest gotowy plik [\.env](.env) oraz szablon produkcyjny [\.env.aws.example](.env.aws.example).

Najwazniejsze zmienne:

- `BOOKED_DB_PATH` - sciezka do SQLite historii
- `DEFAULT_CONFIDENCE_EXACT` - domyslny prog exact match per firma
- `DEFAULT_CONFIDENCE_AI` - prog, ponizej ktorego API zwraca `ai_assist_required`
- `DEFAULT_COMPANY_LLM_ENABLED` - domyslna zgoda firmy na uzycie LLM (0/1)
- `AWS_REGION`, `SQS_QUEUE_URL` - konfiguracja SQS consumera
- `LLM_FALLBACK_ENABLED`, `LLM_BEDROCK_MODEL_ID` - automatyczny fallback do AWS Bedrock

## AWS (EC2/ECS) - szybki runbook

1. Wypelnij `.env` (lub podmien na wartosci z `.env.aws.example`).
2. API uruchom kontenerem:

```bash
ENV_FILE=.env ./scripts/run_docker.sh
```

3. Consumer SQS uruchom jako osobny proces:

```bash
./scripts/run_sqs_consumer.sh
```

Tryb cron (co godzine):

```bash
0 * * * * /sciezka/do/projektu/scripts/run_sqs_consumer.sh --once >> /var/log/kategoryzator-sqs.log 2>&1
```

W AWS preferuj role IAM (ECS Task Role / EC2 Instance Profile) zamiast wpisywania kluczy `AWS_ACCESS_KEY_ID` i `AWS_SECRET_ACCESS_KEY`.

## Fallback do LLM (AWS Bedrock)

Gdy podobienstwo historii spadnie ponizej `confidence_ai`, API moze automatycznie wykonac request do LLM w Bedrock.

Wymagane ustawienia w `.env`:

- `LLM_FALLBACK_ENABLED=1`
- `LLM_BEDROCK_MODEL_ID=<model-id>`
- opcjonalnie: `LLM_AWS_REGION`, `LLM_MAX_TOKENS`, `LLM_TEMPERATURE`, `LLM_TIMEOUT_SECONDS`

Przy wlaczonym fallbacku odpowiedz API zawiera:

- `decision=llm_fallback_used`
- `llm_result` - surowa odpowiedz tekstowa modelu
- `escalation` - payload wejściowy przekazany do modelu

LLM jest uruchamiany tylko gdy:

- globalnie: `LLM_FALLBACK_ENABLED=1`
- per firma: `llm_enabled=true` w `PUT /bookkeeping/company-config`

## Zuzycie LLM per miesiac

Aplikacja zapisuje miesieczne agregaty per firma:

- liczba zapytan (`requests_count`)
- input/output/total tokens

Endpoint:

- `GET /bookkeeping/llm-usage/{company_id}?usage_month=YYYY-MM`
- `GET /bookkeeping/llm-usage-report?usage_month=YYYY-MM` (raport zbiorczy)
- `GET /bookkeeping/llm-usage-clients?usage_month=YYYY-MM&limit=50&offset=0` (lista klientow)

## Testy integracyjne API

```bash
/home/servicedesk/Documents/api-ai/Kategoryzator/.kategoryzator/bin/python -m unittest tests/test_api_integration.py -v
```

## Uwaga o Dockerze

Jesli pojawia sie blad dostepu do `/var/run/docker.sock`, uruchom Docker z uprawnieniami do demona (lub dodaj uzytkownika do grupy `docker`).
