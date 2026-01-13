"use client";

import { useState } from "react";

type LogoutButtonProps = {
  className?: string;
  label?: string;
};

export default function LogoutButton({
  className,
  label,
}: LogoutButtonProps) {
  const [isSigningOut, setIsSigningOut] = useState(false);

  const handleLogout = async () => {
    if (isSigningOut) {
      return;
    }
    setIsSigningOut(true);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      window.location.href = "/login";
    }
  };

  const defaultClasses =
    "panel rounded-2xl px-5 py-3 text-ink/70 transition hover:text-ink";
  const buttonClassName = className ?? defaultClasses;

  return (
    <button
      type="button"
      onClick={handleLogout}
      className={`${buttonClassName} disabled:cursor-not-allowed disabled:opacity-70`}
      disabled={isSigningOut}
    >
      {isSigningOut ? "Signing out..." : label ?? "Sign out"}
    </button>
  );
}
