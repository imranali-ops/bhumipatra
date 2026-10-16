import { headers } from "next/headers";
import VerifyView from "@/components/VerifyView";
import { backend, clientIp } from "@/lib/server";

export const dynamic = "force-dynamic";
export const metadata = { title: "রেকর্ড যাচাই | ভূমিপত্র" };

// Public page opened by scanning a QR code. It runs on the server, so no login
// is needed and the backend address is never exposed to the browser.
export default async function VerifyPage({ params }) {
  const { id, prefix } = params;
  // Both values are checked before they are put into a URL.
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id) || !/^[0-9a-f]{16}$/.test(prefix)) {
    return <VerifyView result={{ status: "not_found" }} />;
  }
  let result;
  try {
    const res = await fetch(`${backend()}/api/verify/${id}/${prefix}/`, {
      cache: "no-store",
      headers: { "X-Forwarded-For": clientIp(headers()) },
    });
    result = res.status === 404 ? { status: "not_found" } : res.ok ? await res.json() : { status: "error" };
  } catch {
    result = { status: "error" };
  }
  return <VerifyView result={result} />;
}
