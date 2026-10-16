"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { authEnabled, currentIdToken, signInGoogle, signOutUser, watchAuth } from "@/lib/firebase";

type AuthState = {
  enabled: boolean; loading: boolean; email?: string; error?: string;
  signIn: () => Promise<void>; signOut: () => Promise<void>;
  /** Headers for BFF calls: Authorization bearer when signed in, empty in dev mode. */
  authHeaders: () => Promise<Record<string, string>>;
};

const Ctx = createContext<AuthState | null>(null);
export const useAuth = () => useContext(Ctx)!;

/** Friendly text for Firebase sign-in errors; null means ignore silently. */
function signInMessage(e: unknown): string | null {
  const code = typeof e === "object" && e && "code" in e ? String((e as { code: unknown }).code) : "";
  switch (code) {
    case "auth/popup-closed-by-user":
    case "auth/cancelled-popup-request": return null;
    case "auth/unauthorized-domain": return "This site's address is not authorised for sign-in yet. Ask the owner to add it in Firebase Authentication settings.";
    case "auth/popup-blocked": return "Your browser blocked the sign-in popup. Allow popups and try again.";
    default: return "Sign-in failed. Please try again.";
  }
}

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(authEnabled);
  const [email, setEmail] = useState<string>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    if (!authEnabled) return;
    return watchAuth((u) => { setEmail(u?.email ?? undefined); setLoading(false); });
  }, []);

  const signIn = useCallback(async () => {
    setError(undefined);
    try { await signInGoogle(); } catch (e) { setError(signInMessage(e) ?? undefined); }
  }, []);
  const signOut = useCallback(() => signOutUser(), []);
  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    if (!authEnabled) return {};
    const token = await currentIdToken(); // Firebase refreshes it when expired
    return token ? { authorization: `Bearer ${token}` } : {};
  }, []);

  const value = useMemo(() => ({ enabled: authEnabled, loading, email, error, signIn, signOut, authHeaders }), [loading, email, error, signIn, signOut, authHeaders]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
