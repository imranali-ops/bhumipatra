import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import {
  backend, clearAuthCookies, clientIp, refreshTokens, sameOrigin, setAuthCookies,
} from "@/lib/server";

export const dynamic = "force-dynamic";

const MAX_UPLOAD = 5 * 1024 * 1024 + 100000; // 5 MB file plus form overhead

const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
// Only these backend paths can be reached from the browser.
const ALLOWED = [
  "^parcels/search/$",
  `^parcels/${UUID}/$`,
  `^parcels/${UUID}/qr\\.svg$`,
  "^mutations/$",
  "^mutations/mine/$",
  "^mutations/queue/$",
  `^mutations/${UUID}/$`,
  `^mutations/${UUID}/action/$`,
  `^mutations/${UUID}/documents/$`,
  `^mutations/${UUID}/documents/[0-9]{1,12}/$`,
  "^notifications/$",
  "^notifications/[0-9]{1,12}/read/$",
  "^auth/me/$",
].map((p) => new RegExp(p));

async function handle(request, { params }) {
  let path = (params.path || []).join("/");
  if (!path.endsWith(".svg")) path += "/";
  if (!ALLOWED.some((re) => re.test(path))) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }
  const method = request.method;
  if (method !== "GET" && !sameOrigin(request)) {
    return NextResponse.json({ detail: "forbidden" }, { status: 403 });
  }
  const search = method === "GET" ? new URL(request.url).search : "";
  let body;
  let contentType = "application/json";
  if (method === "POST") {
    const incoming = request.headers.get("content-type") || "";
    if (incoming.startsWith("multipart/form-data")) {
      // file uploads: only on the documents path, and the size is checked before reading
      if (!/\/documents\/$/.test(path)) return NextResponse.json({ detail: "unsupported" }, { status: 415 });
      if (Number(request.headers.get("content-length") || 0) > MAX_UPLOAD) {
        return NextResponse.json({ detail: "too large" }, { status: 413 });
      }
      body = await request.arrayBuffer();
      if (body.byteLength > MAX_UPLOAD) return NextResponse.json({ detail: "too large" }, { status: 413 });
      contentType = incoming; // keeps the multipart boundary
    } else {
      body = await request.text();
      if (body.length > 20000) return NextResponse.json({ detail: "too large" }, { status: 413 });
    }
  }

  const ip = clientIp(request.headers);
  const jar = cookies();
  const refresh = jar.get("refresh")?.value;
  let access = jar.get("access")?.value;
  let fresh = null;

  const call = (token) =>
    fetch(`${backend()}/api/${path}${search}`, {
      method,
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        "X-Forwarded-For": ip,
        ...(method === "POST" ? { "Content-Type": contentType } : {}),
      },
      body,
      cache: "no-store",
      redirect: "manual",
    });

  try {
    if (!access && refresh) {
      fresh = await refreshTokens(refresh, ip);
      access = fresh?.access;
    }
    let res = await call(access);
    if (res.status === 401 && refresh && !fresh) {
      fresh = await refreshTokens(refresh, ip);
      if (fresh) res = await call(fresh.access);
    }
    const out = new NextResponse(await res.arrayBuffer(), {
      status: res.status,
      headers: {
        "content-type": res.headers.get("content-type") || "application/json",
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
        ...(res.headers.get("content-disposition")
          ? { "content-disposition": res.headers.get("content-disposition") } : {}),
        ...(res.headers.get("content-security-policy")
          ? { "content-security-policy": res.headers.get("content-security-policy") } : {}),
      },
    });
    if (fresh) setAuthCookies(out, fresh);
    else if (res.status === 401 && (refresh || jar.get("access"))) clearAuthCookies(out);
    return out;
  } catch {
    return NextResponse.json({ detail: "unavailable" }, { status: 502 });
  }
}

export const GET = handle;
export const POST = handle;
