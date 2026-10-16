"use client";
import { useT } from "@/lib/i18n";

export default function Footer() {
  const { t } = useT();
  return (
    <footer className="site">
      <div className="wrap">{t("footer_text")}</div>
    </footer>
  );
}
