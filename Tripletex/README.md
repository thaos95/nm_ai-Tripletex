# Tripletex Agent

Selvstendig prosjektmappe for Tripletex-konkurransen. All kode, tester og fixtures ligger her.

## Kom i gang

```powershell
cd C:\Users\amand\NMiAI\nm-ai2\Tripletex
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
pytest
uvicorn app.main:app --reload
```

Kopier eventuelt `.env.example` til `.env` hvis du vil beskytte `/solve` med API-nokkel.

## Struktur

- `app/main.py`: FastAPI-app og `/solve`
- `app/parser.py`: Regelstyrt prompt-parser
- `app/planner.py`: Mapper parsed intent til workflow
- `app/workflows/`: Deterministiske Tripletex-workflows
- `app/clients/tripletex.py`: API-klient og auth
- `tests/`: Lokale tester
- `fixtures/`: Testpayloads

## Nåværende dekning

Denne versjonen er en testbar baseline:

- `create_employee`
- `update_employee`
- `create_customer`
- `update_customer`
- `create_product`
- `create_project`
- `create_department`
- `create_order`
- `create_invoice`
- `create_travel_expense`
- `delete_travel_expense`
- `delete_voucher`

Den er laget for å være lett å utvide med flere workflows uten å flytte kode ut av denne mappa.

## Rask test med fixture

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/solve `
  -ContentType 'application/json' `
  -InFile .\fixtures\sample_request.json
```

Merk:
- `sample_request.json` er en enkel ansatt-test.
- `sample_order_request.json` er en bedre lokal smoke-test enn faktura akkurat nå.
- Sandboxen din ser ut til å mangle bankkonto-oppsett for faktisk fakturaopprettelse, så lokale invoice-feil kan komme fra sandboxoppsettet og ikke nødvendigvis fra agenten.

## Cloud Run

Fra `Tripletex/` kan du deploye til Google Cloud Run:

```bash
gcloud run deploy tripletex-agent \
  --source . \
  --region europe-north1 \
  --allow-unauthenticated
```

Test etter deploy:

```bash
curl https://YOUR_CLOUD_RUN_URL/health
```

Submit denne URL-en til konkurransen:

```text
https://YOUR_CLOUD_RUN_URL/solve
```

## Optional LLM Parser

Regel-parseren fungerer uten ekstern modell, men du kan gi agenten bredere task-forstaelse ved aa sette:

```text
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5-mini
```

Da prover agenten en strukturert OpenAI-parser forst og faller tilbake til regel-parseren hvis LLM-kallet feiler eller mangler nokkel.
