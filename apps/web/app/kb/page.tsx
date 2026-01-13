"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { readOrgIdCookie } from "../../lib/org";

type KbDoc = {
  id: string;
  title: string;
  content: string;
  tags: string[];
  created_at?: string | null;
  updated_at?: string | null;
};

type KbForm = {
  title: string;
  content: string;
  tags: string;
};

const emptyForm: KbForm = { title: "", content: "", tags: "" };

const parseTags = (tags: string) =>
  tags
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);

export default function KbPage() {
  const [docs, setDocs] = useState<KbDoc[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState<KbForm>(emptyForm);
  const [status, setStatus] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const searchParams = useSearchParams();
  const docParam = searchParams.get("doc");

  const loadDocs = async () => {
    setIsLoading(true);
    try {
      const orgId = readOrgIdCookie();
      const headers: Record<string, string> = {};
      if (orgId) {
        headers["X-Org-Id"] = orgId;
      }
      const response = await fetch("/api/kb", {
        cache: "no-store",
        headers,
      });
      if (!response.ok) {
        throw new Error("Failed to load KB");
      }
      const data = (await response.json()) as KbDoc[];
      setDocs(data);
    } catch (error) {
      setStatus("KB is unavailable. Check the agent service.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadDocs();
  }, []);

  useEffect(() => {
    if (!docParam || docs.length === 0) {
      return;
    }
    const match = docs.find((doc) => doc.id === docParam);
    if (match) {
      selectDoc(match);
    }
  }, [docParam, docs]);

  const startNew = () => {
    setSelectedId(null);
    setForm(emptyForm);
    setStatus(null);
  };

  const selectDoc = (doc: KbDoc) => {
    setSelectedId(doc.id);
    setForm({
      title: doc.title,
      content: doc.content,
      tags: doc.tags.join(", "),
    });
    setStatus(null);
  };

  const saveDoc = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStatus(null);

    const payload = {
      title: form.title.trim(),
      content: form.content.trim(),
      tags: parseTags(form.tags),
    };

    if (!payload.title || !payload.content) {
      setStatus("Title and content are required.");
      return;
    }

    try {
      const orgId = readOrgIdCookie();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (orgId) {
        headers["X-Org-Id"] = orgId;
      }
      const response = await fetch(
        selectedId ? `/api/kb/${selectedId}` : "/api/kb",
        {
          method: selectedId ? "PATCH" : "POST",
          headers,
          body: JSON.stringify(payload),
        }
      );

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || "KB save failed");
      }

      await loadDocs();
      if (!selectedId) {
        startNew();
      } else {
        setStatus("Saved.");
      }
    } catch (error) {
      setStatus("Could not save the article.");
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-ink/60">
            Knowledge Base
          </p>
          <h1 className="mt-3 text-4xl font-semibold">KB articles</h1>
          <p className="mt-2 max-w-xl text-sm text-ink/70">
            Create and edit the internal help center. Agents use these articles
            to respond with grounded answers.
          </p>
        </div>
        <Link
          href="/"
          className="inline-flex h-11 items-center justify-center rounded-2xl border border-line px-5 text-sm font-medium text-ink"
        >
          Back to chat
        </Link>
      </header>

      <section className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <div className="panel rounded-3xl p-6 md:p-8">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Articles</h2>
            <button
              type="button"
              onClick={startNew}
              className="text-xs uppercase tracking-[0.2em] text-ink/60"
            >
              New article
            </button>
          </div>

          <div className="mt-4 space-y-3 text-sm text-ink/70">
            {isLoading && <p>Loading...</p>}
            {!isLoading && docs.length === 0 && (
              <p>No articles yet. Create the first one.</p>
            )}
            {docs.map((doc) => (
              <button
                key={doc.id}
                type="button"
                onClick={() => selectDoc(doc)}
                className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
                  selectedId === doc.id
                    ? "border-ink bg-white"
                    : "border-line bg-white/70 hover:border-ink/40"
                }`}
              >
                <p className="font-medium text-ink">{doc.title}</p>
                <p className="mt-1 text-xs text-ink/50">
                  Tags: {doc.tags.length ? doc.tags.join(", ") : "none"}
                </p>
              </button>
            ))}
          </div>
        </div>

        <div className="panel rounded-3xl p-6 md:p-8">
          <h2 className="text-lg font-semibold">
            {selectedId ? "Edit article" : "Create article"}
          </h2>
          <p className="mt-1 text-xs text-ink/50">
            {selectedId ? `ID: ${selectedId}` : "New KB entry"}
          </p>

          <form onSubmit={saveDoc} className="mt-6 space-y-4">
            <div>
              <label className="text-xs uppercase tracking-[0.2em] text-ink/50">
                Title
              </label>
              <input
                value={form.title}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, title: event.target.value }))
                }
                className="mt-2 h-11 w-full rounded-2xl border border-line bg-white px-4 text-sm"
                placeholder="Reset password"
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-[0.2em] text-ink/50">
                Content
              </label>
              <textarea
                value={form.content}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, content: event.target.value }))
                }
                className="mt-2 min-h-[160px] w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm"
                placeholder="Step-by-step instructions..."
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-[0.2em] text-ink/50">
                Tags
              </label>
              <input
                value={form.tags}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, tags: event.target.value }))
                }
                className="mt-2 h-11 w-full rounded-2xl border border-line bg-white px-4 text-sm"
                placeholder="login, billing, outage"
              />
            </div>
            {status && <p className="text-sm text-ink/60">{status}</p>}
            <button
              type="submit"
              className="h-11 rounded-2xl bg-ink px-6 text-sm font-medium text-paper"
            >
              {selectedId ? "Save changes" : "Create article"}
            </button>
          </form>
        </div>
      </section>
    </div>
  );
}
