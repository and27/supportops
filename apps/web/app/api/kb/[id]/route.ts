import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const baseUrl = process.env.AGENT_API_BASE_URL ?? "http://localhost:8000";

const buildUrl = (path: string) => {
  const normalized = baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
  return `${normalized}${path}`;
};

export async function GET(
  request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const docId = encodeURIComponent(params.id);
    const orgId = request.headers.get("x-org-id");
    const cookieStore = await cookies();
    const token = cookieStore.get("sb_access_token")?.value;
    const headers: Record<string, string> = {};
    if (orgId) {
      headers["X-Org-Id"] = orgId;
    }
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const response = await fetch(buildUrl(`/v1/kb/${docId}`), {
      cache: "no-store",
      headers,
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { detail: "agent_unavailable" },
      { status: 502 }
    );
  }
}

export async function PATCH(
  request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const payload = await request.json();
    const docId = encodeURIComponent(params.id);
    const orgId = request.headers.get("x-org-id");
    const cookieStore = await cookies();
    const token = cookieStore.get("sb_access_token")?.value;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (orgId) {
      headers["X-Org-Id"] = orgId;
    }
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const response = await fetch(buildUrl(`/v1/kb/${docId}`), {
      method: "PATCH",
      headers,
      body: JSON.stringify(payload),
      cache: "no-store",
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { detail: "agent_unavailable" },
      { status: 502 }
    );
  }
}
