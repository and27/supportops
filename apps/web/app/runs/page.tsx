import Link from "next/link";
import { cookies } from "next/headers";


type AgentRun = {
  id: string;
  conversation_id: string | null;
  action: string;
  confidence: number | null;
  latency_ms: number | null;
  metadata: Record<string, unknown> | null;
  created_at: string | null;
};

const baseUrl = process.env.AGENT_API_BASE_URL ?? "http://localhost:8000";

const buildUrl = (path: string) => {
  const normalized = baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
  return `${normalized}${path}`;
};

async function loadRuns(
  orgId: string | undefined,
  token: string | undefined
): Promise<AgentRun[]> {
  try {
    const headers: Record<string, string> = {};
    if (orgId) {
      headers["X-Org-Id"] = orgId;
    }
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const response = await fetch(buildUrl("/v1/runs?limit=50"), {
      cache: "no-store",
      headers,
    });
    if (!response.ok) {
      return [];
    }
    return (await response.json()) as AgentRun[];
  } catch (error) {
    return [];
  }
}

export default async function RunsPage() {
  const cookieStore = await cookies();
  const orgId = cookieStore.get("org_id")?.value;
  const token = cookieStore.get("sb_access_token")?.value;
  const runs = await loadRuns(orgId, token);
  const totalRuns = runs.length;
  const actionCounts = runs.reduce<Record<string, number>>((acc, run) => {
    acc[run.action] = (acc[run.action] ?? 0) + 1;
    return acc;
  }, {});
  const retrievalCounts = runs.reduce<Record<string, number>>((acc, run) => {
    const source =
      typeof run.metadata?.retrieval_source === "string"
        ? run.metadata.retrieval_source
        : "unknown";
    acc[source] = (acc[source] ?? 0) + 1;
    return acc;
  }, {});
  const latencyValues = runs
    .map((run) => run.latency_ms)
    .filter((value): value is number => typeof value === "number");
  const averageLatency = latencyValues.length
    ? Math.round(
        latencyValues.reduce((sum, value) => sum + value, 0) /
          latencyValues.length
      )
    : null;
  const escalationCount = runs.filter((run) =>
    ["create_ticket", "escalate"].includes(run.action)
  ).length;
  const escalationRate = totalRuns
    ? Math.round((escalationCount / totalRuns) * 100)
    : null;
  const sortedActions = Object.entries(actionCounts).sort(
    ([, a], [, b]) => b - a
  );
  const sortedRetrieval = Object.entries(retrievalCounts).sort(
    ([, a], [, b]) => b - a
  );

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-ink/60">
            SupportOps
          </p>
          <h1 className="mt-3 text-4xl font-semibold">Agent runs</h1>
          <p className="mt-2 max-w-xl text-sm text-ink/70">
            Recent decisions with latency and retrieval source metadata.
          </p>
        </div>
        <a
          href="/"
          className="inline-flex h-11 items-center justify-center rounded-2xl border border-line px-5 text-sm font-medium text-ink"
        >
          Back to chat
        </a>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        <div className="panel rounded-3xl p-5">
          <p className="text-xs uppercase tracking-[0.2em] text-ink/50">
            Action mix
          </p>
          <div className="mt-3 space-y-2 text-sm text-ink/70">
            {sortedActions.length === 0 && <p>No runs yet.</p>}
            {sortedActions.map(([action, count]) => (
              <div key={action} className="flex items-center justify-between">
                <span className="uppercase tracking-[0.2em] text-ink/50">
                  {action}
                </span>
                <span className="font-medium text-ink">{count}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="panel rounded-3xl p-5">
          <p className="text-xs uppercase tracking-[0.2em] text-ink/50">
            Latency + escalation
          </p>
          <div className="mt-3 space-y-2 text-sm text-ink/70">
            <div className="flex items-center justify-between">
              <span className="uppercase tracking-[0.2em] text-ink/50">
                Avg latency
              </span>
              <span className="font-medium text-ink">
                {averageLatency !== null ? `${averageLatency}ms` : "n/a"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="uppercase tracking-[0.2em] text-ink/50">
                Escalation
              </span>
              <span className="font-medium text-ink">
                {escalationRate !== null ? `${escalationRate}%` : "n/a"}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs text-ink/50">
              <span>{totalRuns} total runs</span>
              <span>{escalationCount} escalated</span>
            </div>
          </div>
        </div>
        <div className="panel rounded-3xl p-5">
          <p className="text-xs uppercase tracking-[0.2em] text-ink/50">
            Retrieval source
          </p>
          <div className="mt-3 space-y-2 text-sm text-ink/70">
            {sortedRetrieval.length === 0 && <p>No runs yet.</p>}
            {sortedRetrieval.map(([source, count]) => (
              <div key={source} className="flex items-center justify-between">
                <span className="uppercase tracking-[0.2em] text-ink/50">
                  {source}
                </span>
                <span className="font-medium text-ink">{count}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="panel rounded-3xl p-6 md:p-8">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Latest runs</h2>
          <span className="text-xs uppercase tracking-[0.2em] text-ink/50">
            {totalRuns} total
          </span>
        </div>

        <div className="mt-6 space-y-3 text-sm text-ink/70">
          {runs.length === 0 && (
            <p>No runs yet. Send a chat message to create one.</p>
          )}
          {runs.map((run) => (
            <Link
              key={run.id}
              href={`/runs/${run.id}`}
              className="block rounded-2xl border border-line bg-white/70 px-4 py-3 transition hover:border-ink/40"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-ink">{run.id}</span>
                <span className="text-xs uppercase tracking-[0.2em] text-ink/50">
                  {run.action} · {run.confidence ?? 0} ·{" "}
                  {run.latency_ms ?? 0}ms
                </span>
              </div>
              <p className="mt-2 text-xs text-ink/50">
                Conversation: {run.conversation_id ?? "none"}
              </p>
              <p className="mt-1 text-xs text-ink/50">
                Source:{" "}
                {typeof run.metadata?.retrieval_source === "string"
                  ? run.metadata.retrieval_source
                  : "unknown"}
              </p>
              <p className="mt-1 text-xs text-ink/50">
                Created: {run.created_at ?? "unknown"}
              </p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}

