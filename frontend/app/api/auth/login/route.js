import { NextResponse } from "next/server";
import { backend, clientIp, sameOrigin, setAuthCookies } from "@/lib/server";

export const dynamic = "force-dynamic";

export async function POST(request) {
  if (!sameOrigin(request)) return NextResponse.json({ detail: "forbidden" }, { status: 403 });
  let payload;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ detail: "bad request" }, { status: 400 });
  }
  const username = String(payload?.username ?? "").slice(0, 150);
  const password = String(payload?.password ?? "").slice(0, 128);
  let res;
  try {
    res = await fetch(`${backend()}/api/auth/login/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Forwarded-For": clientIp(request.headers) },
      body: JSON.stringify({ username, password }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "unavailable" }, { status: 502 });
  }
  if (res.status === 429) return NextResponse.json({ detail: "throttled" }, { status: 429 });
  if (!res.ok) return NextResponse.json({ detail: "invalid" }, { status: 401 });
  const tokens = await res.json();
  const out = NextResponse.json({ ok: true });
  setAuthCookies(out, tokens);
  return out;
}
