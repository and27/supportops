import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const baseUrl = process.env.AGENT_API_BASE_URL ?? "http://localhost:8000";

const buildUrl = (path: string) => {
  const normalized = baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
  return `${normalized}${path}`;
};

export async function GET(
  _request: Request,
  { params }: { params: { ticketId: string } }
) {
  try {
    const ticketId = encodeURIComponent(params.ticketId);
    const response = await fetch(buildUrl(`/v1/tickets/${ticketId}`), {
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
