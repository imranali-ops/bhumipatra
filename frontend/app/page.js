"use client";
import Link from "next/link";
import { useT } from "@/lib/i18n";
import { useSession } from "@/components/Providers";

export default function Home() {
  const { t } = useT();
  const { user } = useSession();
  return (
    <>
      <section className="hero hero-land">
        <div className="hero-panel">
          <h1>{t("hero_title")}</h1>
          <p>{t("hero_text")}</p>
          <div className="row">
            <Link className="btn ghost" href="/search">{t("cta_search")}</Link>
            {!user && <Link className="btn ghost" href="/login">{t("cta_login")}</Link>}
          </div>
        </div>
      </section>
      <div className="grid">
        <div className="card"><h3>{t("f1_title")}</h3><p>{t("f1_text")}</p></div>
        <div className="card red"><h3>{t("f2_title")}</h3><p>{t("f2_text")}</p></div>
        <div className="card"><h3>{t("f3_title")}</h3><p>{t("f3_text")}</p></div>
      </div>
      <h2>{t("how_title")}</h2>
      <ol className="steps">
        {[1, 2, 3, 4, 5].map((n) => <li key={n}>{t(`how${n}`)}</li>)}
      </ol>
    </>
  );
}
