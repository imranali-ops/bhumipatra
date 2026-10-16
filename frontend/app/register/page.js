"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { errText } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { useSession } from "@/components/Providers";

export default function RegisterPage() {
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
    const creds = { username: form.get("username"), password: form.get("password") };
    try {
      const reg = await fetch("/api/auth/register", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...creds, email: form.get("email") }),
      });
      if (!reg.ok) {
        const data = await reg.json().catch(() => null);
        setError(errText(data, t("error_generic")));
        setBusy(false);
        return;
      }
      const login = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(creds),
      });
      if (login.ok) {
        await refresh();
        router.push("/dashboard");
        return;
      }
      router.push("/login");
    } catch {
      setError(t("error_generic"));
      setBusy(false);
    }
  }

  return (
    <>
      <h1>{t("register_title")}</h1>
      <p className="muted">{t("register_hint")}</p>
      <form className="stack" onSubmit={onSubmit}>
        {error && <div className="err" role="alert">{error}</div>}
        <label>{t("username")}
          <input name="username" autoComplete="username" required minLength={4} maxLength={30} pattern="[A-Za-z0-9_.\-]{4,30}" />
        </label>
        <label>{t("email")}
          <input name="email" type="email" autoComplete="email" maxLength={254} />
        </label>
        <label>{t("password")}
          <input name="password" type="password" autoComplete="new-password" required minLength={12} maxLength={128} />
        </label>
        <button className="btn" disabled={busy}>{busy ? t("loading") : t("register")}</button>
      </form>
      <p>{t("have_account")} <Link href="/login">{t("login")}</Link></p>
    </>
  );
}
