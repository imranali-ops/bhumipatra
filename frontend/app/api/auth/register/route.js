import { NextResponse } from "next/server";
import { backend, clientIp, sameOrigin } from "@/lib/server";

export const dynamic = "force-dynamic";

export async function POST(request) {
  if (!sameOrigin(request)) return NextResponse.json({ detail: "forbidden" }, { status: 403 });
  let payload;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ detail: "bad request" }, { status: 400 });
  }
  // Only these three fields are forwarded; a role can never be chosen here.
  const body = {
    username: String(payload?.username ?? "").slice(0, 30),
    email: String(payload?.email ?? "").slice(0, 254),
    password: String(payload?.password ?? "").slice(0, 128),
  };
  try {
    const res = await fetch(`${backend()}/api/auth/register/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Forwarded-For": clientIp(request.headers) },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ detail: "unavailable" }, { status: 502 });
  }
}
