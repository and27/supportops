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
