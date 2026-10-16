"use client";
import { useT } from "@/lib/i18n";

export default function StatusBadge({ status }) {
  const { t } = useT();
  return <span className={`status ${status}`}>{t(`st_${status}`)}</span>;
}
