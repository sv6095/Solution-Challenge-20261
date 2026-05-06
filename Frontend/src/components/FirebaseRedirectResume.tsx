import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getFirebaseAuth, hasFirebaseAuthConfig } from "@/lib/firebase";
import {
  clearRememberPreferenceFlag,
  completeGoogleOAuthSession,
  firebaseAuthErrorMessage,
  readRememberPreferenceAfterGoogleRedirect,
} from "@/lib/firebaseRedirect";
import { toast } from "@/components/ui/sonner";
import type { UserCredential } from "firebase/auth";

/**
 * One shared `getRedirectResult` promise per full page load. A second call
 * always returns null and would strand the user if two effects ran it
 * (e.g. React Strict Mode or duplicate mount).
 */
let redirectResultInFlight: Promise<UserCredential | null> | null = null;

/**
 * Firebase `signInWithRedirect` can return the user to any URL on this origin
 * (often `/` after the auth handler). `getRedirectResult` must run on that
 * first paint — not only on `/login` — or the pending redirect is never
 * completed and the user stays signed out.
 */
export function FirebaseRedirectResume() {
  const navigate = useNavigate();

  useEffect(() => {
    if (!hasFirebaseAuthConfig) return;

    let cancelled = false;
    void (async () => {
      try {
        const { getRedirectResult } = await import("firebase/auth");
        const auth = getFirebaseAuth();
        if (!auth) return;

        if (!redirectResultInFlight) {
          redirectResultInFlight = getRedirectResult(auth);
        }
        const result = await redirectResultInFlight;
        if (!result?.user) return;
        if (cancelled) return;

        const rememberMe = readRememberPreferenceAfterGoogleRedirect();
        clearRememberPreferenceFlag();
        await completeGoogleOAuthSession(result.user, navigate, { rememberMe });
      } catch (err) {
        clearRememberPreferenceFlag();
        if (!cancelled) toast.error(firebaseAuthErrorMessage(err));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [navigate]);

  return null;
}
