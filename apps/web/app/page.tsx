"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  action?: "reply" | "ask_clarifying" | "create_ticket" | "escalate";
  confidence?: number;
  ticket_id?: string | null;
};

export default function Home() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "Hi, I am SupportOps. Tell me what is going on and I will look it up.",
    },
  ]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const statusLabel = useMemo(
    () => (conversationId ? "Active conversation" : "New conversation"),
    [conversationId]
  );

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isSending) {
      return;
    }

    setInput("");
    setError(null);
    setIsSending(true);
    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: conversationId ?? undefined,
          channel: "web",
          message: trimmed,
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || "Agent request failed");
      }

      const data = (await response.json()) as {
        conversation_id: string;
        reply: string;
        action: ChatMessage["action"];
        confidence: number;
        ticket_id?: string | null;
      };

      setConversationId(data.conversation_id);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.reply,
          action: data.action,
          confidence: data.confidence,
          ticket_id: data.ticket_id ?? null,
        },
      ]);
    } catch (err) {
      setError("Agent is unavailable. Please try again.");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden text-ink">
      <div className="pointer-events-none absolute inset-0 bg-grid" />
      <div className="pointer-events-none absolute -top-20 right-12 h-64 w-64 rounded-full bg-accent/30 blur-[90px] float-slow" />
      <div className="pointer-events-none absolute bottom-24 left-10 h-52 w-52 rounded-full bg-accent-2/30 blur-[90px] float-fast" />

      <main className="relative mx-auto flex min-h-screen max-w-6xl flex-col gap-10 px-6 py-12">
        <header className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between fade-up">
          <div className="space-y-3">
            <p className="text-xs uppercase tracking-[0.3em] text-ink/60">
              SupportOps
            </p>
            <h1 className="text-4xl font-semibold leading-tight md:text-5xl">
              Agent-driven support desk with an audit trail.
            </h1>
            <p className="max-w-2xl text-base text-ink/70">
              Chat with the runtime, capture every step in Supabase, and keep
              the team looped in with deterministic actions.
            </p>
          </div>
          <div className="panel rounded-2xl px-5 py-4 text-xs uppercase tracking-[0.2em] text-ink/60">
            {statusLabel}
          </div>
        </header>

        <section className="grid gap-6 lg:grid-cols-[1.6fr_0.8fr]">
          <div className="panel rounded-3xl p-6 md:p-8 fade-up">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Live chat</p>
                <p className="text-xs text-ink/60">
                  Messages are stored in Supabase as you send them.
                </p>
              </div>
              <span className="text-xs font-mono uppercase tracking-[0.25em] text-ink/50">
                v0 runtime
              </span>
            </div>

            <div className="mt-6 space-y-4">
              {messages.map((message, index) => {
                const isUser = message.role === "user";
                const confidence =
                  message.confidence !== undefined
                    ? Math.round(message.confidence * 100)
                    : null;

                return (
                  <div
                    key={`${message.role}-${index}`}
                    className={`flex ${isUser ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[82%] space-y-2 rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                        isUser ? "bubble-user" : "bubble-assistant"
                      }`}
                    >
                      <p>{message.content}</p>
                      {!isUser && message.action && (
                        <div className="flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.2em] text-ink/50">
                          <span>Action: {message.action}</span>
                          {confidence !== null && (
                            <span>Confidence: {confidence}%</span>
                          )}
                          {message.ticket_id && (
                            <Link
                              href={`/tickets/${message.ticket_id}`}
                              className="underline decoration-dotted underline-offset-4"
                            >
                              Ticket: {message.ticket_id}
                            </Link>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}

              {error && (
                <div className="rounded-xl border border-accent/30 bg-accent/10 px-4 py-3 text-sm text-ink">
                  {error}
                </div>
              )}
            </div>

            <form onSubmit={handleSubmit} className="mt-6">
              <div className="flex flex-col gap-3 sm:flex-row">
                <input
                  type="text"
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  placeholder="Describe the issue or ask a question"
                  className="h-12 flex-1 rounded-2xl border border-line bg-white/80 px-4 text-sm shadow-sm outline-none transition focus:border-accent/50"
                />
                <button
                  type="submit"
                  disabled={isSending}
                  className="h-12 rounded-2xl bg-ink px-6 text-sm font-medium text-paper transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {isSending ? "Sending..." : "Send message"}
                </button>
              </div>
              <p className="mt-3 text-xs text-ink/50">
                Try asking about login issues, outages, or missing context.
              </p>
            </form>
          </div>

          <aside className="panel rounded-3xl p-6 md:p-8 fade-up">
            <h2 className="text-lg font-semibold">Runtime signals</h2>
            <p className="mt-2 text-sm text-ink/70">
              Every reply includes the action and confidence to keep
              agent logic transparent.
            </p>

            <div className="mt-6 space-y-4 text-sm text-ink/70">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-ink/50">
                  Agent actions
                </p>
                <ul className="mt-2 space-y-2">
                  <li>reply: grounded response from KB</li>
                  <li>ask_clarifying: request missing fields</li>
                  <li>create_ticket: escalate into workflow</li>
                </ul>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-ink/50">
                  What ships next
                </p>
                <ul className="mt-2 space-y-2">
                  <li>KB management dashboard</li>
                  <li>Evidence citations per reply</li>
                  <li>Eval suite with regression cases</li>
                </ul>
              </div>
            </div>
          </aside>
        </section>
      </main>
    </div>
  );
}
