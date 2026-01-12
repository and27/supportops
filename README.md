# SupportOps

SupportOps is a support/helpdesk system with a FastAPI agent runtime, a Next.js
chat UI, and Supabase Postgres for persistence.

## Repo layout
- `apps/web`: Next.js product UI (chat + admin dashboard)
- `services/agent`: FastAPI agent runtime API
- `packages/eval`: pytest-based eval suite calling the agent API
- `infra/supabase`: Supabase schema and infra assets

## Local development

### 1) Apply the Supabase schema
Run the schema against your Supabase Postgres instance:

```bash
psql "$SUPABASE_DB_URL" -f infra/supabase/schema.sql
```

For applying changes to an existing DB, run the latest migration in
`infra/supabase/migrations` (example):

```bash
psql "$SUPABASE_DB_URL" -f infra/supabase/migrations/2026-01-12_v1_vector_agent_runs.sql
```

### 2) Start the agent API

```bash
cd services/agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

$env:SUPABASE_URL="https://your-project.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"

uvicorn app.main:app --reload --port 8000
```

### 3) Start the web app

```bash
pnpm install
$env:AGENT_API_BASE_URL="http://localhost:8000"
pnpm dev:web
```

Open `http://localhost:3000` for chat, `http://localhost:3000/kb` for the KB
admin screen, and `http://localhost:3000/runs` for recent agent runs.

### 4) Run evals

```bash
cd packages/eval
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

$env:AGENT_API_BASE_URL="http://localhost:8000"
pytest

# or
python run_eval.py
```

### 5) Seed KB fixtures (optional)

```bash
cd infra/kb-fixtures
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

$env:AGENT_API_BASE_URL="http://localhost:8000"
python seed_kb.py --ingest
```

### 6) Vector evals (optional)
Semantic evals require embeddings + vector search enabled. Opt-in with:

```bash
$env:VECTOR_EVALS="true"
python run_eval.py
```
