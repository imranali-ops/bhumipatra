"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { LangProvider } from "@/lib/i18n";

const SessionCtx = createContext({ user: null, loading: true, refresh: async () => {} });

function SessionProvider({ children }) {
  const [state, setState] = useState({ user: null, loading: true });
  const refresh = useCallback(async () => {
    const r = await api("auth/me");
    setState({ user: r.ok ? r.data : null, loading: false });
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  return <SessionCtx.Provider value={{ ...state, refresh }}>{children}</SessionCtx.Provider>;
}

export const useSession = () => useContext(SessionCtx);

export default function Providers({ children }) {
  return (
    <LangProvider>
      <SessionProvider>{children}</SessionProvider>
    </LangProvider>
  );
}
