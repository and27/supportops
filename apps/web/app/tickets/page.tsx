import { cookies } from "next/headers";


type Ticket = {
  id: string;
  conversation_id: string | null;
  status: string;
  priority: string;
  subject: string | null;
  created_at: string | null;
  updated_at: string | null;
};

const baseUrl = process.env.AGENT_API_BASE_URL ?? "http://localhost:8000";

const buildUrl = (path: string) => {
  const normalized = baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
  return `${normalized}${path}`;
};

async function loadTickets(
  orgId: string | undefined,
  token: string | undefined
): Promise<Ticket[]> {
  try {
    const headers: Record<string, string> = {};
    if (orgId) {
      headers["X-Org-Id"] = orgId;
    }
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const response = await fetch(buildUrl("/v1/tickets"), {
      cache: "no-store",
      headers,
    });
    if (!response.ok) {
      return [];
    }
    return (await response.json()) as Ticket[];
  } catch (error) {
    return [];
  }
}

export default async function TicketsPage() {
  const cookieStore = await cookies();
  const orgId = cookieStore.get("org_id")?.value;
  const token = cookieStore.get("sb_access_token")?.value;
  const tickets = await loadTickets(orgId, token);

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-ink/60">
            SupportOps
          </p>
          <h1 className="mt-3 text-4xl font-semibold">Tickets</h1>
          <p className="mt-2 max-w-xl text-sm text-ink/70">
            Track open issues that the agent escalated or flagged as needing
            follow-up.
          </p>
        </div>
        <a
          href="/"
          className="inline-flex h-11 items-center justify-center rounded-2xl border border-line px-5 text-sm font-medium text-ink"
        >
          Back to chat
        </a>
      </header>

      <section className="panel rounded-3xl p-6 md:p-8">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Recent tickets</h2>
          <span className="text-xs uppercase tracking-[0.2em] text-ink/50">
            {tickets.length} total
          </span>
        </div>

        <div className="mt-6 space-y-3 text-sm text-ink/70">
          {tickets.length === 0 && (
            <p>No tickets yet. Trigger one from the chat.</p>
          )}
          {tickets.map((ticket) => (
            <a
              key={ticket.id}
              href={`/tickets/${ticket.id}`}
              className="flex flex-col gap-2 rounded-2xl border border-line bg-white/70 px-4 py-3 transition hover:border-ink/40"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="font-medium text-ink">{ticket.id}</span>
                <span className="text-xs uppercase tracking-[0.2em] text-ink/50">
                  {ticket.status} · {ticket.priority}
                </span>
              </div>
              <p className="text-sm text-ink/70">
                {ticket.subject || "No subject recorded."}
              </p>
              <p className="text-xs text-ink/50">
                Created: {ticket.created_at ?? "Unknown"}
              </p>
            </a>
          ))}
        </div>
      </section>
    </div>
  );
}

