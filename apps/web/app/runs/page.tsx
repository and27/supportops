import Link from "next/link";
import { cookies } from "next/headers";

import LogoutButton from "../../components/LogoutButton";
import OrgSwitcher from "../../components/OrgSwitcher";

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
  const orgId = cookies().get("org_id")?.value;
  const token = cookies().get("sb_access_token")?.value;
  const runs = await loadRuns(orgId, token);

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
        <div className="flex flex-col items-start gap-3">
          <OrgSwitcher />
          <LogoutButton />
          <a
            href="/"
            className="inline-flex h-11 items-center justify-center rounded-2xl border border-line px-5 text-sm font-medium text-ink"
          >
            Back to chat
          </a>
        </div>
      </header>

      <section className="panel rounded-3xl p-6 md:p-8">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Latest runs</h2>
          <span className="text-xs uppercase tracking-[0.2em] text-ink/50">
            {runs.length} total
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

