# SupportOps — Agents Towards Production (MVP)

## Objetivo

Construir un producto real llamado **SupportOps**: un sistema de soporte (helpdesk) con un **Agent Runtime** que:

1. recibe mensajes de usuarios (web),
2. consulta una base de conocimiento (KB),
3. responde con grounding (basado en KB) o hace preguntas de clarificación,
4. crea/actualiza tickets y escala a humano cuando corresponde,
5. registra trazas y métricas para poder evaluar y mejorar el sistema.

El objetivo de aprendizaje es dominar el ciclo completo de un **LLM System**:
**ingestión → retrieval → generación → evaluación → observabilidad → iteración → control de costos**.

## Alcance MVP (v0)

### Canales

- Web (UI en Next.js).
- WhatsApp/Instagram quedan fuera en v0.

### Experiencia del usuario (v0)

- Un usuario escribe un mensaje en una pantalla tipo chat.
- El sistema responde en segundos.
- La conversación se persiste.
- Si el caso es ambiguo o de baja confianza, el agent pide datos faltantes o escala.

### Base de Conocimiento (v0)

- CRUD mínimo de KB desde dashboard admin:
  - crear/editar artículos (title, content, tags).
- Retrieval inicial sin embeddings:
  - búsqueda simple (tags / texto / top N).
- Embeddings + Supabase Vector se activan en v1.

### Tickets (v0)

- Se crea un ticket cuando:
  - el agent no puede resolver con KB,
  - o confianza es baja,
  - o el usuario reporta bug/incident.
- Estados: `open`, `waiting_user`, `waiting_team`, `resolved`
- Prioridad: `low`, `normal`, `high`

## Arquitectura (monorepo)

Repositorio único: `supportops`

Estructura:

- `apps/web` — Next.js (React UI) + dashboard + chat UI
- `services/agent` — FastAPI (Python) Agent Runtime (API)
- `packages/eval` — suite de evaluación (pytest + runner)
- `packages/shared` — contratos/DTOs (schemas), opcional
- `infra/supabase` — SQL schema/migrations, seed

Principio clave:

- **Next.js = producto** (UX, dashboard, auth, llamadas a Agent API)
- **FastAPI = cerebro** (decisiones del agent, retrieval, llamadas LLM, logging)
- **Supabase = fuente de verdad** (conversaciones, tickets, KB y luego embeddings)

## Contratos (API Agent)

### POST /v1/chat

Input (JSON):

- `conversation_id?: string` (si no viene, se crea)
- `user_id?: string` (opcional)
- `channel: "web"`
- `message: string`
- `metadata?: object` (device, locale, etc.)

Output (JSON):

- `conversation_id: string`
- `reply: string`
- `action: "reply" | "ask_clarifying" | "create_ticket" | "escalate"`
- `confidence: number` (0..1)
- `ticket_id?: string`
- `missing_fields?: string[]`
- `citations?: { kb_document_id: string, kb_chunk_id?: string }[]`

### POST /v1/ingest (v1)

- Cargar artículos/archivos y trocear en chunks + embeddings (más adelante).

### GET /health

- Healthcheck.

## Persistencia (Supabase Postgres)

Tablas mínimas (v0):

- `conversations`
- `messages` (role: user/assistant/system)
- `tickets`
- `kb_documents`
- `kb_chunks` (para RAG; embeddings en v1)
  Opcional:
- `agent_runs` (trazas: decisión, docs usados, costos, timing)

## Reglas de decisión del Agent (v0)

1. Siempre persistir el mensaje del usuario.
2. Intentar resolver con KB:
   - recuperar candidatos (simple retrieval)
   - si hay evidencia clara, responder citando KB.
3. Si es ambiguo, pedir datos faltantes (action: ask_clarifying).
4. Si no hay respuesta confiable, crear ticket o escalar.
5. Nunca inventar políticas, precios o hechos no presentes en KB.
6. Mantener respuestas concisas, orientadas a solución.

## Evaluación (packages/eval)

Objetivo: desde el día 1, evitar regressions.

- Mantener un set de casos `eval/cases/*.jsonl`:
  - entrada (mensaje + contexto)
  - expectativa (action esperada, debe pedir X datos, etc.)
- Runner:
  - llama a `/v1/chat`
  - valida formato + reglas + expectativas
- Criterios iniciales:
  - response JSON válido
  - action ∈ set permitido
  - no “alucinaciones” obvias (p.ej. afirmar que consultó sistemas externos cuando no existe tool)

## Fases

### v0 (ahora)

- Web chat UI + dashboard KB mínimo
- Agent /v1/chat con persistencia y respuesta dummy + retrieval simple
- DB schema creado
- Eval suite con 10 casos

### v1

- Chunking formal
- Embeddings + Supabase Vector
- Grounding estricto con citations
- Agent_runs/tracing
- Métricas básicas

### v2

- Integraciones (WhatsApp, etc.)
- Multi-tenant
- Roles (admin/agent)
- Mejor evaluación + observabilidad
