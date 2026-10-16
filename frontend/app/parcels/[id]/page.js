"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import Guard from "@/components/Guard";
import { useSession } from "@/components/Providers";

function Detail() {
  const { id } = useParams();
  const { t } = useT();
  const { user } = useSession();
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    api(`parcels/${id}`).then((r) => {
      if (!alive) return;
      if (r.ok) setData(r.data); else setFailed(true);
    });
    return () => { alive = false; };
  }, [id]);

  if (failed) return <div className="err">{t("no_results")}</div>;
  if (!data) return <p className="muted">{t("loading")}</p>;
  const ok = data.integrity.ok;
  return (
    <>
      <h1>{t("parcel_title")}</h1>
      <div className={`big ${ok ? "" : "bad"}`} role="status">
        <span className="ico" aria-hidden="true">{ok ? "✔" : "✖"}</span>
        <span>{ok ? t("integrity_ok") : t("integrity_bad")}</span>
      </div>
      <div className="grid" style={{ marginTop: 16 }}>
        <div className="card">
          <dl className="kv">
            <dt>{t("khatian")}</dt><dd>{data.khatian_no}</dd>
            <dt>{t("dag")}</dt><dd>{data.dag_no}</dd>
            <dt>{t("mouza")}</dt><dd>{data.mouza}</dd>
            <dt>{t("upazila")}</dt><dd>{data.upazila}</dd>
            <dt>{t("district")}</dt><dd>{data.district}</dd>
            <dt>{t("area")}</dt><dd>{data.area_decimal}</dd>
            <dt>{t("land_type")}</dt><dd>{data.land_type}</dd>
            {data.current_owner && (<><dt>{t("owner")}</dt><dd>{data.current_owner.name} (****{data.current_owner.nid_last4})</dd></>)}
          </dl>
          {user.role === "citizen" && ok && (
            <p style={{ marginTop: 16 }}><Link className="btn red" href={`/parcels/${id}/apply`}>{t("apply_btn")}</Link></p>
          )}
        </div>
        <div className="card red">
          <h3>{t("qr_title")}</h3>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="qr" src={`/api/proxy/parcels/${id}/qr.svg`} alt={t("qr_title")} width="200" height="200" />
          <p className="muted">{t("qr_hint")}</p>
        </div>
      </div>
      <h2>{t("history")}</h2>
      <ol className="timeline">
        {data.history.map((h) => (
          <li key={h.seq}>
            <b>{h.owner ? h.owner.name : "?"}</b> <span className="muted">(****{h.owner?.nid_last4})</span>
            <div>{t(`kind_${h.kind}`) === `kind_${h.kind}` ? h.kind : t(`kind_${h.kind}`)} · {h.effective_date}{h.ref ? ` · ${h.ref}` : ""}</div>
            <div className="hash">{t("hash")}: {h.hash}</div>
          </li>
        ))}
      </ol>
    </>
  );
}

export default function ParcelPage() {
  return <Guard><Detail /></Guard>;
}
