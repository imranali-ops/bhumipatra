"use client";
import { useT } from "@/lib/i18n";

export default function HelpPage() {
  const { t } = useT();
  return (
    <>
      <h1>{t("help_title")}</h1>
      <div style={{ display: "grid", gap: 12 }}>
        {[1, 2, 3, 4].map((n) => (
          <div className="card" key={n}>
            <h3>{t(`q${n}`)}</h3>
            <p style={{ margin: 0 }}>{t(`a${n}`)}</p>
          </div>
        ))}
      </div>
    </>
  );
}
