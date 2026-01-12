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

async function loadTicket(ticketId: string): Promise<Ticket | null> {
  try {
    const response = await fetch(buildUrl(`/v1/tickets/${ticketId}`), {
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as Ticket;
  } catch (error) {
    return null;
  }
}

export default async function TicketPage({
  params,
}: {
  params: Promise<{ ticketId: string }>;
}) {
  const { ticketId } = await params;
  const ticket = await loadTicket(ticketId);

  if (!ticket) {
    return (
      <div className="mx-auto flex min-h-screen max-w-2xl items-center justify-center px-6">
        <div className="panel rounded-3xl p-8 text-center">
          <p className="text-sm uppercase tracking-[0.25em] text-ink/50">
            Ticket not found
          </p>
          <h1 className="mt-4 text-2xl font-semibold">We could not load it.</h1>
          <p className="mt-2 text-sm text-ink/60">
            Check the ticket id or return to the chat.
          </p>
          <a
            href="/"
            className="mt-6 inline-flex h-11 items-center justify-center rounded-2xl bg-ink px-5 text-sm font-medium text-paper"
          >
            Back to chat
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 px-6 py-12">
      <header className="panel rounded-3xl p-6 md:p-8">
        <p className="text-xs uppercase tracking-[0.3em] text-ink/50">
          SupportOps ticket
        </p>
        <h1 className="mt-4 text-3xl font-semibold">{ticket.id}</h1>
        <p className="mt-2 text-sm text-ink/60">
          Status: {ticket.status} · Priority: {ticket.priority}
        </p>
      </header>

      <section className="panel rounded-3xl p-6 md:p-8">
        <h2 className="text-lg font-semibold">Summary</h2>
        <p className="mt-2 text-sm text-ink/70">
          {ticket.subject || "No subject recorded."}
        </p>

        <div className="mt-6 grid gap-4 text-sm text-ink/70 md:grid-cols-2">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-ink/50">
              Conversation
            </p>
            <p className="mt-2">{ticket.conversation_id ?? "None"}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-ink/50">
              Created
            </p>
            <p className="mt-2">{ticket.created_at ?? "Unknown"}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-ink/50">
              Updated
            </p>
            <p className="mt-2">{ticket.updated_at ?? "Unknown"}</p>
          </div>
        </div>

        <a
          href="/"
          className="mt-8 inline-flex h-11 items-center justify-center rounded-2xl border border-line px-5 text-sm font-medium text-ink"
        >
          Back to chat
        </a>
      </section>
    </div>
  );
}
