"use client";

const ORG_COOKIE = "org_id";

const findCookie = (name: string): string | null => {
  if (typeof document === "undefined") {
    return null;
  }
  const parts = document.cookie.split("; ").map((part) => part.split("="));
  const match = parts.find(([key]) => key === name);
  if (!match || match.length < 2) {
    return null;
  }
  return decodeURIComponent(match[1]);
};

export const readOrgIdCookie = () => findCookie(ORG_COOKIE);

export const writeOrgIdCookie = (orgId: string) => {
  if (typeof document === "undefined") {
    return;
  }
  const encoded = encodeURIComponent(orgId);
  document.cookie = `${ORG_COOKIE}=${encoded}; path=/; max-age=2592000`;
};
