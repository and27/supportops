# KB Fixtures

Seed a small, consistent knowledge base for local testing.

## Setup
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Seed articles
```bash
$env:AGENT_API_BASE_URL="http://localhost:8000"
python seed_kb.py
```

## Seed + ingest
```bash
$env:AGENT_API_BASE_URL="http://localhost:8000"
python seed_kb.py --ingest
```
