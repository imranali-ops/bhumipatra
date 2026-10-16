// Browser-side helper. All calls go to our own server (/api/proxy/...), which
// adds the login token from the httpOnly cookie.
export async function api(path, { method = "GET", body } = {}) {
  try {
    const res = await fetch(`/api/proxy/${path}`, {
      method,
      credentials: "same-origin",
      cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try {
      data = await res.json();
    } catch {
      /* empty or non-JSON body */
    }
    return { ok: res.ok, status: res.status, data };
  } catch {
    return { ok: false, status: 0, data: null };
  }
}

// Turn any error body from the server into one readable line.
export function errText(data, fallback) {
  if (!data) return fallback;
  const out = [];
  const walk = (v) => {
    if (typeof v === "string") out.push(v);
    else if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v === "object") Object.values(v).forEach(walk);
  };
  walk(data);
  return out.length ? out.join(" ") : fallback;
}

export function fmtDate(iso, lang) {
  try {
    return new Date(iso).toLocaleString(lang === "bn" ? "bn-BD" : "en-GB", {
      dateStyle: "medium", timeStyle: "short",
    });
  } catch {
    return iso;
  }
}
