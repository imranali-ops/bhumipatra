// Server-only helpers (route handlers and server components). Tokens live in
// httpOnly cookies, so JavaScript in the browser can never read them.
const prod = process.env.NODE_ENV === "production";
// Cookies are Secure (HTTPS-only) in production. COOKIE_SECURE=false exists only
// for trying the production build over plain http://localhost.
const secure = process.env.COOKIE_SECURE ? process.env.COOKIE_SECURE === "true" : prod;

export function backend() {
  const url = (process.env.BACKEND_URL || "").replace(/\/$/, "");
  if (!url) throw new Error("BACKEND_URL is not set (see .env.example)");
  return url;
}

// IP forwarded to Django for rate limiting and the audit log.
export function clientIp(headers) {
  if (process.env.TRUST_FRONT_PROXY === "true") {
    const parts = (headers.get("x-forwarded-for") || "").split(",").map((s) => s.trim()).filter(Boolean);
    if (parts.length) return parts[parts.length - 1]; // entry added by our own proxy
  }
  return "127.0.0.1";
}

// CSRF defence for state-changing requests: the Origin header must be our own host.
export function sameOrigin(request) {
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  if (!origin || !host) return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

const base = { httpOnly: true, secure, sameSite: "strict", path: "/" };

export function setAuthCookies(res, { access, refresh }) {
  if (access) res.cookies.set("access", access, { ...base, maxAge: 600 });
  if (refresh) res.cookies.set("refresh", refresh, { ...base, maxAge: 8 * 3600 });
}

export function clearAuthCookies(res) {
  for (const name of ["access", "refresh"]) res.cookies.set(name, "", { ...base, maxAge: 0 });
}

// Django rotates the refresh token on every use. If several requests notice an
// expired access token at once, they must share ONE refresh call, otherwise the
// second one would use an already-rotated token and log the user out.
const inflight = new Map();

export function refreshTokens(refresh, ip) {
  if (inflight.has(refresh)) return inflight.get(refresh);
  const promise = (async () => {
    try {
      const r = await fetch(`${backend()}/api/auth/refresh/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Forwarded-For": ip },
        body: JSON.stringify({ refresh }),
        cache: "no-store",
      });
      if (!r.ok) return null;
      const data = await r.json();
      return data && data.access ? data : null;
    } catch {
      return null;
    } finally {
      setTimeout(() => inflight.delete(refresh), 5000);
    }
  })();
  inflight.set(refresh, promise);
  return promise;
}
