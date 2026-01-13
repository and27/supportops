import { cookies } from "next/headers";


type AgentRun = {
  id: string;
  conversation_id: string | null;
  action: string;
  confidence: number | null;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  citations: Record<string, unknown>[] | null;
  latency_ms: number | null;
  metadata: Record<string, unknown> | null;
  created_at: string | null;
};

const baseUrl = process.env.AGENT_API_BASE_URL ?? "http://localhost:8000";

const buildUrl = (path: string) => {
  const normalized = baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
  return `${normalized}${path}`;
};

async function loadRun(
  runId: string,
  orgId: string | undefined,
  token: string | undefined
): Promise<AgentRun | null> {
  try {
    const headers: Record<string, string> = {};
    if (orgId) {
      headers["X-Org-Id"] = orgId;
    }
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const response = await fetch(buildUrl(`/v1/runs/${runId}`), {
      cache: "no-store",
      headers,
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as AgentRun;
  } catch (error) {
    return null;
  }
}

const formatJson = (value: unknown) =>
  value ? JSON.stringify(value, null, 2) : "null";

export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  const cookieStore = await cookies();
  const orgId = cookieStore.get("org_id")?.value;
  const token = cookieStore.get("sb_access_token")?.value;
  const run = await loadRun(runId, orgId, token);

  if (!run) {
    return (
      <div className="mx-auto flex min-h-screen max-w-2xl items-center justify-center px-6">
        <div className="panel rounded-3xl p-8 text-center">
          <p className="text-sm uppercase tracking-[0.25em] text-ink/50">
            Run not found
          </p>
          <h1 className="mt-4 text-2xl font-semibold">We could not load it.</h1>
          <p className="mt-2 text-sm text-ink/60">
            Check the run id or return to the runs list.
          </p>
          <a
            href="/runs"
            className="mt-6 inline-flex h-11 items-center justify-center rounded-2xl bg-ink px-5 text-sm font-medium text-paper"
          >
            Back to runs
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col gap-6 px-6 py-12">
      <header className="panel rounded-3xl p-6 md:p-8">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-ink/50">
              Agent run
            </p>
            <h1 className="mt-4 text-2xl font-semibold">{run.id}</h1>
            <p className="mt-2 text-sm text-ink/60">
              {run.action} | {run.confidence ?? 0} | {run.latency_ms ?? 0}ms
            </p>
            <p className="mt-1 text-xs text-ink/50">
              Created: {run.created_at ?? "unknown"}
            </p>
          </div>
        </div>
      </header>

      <section className="grid gap-6 md:grid-cols-2">
        <div className="panel rounded-3xl p-6 md:p-8">
          <h2 className="text-lg font-semibold">Input</h2>
          <pre className="mt-4 whitespace-pre-wrap break-words text-xs text-ink/70">
            {formatJson(run.input)}
          </pre>
        </div>
        <div className="panel rounded-3xl p-6 md:p-8">
          <h2 className="text-lg font-semibold">Output</h2>
          <pre className="mt-4 whitespace-pre-wrap break-words text-xs text-ink/70">
            {formatJson(run.output)}
          </pre>
        </div>
      </section>

      <section className="panel rounded-3xl p-6 md:p-8">
        <h2 className="text-lg font-semibold">Metadata</h2>
        <pre className="mt-4 whitespace-pre-wrap break-words text-xs text-ink/70">
          {formatJson(run.metadata)}
        </pre>
      </section>
    </div>
  );
}
