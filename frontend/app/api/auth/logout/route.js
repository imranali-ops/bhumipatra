import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { backend, clearAuthCookies, clientIp, sameOrigin } from "@/lib/server";

export const dynamic = "force-dynamic";

export async function POST(request) {
  if (!sameOrigin(request)) return NextResponse.json({ detail: "forbidden" }, { status: 403 });
  const refresh = cookies().get("refresh")?.value;
  if (refresh) {
    try {
      // blacklist the refresh token on the server so it cannot be reused
      await fetch(`${backend()}/api/auth/logout/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Forwarded-For": clientIp(request.headers) },
        body: JSON.stringify({ refresh }),
        cache: "no-store",
      });
    } catch { /* cookies are cleared below anyway */ }
  }
  const out = NextResponse.json({ ok: true });
  clearAuthCookies(out);
  return out;
}
