"use client";
import Link from "next/link";
import { useState } from "react";
import { api, errText } from "@/lib/api";
import { useT } from "@/lib/i18n";
import Guard from "@/components/Guard";

function SearchForm() {
  const { t } = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState(null);

  async function onSubmit(e) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const params = new URLSearchParams();
    for (const k of ["khatian_no", "dag_no", "district", "upazila", "mouza"]) {
      const v = String(f.get(k) || "").trim();
      if (v) params.set(k, v);
    }
    if (!params.get("khatian_no") && !params.get("dag_no")) {
      setError(t("need_number"));
      return;
    }
    setBusy(true);
    setError("");
    const r = await api(`parcels/search?${params.toString()}`);
    setBusy(false);
    if (r.ok) setResults(r.data.results);
    else { setResults(null); setError(errText(r.data, t("error_generic"))); }
  }

  return (
    <>
      <h1>{t("search_title")}</h1>
      <form className="stack" onSubmit={onSubmit}>
        {error && <div className="err" role="alert">{error}</div>}
        <label>{t("khatian")}<input name="khatian_no" maxLength={30} inputMode="text" /></label>
        <label>{t("dag")}<input name="dag_no" maxLength={30} /></label>
        <label>{t("district")}<input name="district" maxLength={100} /></label>
        <label>{t("upazila")}<input name="upazila" maxLength={100} /></label>
        <label>{t("mouza")}<input name="mouza" maxLength={100} /></label>
        <button className="btn" disabled={busy}>{busy ? t("loading") : t("search_btn")}</button>
      </form>
      {results && (
        <>
          <h2>{t("results")}</h2>
          {results.length === 0 ? <p className="muted">{t("no_results")}</p> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>{t("khatian")} / {t("dag")}</th><th>{t("mouza")}</th><th>{t("area")}</th><th>{t("owner")}</th><th /></tr></thead>
                <tbody>
                  {results.map((p) => (
                    <tr key={p.id}>
                      <td>{p.khatian_no} / {p.dag_no}</td>
                      <td>{p.mouza}<div className="muted">{p.upazila}, {p.district}</div></td>
                      <td>{p.area_decimal}</td>
                      <td>{p.current_owner.name} <span className="muted">(****{p.current_owner.nid_last4})</span></td>
                      <td><Link href={`/parcels/${p.id}`}>{t("view")}</Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  );
}

export default function SearchPage() {
  return <Guard><SearchForm /></Guard>;
}
