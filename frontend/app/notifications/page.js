"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { useT } from "@/lib/i18n";
import Guard from "@/components/Guard";

function List() {
  const { t, lang } = useT();
  const [items, setItems] = useState(null);

  const load = useCallback(async () => {
    const r = await api("notifications");
    setItems(r.ok ? r.data.results : []);
  }, []);
  useEffect(() => { load(); }, [load]);

  async function markRead(id) {
    await api(`notifications/${id}/read`, { method: "POST" });
    await load();
  }

  return (
    <>
      <h1>{t("notif_title")}</h1>
      {!items ? <p className="muted">{t("loading")}</p> : items.length === 0 ? <p className="muted">{t("no_items")}</p> : (
        <div style={{ display: "grid", gap: 12 }}>
          {items.map((n) => (
            <div key={n.id} className={`card ${n.read ? "" : "unread"}`}>
              <div>{!n.read && <b className="flagwarn">{t("unread")} · </b>}{n.message}</div>
              <div className="muted">{fmtDate(n.created_at, lang)}</div>
              <div className="row" style={{ marginTop: 8 }}>
                {n.application_id && <Link href={`/mutations/${n.application_id}`}>{t("view")}</Link>}
                {!n.read && <button className="btn ghost" onClick={() => markRead(n.id)}>{t("mark_read")}</button>}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

export default function NotificationsPage() {
  return <Guard><List /></Guard>;
}
