"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import Guard from "@/components/Guard";
import StatusBadge from "@/components/StatusBadge";
import { useSession } from "@/components/Providers";

function AppTable({ items }) {
  const { t } = useT();
  if (!items) return <p className="muted">{t("loading")}</p>;
  if (items.length === 0) return <p className="muted">{t("no_items")}</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr><th>{t("code")}</th><th>{t("khatian")} / {t("dag")}</th><th>{t("kind")}</th><th>{t("status")}</th><th /></tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr key={a.id}>
              <td>{a.code}{a.conflict_flag && <div className="flagwarn">⚠ {t("conflict_warn")}</div>}</td>
              <td>{a.parcel.khatian_no} / {a.parcel.dag_no}<div className="muted">{a.parcel.mouza}</div></td>
              <td>{t(`kind_${a.kind}`)}</td>
              <td><StatusBadge status={a.status} /></td>
              <td><Link href={`/mutations/${a.id}`}>{t("view")}</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Panel() {
  const { t } = useT();
  const { user } = useSession();
  const [items, setItems] = useState(null);
  const role = user.role;
  const listPath = role === "citizen" ? "mutations/mine" : role === "surveyor" || role === "ac_land" ? "mutations/queue" : null;

  useEffect(() => {
    if (!listPath) return;
    let alive = true;
    api(listPath).then((r) => { if (alive) setItems(r.ok ? r.data.results : []); });
    return () => { alive = false; };
  }, [listPath]);

  const title = role === "citizen" ? t("my_apps") : role === "surveyor" ? t("queue_survey") : t("queue_approval");
  return (
    <>
      <h1>{t("dash_title")}</h1>
      <p>{t("hello")}, <b>{user.username}</b> ({t(`role_${role}`)})</p>
      {listPath && (<><h2>{title}</h2><AppTable items={items} /></>)}
      {role === "citizen" && (
        <p><span className="muted">{t("new_app_hint")} </span><Link className="btn" href="/search">{t("nav_search")}</Link></p>
      )}
      {role === "lawyer" && (
        <div className="card"><p>{t("lawyer_hint")}</p><Link className="btn" href="/search">{t("nav_search")}</Link></div>
      )}
      {role === "admin" && <div className="card red"><p>{t("admin_hint")}</p></div>}
    </>
  );
}

export default function DashboardPage() {
  return <Guard><Panel /></Guard>;
}
