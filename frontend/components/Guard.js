"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useT } from "@/lib/i18n";
import { useSession } from "@/components/Providers";

// Shows its children only to logged-in users (optionally only certain roles).
// This is a convenience for the interface; the real checks are on the server.
export default function Guard({ roles, children }) {
  const { user, loading } = useSession();
  const { t } = useT();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) return <p className="muted">{t("loading")}</p>;
  if (roles && !roles.includes(user.role)) return <div className="err">{t("forbidden")}</div>;
  return <>{children}</>;
}
