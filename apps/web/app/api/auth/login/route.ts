import { NextResponse } from "next/server";

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseAnonKey = process.env.SUPABASE_ANON_KEY;

export async function POST(request: Request) {
  if (!supabaseUrl || !supabaseAnonKey) {
    return NextResponse.json(
      { detail: "supabase_not_configured" },
      { status: 500 }
    );
  }

  const payload = await request.json();
  const response = await fetch(
    `${supabaseUrl}/auth/v1/token?grant_type=password`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        apikey: supabaseAnonKey,
        Authorization: `Bearer ${supabaseAnonKey}`,
      },
      body: JSON.stringify(payload),
    }
  );

  const data = await response.json();
  if (!response.ok) {
    return NextResponse.json(data, { status: response.status });
  }

  const result = NextResponse.json({ ok: true });
  const maxAge = typeof data.expires_in === "number" ? data.expires_in : 3600;
  result.cookies.set("sb_access_token", data.access_token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge,
  });
  if (data.refresh_token) {
    result.cookies.set("sb_refresh_token", data.refresh_token, {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 24 * 30,
    });
  }
  return result;
}
