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
$env:AUTH_ENABLED="false"
$env:SUPABASE_JWT_SECRET="your-legacy-jwt-secret-if-using-hs256"
$env:SUPABASE_JWKS_URL="https://your-project.supabase.co/auth/v1/.well-known/jwks.json"

uvicorn app.main:app --reload --port 8000
```

### 3) Start the web app

```bash
pnpm install
$env:AGENT_API_BASE_URL="http://localhost:8000"
$env:SUPABASE_URL="https://your-project.supabase.co"
$env:SUPABASE_ANON_KEY="your-anon-key"
pnpm dev:web
```

Open `http://localhost:3000` for chat, `http://localhost:3000/kb` for the KB
admin screen, and `http://localhost:3000/runs` for recent agent runs.
Use `http://localhost:3000/login` to sign in when auth is enabled.

### 3a) Auth (optional)

- Create a user in Supabase Auth (email + password).
- Set `AUTH_ENABLED=true` in `services/agent`.
- For modern Supabase projects (ECC/RS256), set `SUPABASE_JWKS_URL`.
- Only set `SUPABASE_JWT_SECRET` if you are on legacy HS256.
- Set `SUPABASE_URL` + `SUPABASE_ANON_KEY` for the web app.

### 3b) Observability smoke checks

1) Send a chat message from `http://localhost:3000`.
2) Open `http://localhost:3000/runs` and verify the summary cards populate.
3) In agent logs, confirm `chat_response` includes `latency_ms` and `retrieval_source`.

### 3c) Decision guardrail behavior

- The agent only returns `action=reply` when citations are present.
- If no evidence is found, the agent asks for more context (`ask_clarifying`).
- For vector search, replies are blocked when `top_similarity` is below `REPLY_MIN_SIMILARITY`.
- Recent conversation context is appended (last N messages) to help follow-up questions.

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

When running evals, the agent logs `eval_action_result` to track action accuracy by category.
`packages/eval/thresholds.json` defines per-category thresholds (action accuracy,
and optional citation/hand-off rates). `run_eval.py` prints a category summary
and fails if any threshold is missed.
CI runs `python packages/eval/run_eval.py` and requires `AGENT_API_BASE_URL` as a
repo secret pointing at a reachable agent environment.
The eval runner creates/uses an org with slug `eval` (configurable via
`EVAL_ORG_SLUG`) and seeds KB data into that org to avoid cross-contamination.

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
