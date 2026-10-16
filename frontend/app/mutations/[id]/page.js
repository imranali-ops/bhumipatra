"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, errText, fmtDate } from "@/lib/api";
import { useT } from "@/lib/i18n";
import Guard from "@/components/Guard";
import StatusBadge from "@/components/StatusBadge";
import { useSession } from "@/components/Providers";

function Detail() {
  const { id } = useParams();
  const { t, lang } = useT();
  const { user } = useSession();
  const [app, setApp] = useState(null);
  const [failed, setFailed] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [docError, setDocError] = useState("");
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async () => {
    const r = await api(`mutations/${id}`);
    if (r.ok) setApp(r.data); else setFailed(true);
  }, [id]);
  useEffect(() => { load(); }, [load]);

  async function act(action) {
    if (action === "approve" && !window.confirm(t("confirm_approve"))) return;
    setBusy(true);
    setError("");
    const r = await api(`mutations/${id}/action`, { method: "POST", body: { action, note } });
    setBusy(false);
    if (r.ok) { setNote(""); await load(); } else setError(errText(r.data, t("error_generic")));
  }

  async function upload(e) {
    e.preventDefault();
    const form = e.currentTarget;
    const file = new FormData(form).get("file");
    if (!file || !file.size) return;
    if (file.size > 5 * 1024 * 1024) { setDocError(t("doc_too_big")); return; }
    setUploading(true);
    setDocError("");
    try {
      const res = await fetch(`/api/proxy/mutations/${id}/documents`, {
        method: "POST",
        credentials: "same-origin",
        body: new FormData(form),
      });
      const data = await res.json().catch(() => null);
      if (res.ok) { form.reset(); await load(); } else setDocError(errText(data, t("error_generic")));
    } catch {
      setDocError(t("error_generic"));
    }
    setUploading(false);
  }

  if (failed) return <div className="err">{t("no_results")}</div>;
  if (!app) return <p className="muted">{t("loading")}</p>;

  const officer = user.role === "surveyor" || user.role === "ac_land";
  const canSurvey = user.role === "surveyor" && app.status === "submitted";
  const canDecide = user.role === "ac_land" && app.status === "survey_verified";
  const canCancel = user.role === "citizen" && app.status === "submitted";

  return (
    <>
      <h1>{t("app_title")}</h1>
      {app.conflict_flag && <div className="err" role="alert">⚠ {t("conflict_warn")}</div>}
      <div className="card" style={{ marginTop: 12 }}>
        <dl className="kv">
          <dt>{t("code")}</dt><dd>{app.code}</dd>
          <dt>{t("status")}</dt><dd><StatusBadge status={app.status} /></dd>
          <dt>{t("kind")}</dt><dd>{t(`kind_${app.kind}`)}</dd>
          <dt>{t("deed_ref")}</dt><dd>{app.deed_ref}</dd>
          <dt>{t("khatian")} / {t("dag")}</dt>
          <dd><Link href={`/parcels/${app.parcel.id}`}>{app.parcel.khatian_no} / {app.parcel.dag_no}</Link> <span className="muted">{app.parcel.mouza}</span></dd>
          {officer && app.seller && (<><dt>{t("seller")}</dt><dd>{app.seller.name} (****{app.seller.nid_last4})</dd></>)}
          {officer && app.claimant && (<><dt>{t("claimant")}</dt><dd>{app.claimant.name} (****{app.claimant.nid_last4})</dd></>)}
        </dl>
      </div>

      {(canSurvey || canDecide || canCancel) && (
        <div className="card red" style={{ marginTop: 16 }}>
          {error && <div className="err" role="alert" style={{ marginBottom: 10 }}>{error}</div>}
          {(canSurvey || canDecide) && (
            <label>{t("note_label")}
              <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} />
            </label>
          )}
          <div className="row" style={{ marginTop: 12 }}>
            {canSurvey && (<>
              <button className="btn" disabled={busy} onClick={() => act("survey_verify")}>{t("action_survey_verify")}</button>
              <button className="btn red" disabled={busy} onClick={() => act("survey_reject")}>{t("action_survey_reject")}</button>
            </>)}
            {canDecide && (<>
              <button className="btn" disabled={busy} onClick={() => act("approve")}>{t("action_approve")}</button>
              <button className="btn red" disabled={busy} onClick={() => act("reject")}>{t("action_reject")}</button>
            </>)}
            {canCancel && <button className="btn red" disabled={busy} onClick={() => act("cancel")}>{t("action_cancel")}</button>}
          </div>
        </div>
      )}

      <h2>{t("docs_title")}</h2>
      {app.documents.length === 0 ? <p className="muted">{t("no_docs")}</p> : (
        <ul>
          {app.documents.map((d) => (
            <li key={d.id}>
              <a href={`/api/proxy/mutations/${id}/documents/${d.id}`}>{d.name}</a>{" "}
              <span className="muted">({d.kind.toUpperCase()}, {Math.ceil(d.size / 1024)} KB)</span>
              <div className="hash">SHA-256: {d.sha256}</div>
            </li>
          ))}
        </ul>
      )}
      {canCancel && (
        <form className="stack" onSubmit={upload}>
          {docError && <div className="err" role="alert">{docError}</div>}
          <label>{t("upload_label")}
            <input type="file" name="file" required accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/png,image/jpeg" />
          </label>
          <p className="muted" style={{ margin: 0 }}>{t("upload_hint")}</p>
          <button className="btn ghost" disabled={uploading}>{uploading ? t("loading") : t("upload_btn")}</button>
        </form>
      )}

      <h2>{t("steps")}</h2>
      <ol className="timeline">
        {app.steps.map((s, i) => (
          <li key={i}>
            <b>{t(`act_${s.action}`)}</b> <span className="muted">· {fmtDate(s.at, lang)}</span>
            {s.note && <div>{s.note}</div>}
          </li>
        ))}
      </ol>
    </>
  );
}

export default function MutationPage() {
  return <Guard roles={["citizen", "surveyor", "ac_land"]}><Detail /></Guard>;
}
