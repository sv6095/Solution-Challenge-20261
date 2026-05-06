import type { User } from "firebase/auth";
import type { NavigateFunction } from "react-router-dom";
import { toast } from "@/components/ui/sonner";
import { api, storeAuthSession } from "@/lib/api";

const GOOGLE_OAUTH_REMEMBER_KEY = "google_oauth_remember";

export function rememberPreferenceBeforeGoogleRedirect(rememberMe: boolean): void {
  try {
    sessionStorage.setItem(GOOGLE_OAUTH_REMEMBER_KEY, rememberMe ? "1" : "0");
  } catch {
    /* ignore quota / private mode */
  }
}

export function readRememberPreferenceAfterGoogleRedirect(): boolean {
  try {
    const raw = sessionStorage.getItem(GOOGLE_OAUTH_REMEMBER_KEY);
    return raw !== "0";
  } catch {
    return true;
  }
}

export function clearRememberPreferenceFlag(): void {
  try {
    sessionStorage.removeItem(GOOGLE_OAUTH_REMEMBER_KEY);
  } catch {
    /* ignore */
  }
}

export function firebaseAuthErrorMessage(err: unknown): string {
  if (err && typeof err === "object" && "code" in err) {
    const code = String((err as { code?: string }).code);
    const hints: Record<string, string> = {
      "auth/popup-closed-by-user": "Sign-in was cancelled.",
      "auth/unauthorized-domain":
        "This site’s domain is not in Firebase → Authentication → Settings → Authorized domains.",
      "auth/operation-not-allowed":
        "Enable Google in Firebase → Authentication → Sign-in method.",
      "auth/network-request-failed": "Network error. Try again.",
      "auth/account-exists-with-different-credential":
        "An account already exists with this email using a different sign-in method.",
    };
    if (hints[code]) return hints[code];
  }
  if (err instanceof Error) {
    const msg = err.message;
    if (/missing initial state/i.test(msg)) {
      return (
        "Google redirect could not read sign-in state (browser storage partitioning). " +
        "Allow popups for this site and try again, or configure Firebase with your app hostname " +
        "as authDomain and reverse-proxy /__/auth to your-project.firebaseapp.com."
      );
    }
    return msg;
  }
  return "Google sign-in failed.";
}

/**
 * Persist Firebase user + route after Google popup or redirect completes.
 */
export async function completeGoogleOAuthSession(
  user: User,
  navigate: NavigateFunction,
  options?: { rememberMe?: boolean; notify?: boolean },
): Promise<void> {
  const rememberMe = options?.rememberMe ?? true;
  const idToken = await user.getIdToken();
  storeAuthSession({
    userId: user.uid,
    accessToken: idToken,
    refreshToken: "",
    rememberMe,
    authKind: "firebase",
  });
  if (options?.notify !== false) {
    toast.success("Signed in with Google.");
  }
  try {
    const status = await api.onboarding.status(user.uid);
    navigate(status.complete ? "/dashboard" : "/onboarding", { replace: true });
  } catch {
    navigate("/onboarding", { replace: true });
  }
}
