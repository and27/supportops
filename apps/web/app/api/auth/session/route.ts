import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export async function GET() {
  const cookieStore = await cookies();
  const token = cookieStore.get("sb_access_token")?.value;
  return NextResponse.json({ logged_in: Boolean(token) });
}
