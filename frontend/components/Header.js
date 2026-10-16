"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { useSession } from "@/components/Providers";

export default function Header() {
  const { t, lang, setLang } = useT();
  const { user, refresh } = useSession();
  const router = useRouter();
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    let alive = true;
    if (user) {
      api("notifications").then((r) => {
        if (alive && r.ok) setUnread(r.data.results.filter((n) => !n.read).length);
      });
    } else {
      setUnread(0);
    }
    return () => { alive = false; };
  }, [user]);

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
    await refresh();
    router.push("/");
  }

  return (
    <>
      <div className="topbar">
        <div className="wrap">
          <span className="flag" aria-hidden="true" />
          <span className="grow">{t("app_sub")}</span>
          <button className="langbtn" onClick={() => setLang(lang === "bn" ? "en" : "bn")}>
            {t("language")}
          </button>
        </div>
      </div>
      <div className="notice"><div className="wrap">{t("prototype_notice")}</div></div>
      <header className="site">
        <div className="wrap">
          <Link href="/" className="brand">
            <span>
              <b>{t("app_name")}</b>
              <small>{t("app_sub")}</small>
            </span>
          </Link>
          <nav className="main" aria-label="main">
            <Link href="/">{t("nav_home")}</Link>
            <Link href="/search">{t("nav_search")}</Link>
            {user && <Link href="/dashboard">{t("nav_dashboard")}</Link>}
            {user && (
              <Link href="/notifications">
                {t("nav_notifications")}
                {unread > 0 && <span className="badge-count">{unread}</span>}
              </Link>
            )}
            <Link href="/help">{t("nav_help")}</Link>
            {user ? (
              <button className="linkbtn" onClick={logout}>{t("logout")} ({user.username})</button>
            ) : (
              <>
                <Link href="/login">{t("login")}</Link>
                <Link href="/register">{t("register")}</Link>
              </>
            )}
          </nav>
        </div>
      </header>
    </>
  );
}
