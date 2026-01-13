"use client";

import { useState } from "react";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStatus(null);
    setIsSubmitting(true);

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      if (!response.ok) {
        setStatus("Login failed. Check credentials.");
        return;
      }
      window.location.href = "/";
    } catch (error) {
      setStatus("Login failed. Try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-md items-center px-6 py-12">
      <div className="panel w-full rounded-3xl p-6 md:p-8">
        <p className="text-xs uppercase tracking-[0.3em] text-ink/60">
          SupportOps
        </p>
        <h1 className="mt-4 text-2xl font-semibold">Sign in</h1>
        <p className="mt-2 text-sm text-ink/60">
          Use your Supabase Auth credentials to access your orgs.
        </p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label className="text-xs uppercase tracking-[0.2em] text-ink/50">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-2 h-11 w-full rounded-2xl border border-line bg-white px-4 text-sm"
              placeholder="agent@company.com"
              required
            />
          </div>
          <div>
            <label className="text-xs uppercase tracking-[0.2em] text-ink/50">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-2 h-11 w-full rounded-2xl border border-line bg-white px-4 text-sm"
              placeholder="password"
              required
            />
          </div>
          {status && <p className="text-sm text-ink/60">{status}</p>}
          <button
            type="submit"
            className="h-11 w-full rounded-2xl bg-ink text-sm font-medium text-paper"
            disabled={isSubmitting}
          >
            {isSubmitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
