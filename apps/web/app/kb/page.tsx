"use client";

import { Check, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

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
  const [isDeleting, setIsDeleting] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
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
    setConfirmDeleteId(null);
  };

  const selectDoc = (doc: KbDoc) => {
    setSelectedId(doc.id);
    setForm({
      title: doc.title,
      content: doc.content,
      tags: doc.tags.join(", "),
    });
    setStatus(null);
    setConfirmDeleteId(null);
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
        toast.success("Article created.");
      } else {
        toast.success("Article updated.");
      }
    } catch (error) {
      toast.error("Could not save the article.");
    }
  };

  const deleteDocById = async (docId: string) => {
    setStatus(null);
    setIsDeleting(true);
    try {
      const orgId = readOrgIdCookie();
      const headers: Record<string, string> = {};
      if (orgId) {
        headers["X-Org-Id"] = orgId;
      }
      const response = await fetch(`/api/kb/${docId}`, {
        method: "DELETE",
        headers,
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || "KB delete failed");
      }
      await loadDocs();
      if (selectedId === docId) {
        startNew();
      }
      toast.success("Article deleted.");
    } catch (error) {
      toast.error("Could not delete the article.");
    } finally {
      setIsDeleting(false);
      setConfirmDeleteId(null);
    }
  };

  const deleteDoc = async () => {
    if (!selectedId) {
      return;
    }
    await deleteDocById(selectedId);
  };

  const requestDelete = (docId: string) => {
    setConfirmDeleteId(docId);
    setStatus(null);
  };

  const cancelDelete = () => {
    setConfirmDeleteId(null);
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
              <div
                key={doc.id}
                className={`flex items-start justify-between gap-3 rounded-2xl border px-4 py-3 text-left transition ${
                  selectedId === doc.id
                    ? "border-ink bg-white"
                    : "border-line bg-white/70 hover:border-ink/40"
                }`}
              >
                <button
                  type="button"
                  onClick={() => selectDoc(doc)}
                  className="flex-1 text-left"
                >
                  <p className="font-medium text-ink">{doc.title}</p>
                  <p className="mt-1 text-xs text-ink/50">
                    Tags: {doc.tags.length ? doc.tags.join(", ") : "none"}
                  </p>
                </button>
                <button
                  type="button"
                  aria-label={`Delete ${doc.title}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    requestDelete(doc.id);
                  }}
                  className={`flex h-8 w-8 items-center justify-center rounded-full border text-ink/60 transition hover:border-ink/40 ${
                    confirmDeleteId === doc.id
                      ? "hidden"
                      : "border-line"
                  }`}
                  disabled={isDeleting}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
                {confirmDeleteId === doc.id && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      aria-label={`Confirm delete ${doc.title}`}
                      onClick={(event) => {
                        event.stopPropagation();
                        void deleteDocById(doc.id);
                      }}
                      className="flex h-8 w-8 items-center justify-center rounded-full border border-red-200 text-red-500 transition hover:border-red-300"
                      disabled={isDeleting}
                    >
                      <Check className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      aria-label={`Cancel delete ${doc.title}`}
                      onClick={(event) => {
                        event.stopPropagation();
                        cancelDelete();
                      }}
                      className="flex h-8 w-8 items-center justify-center rounded-full border border-line text-ink/60 transition hover:border-ink/40"
                      disabled={isDeleting}
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                )}
              </div>
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
            <div className="flex flex-wrap gap-3">
              <button
                type="submit"
                className="h-11 rounded-2xl bg-ink px-6 text-sm font-medium text-paper"
              >
                {selectedId ? "Save changes" : "Create article"}
              </button>
              {selectedId && confirmDeleteId !== selectedId && (
                <button
                  type="button"
                  onClick={() => requestDelete(selectedId)}
                  className="h-11 rounded-2xl border border-red-200 px-6 text-sm font-medium text-red-500"
                  disabled={isDeleting}
                >
                  Delete article
                </button>
              )}
              {selectedId && confirmDeleteId === selectedId && (
                <>
                  <button
                    type="button"
                    onClick={deleteDoc}
                    className="h-11 rounded-2xl bg-red-500 px-6 text-sm font-medium text-white"
                    disabled={isDeleting}
                  >
                    {isDeleting ? "Deleting..." : "Confirm delete"}
                  </button>
                  <button
                    type="button"
                    onClick={cancelDelete}
                    className="h-11 rounded-2xl border border-line px-6 text-sm font-medium text-ink/70"
                    disabled={isDeleting}
                  >
                    Cancel
                  </button>
                </>
              )}
            </div>
          </form>
        </div>
      </section>
    </div>
  );
}
