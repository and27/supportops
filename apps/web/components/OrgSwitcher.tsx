"use client";

import { useEffect, useState } from "react";

import { readOrgIdCookie, writeOrgIdCookie } from "../lib/org";

type Org = {
  id: string;
  name: string;
  slug: string;
};

export default function OrgSwitcher() {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [orgId, setOrgId] = useState<string>("");

  useEffect(() => {
    const loadOrgs = async () => {
      try {
        const response = await fetch("/api/orgs", { cache: "no-store" });
        if (!response.ok) {
          return;
        }
        const data = (await response.json()) as Org[];
        setOrgs(data);
        const stored = readOrgIdCookie();
        const fallback = data[0]?.id ?? "";
        const next = stored && data.some((org) => org.id === stored) ? stored : fallback;
        if (next) {
          setOrgId(next);
          if (next !== stored) {
            writeOrgIdCookie(next);
          }
        }
      } catch (error) {
        // Swallow errors; UI can still render without org selection.
      }
    };

    loadOrgs();
  }, []);

  const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const next = event.target.value;
    setOrgId(next);
    writeOrgIdCookie(next);
    if (typeof window !== "undefined") {
      window.location.reload();
    }
  };

  return (
    <div className="panel flex items-center gap-3 rounded-2xl px-4 py-3 text-xs uppercase tracking-[0.2em] text-ink/60">
      <span>Org</span>
      <select
        value={orgId}
        onChange={handleChange}
        className="rounded-xl border border-line bg-white px-2 py-1 text-xs uppercase tracking-[0.2em] text-ink/70"
      >
        {orgs.length === 0 && <option value="">default</option>}
        {orgs.map((org) => (
          <option key={org.id} value={org.id}>
            {org.slug}
          </option>
        ))}
      </select>
    </div>
  );
}
