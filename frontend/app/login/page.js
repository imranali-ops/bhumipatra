"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useT } from "@/lib/i18n";
import { useSession } from "@/components/Providers";

export default function LoginPage() {
  const { t } = useT();
  const { refresh } = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(e.currentTarget);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: form.get("username"), password: form.get("password") }),
      });
      if (res.ok) {
        await refresh();
        router.push("/dashboard");
        return;
      }
      setError(res.status === 429 ? t("login_throttled") : res.status === 401 ? t("login_failed") : t("error_generic"));
    } catch {
      setError(t("error_generic"));
    }
    setBusy(false);
  }

  return (
    <>
      <h1>{t("login_title")}</h1>
      <form className="stack" onSubmit={onSubmit}>
        {error && <div className="err" role="alert">{error}</div>}
        <label>{t("username")}
          <input name="username" autoComplete="username" required maxLength={150} />
        </label>
        <label>{t("password")}
          <input name="password" type="password" autoComplete="current-password" required maxLength={128} />
        </label>
        <button className="btn" disabled={busy}>{busy ? t("loading") : t("login")}</button>
      </form>
      <p>{t("no_account")} <Link href="/register">{t("register")}</Link></p>
    </>
  );
}
