"use client";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { api, errText } from "@/lib/api";
import { useT } from "@/lib/i18n";
import Guard from "@/components/Guard";

function ApplyForm() {
  const { id } = useParams();
  const { t } = useT();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const f = new FormData(e.currentTarget);
    const r = await api("mutations", {
      method: "POST",
      body: {
        parcel_id: id,
        kind: f.get("kind"),
        deed_ref: f.get("deed_ref"),
        claimant_name: f.get("claimant_name"),
        claimant_nid: f.get("claimant_nid"),
        claimant_address: f.get("claimant_address") || "",
      },
    });
    if (r.ok) {
      router.push(`/mutations/${r.data.id}`);
      return;
    }
    setError(errText(r.data, t("error_generic")));
    setBusy(false);
  }

  return (
    <>
      <h1>{t("apply_title")}</h1>
      <p className="muted">{t("nid_notice")}</p>
      <form className="stack" onSubmit={onSubmit}>
        {error && <div className="err" role="alert">{error}</div>}
        <label>{t("kind")}
          <select name="kind" defaultValue="sale">
            {["sale", "inheritance", "gift", "court_order"].map((k) => <option key={k} value={k}>{t(`kind_${k}`)}</option>)}
          </select>
        </label>
        <label>{t("deed_ref")}<input name="deed_ref" required maxLength={100} /></label>
        <label>{t("claimant_name")}<input name="claimant_name" required maxLength={200} /></label>
        <label>{t("claimant_nid")}<input name="claimant_nid" required maxLength={30} inputMode="numeric" /></label>
        <label>{t("claimant_address")}<input name="claimant_address" maxLength={300} /></label>
        <button className="btn" disabled={busy}>{busy ? t("loading") : t("submit")}</button>
      </form>
    </>
  );
}

export default function ApplyPage() {
  return <Guard roles={["citizen"]}><ApplyForm /></Guard>;
}
