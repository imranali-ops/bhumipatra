"use client";
import Link from "next/link";
import { fmtDate } from "@/lib/api";
import { useT } from "@/lib/i18n";

const ICON = { valid_current: "✔", valid_outdated: "⚠", invalid: "✖", not_found: "✖", error: "⚠" };
const KEY = { valid_current: "current", valid_outdated: "outdated", invalid: "invalid", not_found: "not_found", error: "error" };

export default function VerifyView({ result }) {
  const { t, lang } = useT();
  const status = result?.status || "error";
  const k = KEY[status] || "error";
  const good = status === "valid_current";
  return (
    <div>
      <h1>{t("verify_title")}</h1>
      <div className={`big ${good ? "" : "bad"}`} role="status">
        <span className="ico" aria-hidden="true">{ICON[status] || "⚠"}</span>
        <span>{t(`v_${k}`)}</span>
      </div>
      <p>{t(`v_${k}_text`)}</p>
      {result?.khatian_no && (
        <div className="card">
          <dl className="kv">
            <dt>{t("khatian")}</dt><dd>{result.khatian_no}</dd>
            <dt>{t("dag")}</dt><dd>{result.dag_no}</dd>
            <dt>{t("mouza")}</dt><dd>{result.mouza}</dd>
            <dt>{t("upazila")}</dt><dd>{result.upazila}</dd>
            <dt>{t("district")}</dt><dd>{result.district}</dd>
            <dt>{t("area")}</dt><dd>{result.area_decimal}</dd>
            <dt>{t("land_type")}</dt><dd>{result.land_type}</dd>
            {result.last_effective_date && (<><dt>{t("last_update")}</dt><dd>{result.last_effective_date}</dd></>)}
            {result.checked_at && (<><dt>{t("checked_at")}</dt><dd>{fmtDate(result.checked_at, lang)}</dd></>)}
          </dl>
        </div>
      )}
      <p className="muted">{t("verify_no_personal")}</p>
      <p><Link href="/">← {t("nav_home")}</Link></p>
    </div>
  );
}
