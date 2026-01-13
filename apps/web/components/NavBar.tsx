"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import LogoutButton from "./LogoutButton";
import OrgSwitcher from "./OrgSwitcher";

const navLinks = [
  { href: "/", label: "Chat" },
  { href: "/kb", label: "KB" },
  { href: "/tickets", label: "Tickets" },
  { href: "/runs", label: "Runs" },
];

export default function NavBar() {
  const [hasSession, setHasSession] = useState<boolean | null>(null);
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  useEffect(() => {
    const loadSession = async () => {
      try {
        const response = await fetch("/api/auth/session", {
          cache: "no-store",
        });
        if (!response.ok) {
          setHasSession(false);
          return;
        }
        const data = (await response.json()) as { logged_in?: boolean };
        setHasSession(Boolean(data.logged_in));
      } catch (error) {
        setHasSession(false);
      }
    };

    loadSession();
  }, []);

  const closeMenu = () => {
    setIsMenuOpen(false);
  };

  return (
    <div className="mx-auto w-full max-w-6xl px-6 pt-8">
      <nav className="relative flex items-center justify-between">
        <Link href="/" className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-ink text-sm font-semibold text-paper">
            SO
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-ink/60">
              SupportOps
            </p>
            <p className="text-xs text-ink/50">Agent runtime</p>
          </div>
        </Link>

        <div className="hidden items-center gap-3 md:flex">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="panel rounded-2xl px-4 py-2 text-xs uppercase tracking-[0.2em] text-ink/70 transition hover:text-ink"
            >
              {link.label}
            </Link>
          ))}
        </div>

        <div className="hidden items-center gap-3 md:flex">
          <OrgSwitcher />
          {hasSession === true && (
            <LogoutButton className="panel rounded-2xl px-4 py-2 text-xs uppercase tracking-[0.2em] text-ink/70 transition hover:text-ink" />
          )}
          {hasSession === false && (
            <Link
              href="/login"
              className="panel rounded-2xl px-4 py-2 text-xs uppercase tracking-[0.2em] text-ink/70 transition hover:text-ink"
            >
              Sign in
            </Link>
          )}
        </div>

        <button
          type="button"
          onClick={() => setIsMenuOpen((prev) => !prev)}
          className="panel flex h-10 items-center justify-center rounded-2xl px-3 text-xs uppercase tracking-[0.2em] text-ink md:hidden"
          aria-expanded={isMenuOpen}
          aria-label="Toggle navigation"
        >
          Menu
        </button>

        {isMenuOpen && (
          <div className="absolute right-0 top-12 z-20 w-64 rounded-3xl border border-line bg-white/95 p-4 shadow-lg md:hidden">
            <div className="flex flex-col gap-3 text-sm text-ink/70">
              <OrgSwitcher />
              {navLinks.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={closeMenu}
                  className="rounded-2xl border border-line px-4 py-2 text-left transition hover:border-ink/40 hover:text-ink"
                >
                  {link.label}
                </Link>
              ))}
              {hasSession === true && (
                <LogoutButton className="w-full rounded-2xl border border-line px-4 py-2 text-left transition hover:border-ink/40 hover:text-ink" />
              )}
              {hasSession === false && (
                <Link
                  href="/login"
                  onClick={closeMenu}
                  className="rounded-2xl border border-line px-4 py-2 text-left transition hover:border-ink/40 hover:text-ink"
                >
                  Sign in
                </Link>
              )}
            </div>
          </div>
        )}
      </nav>
    </div>
  );
}
