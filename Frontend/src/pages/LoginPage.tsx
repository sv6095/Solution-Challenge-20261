import { useState } from "react";
import { Link } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff } from "lucide-react";
import { toast } from "@/components/ui/sonner";
import { api, storeAuthSession } from "@/lib/api";
import { getFirebaseAuth, hasFirebaseAuthConfig } from "@/lib/firebase";
import {
  completeGoogleOAuthSession,
  firebaseAuthErrorMessage,
  rememberPreferenceBeforeGoogleRedirect,
} from "@/lib/firebaseRedirect";

const LoginPage = () => {
  const navigate = useNavigate();
  const [showPassword, setShowPassword] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [googleSubmitting, setGoogleSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error("Email and password are required.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.auth.login({ email: email.trim(), password, remember_me: rememberMe });
      storeAuthSession({
        userId: res.user_id,
        accessToken: res.access_token,
        refreshToken: res.refresh_token,
        rememberMe,
        authKind: "local",
      });
      toast.success("Signed in.");
      try {
        const status = await api.onboarding.status(res.user_id);
        navigate(status.complete ? "/dashboard" : "/onboarding");
      } catch {
        navigate("/onboarding");
      }
    } catch {
      toast.error("Sign in failed. Check your credentials.");
    } finally {
      setSubmitting(false);
    }
  };

  const onGoogleSignIn = async () => {
    if (!hasFirebaseAuthConfig || !getFirebaseAuth()) {
      toast.error(
        "Firebase Auth is not configured. Set VITE_FIREBASE_API_KEY, VITE_FIREBASE_AUTH_DOMAIN (e.g. your-project.firebaseapp.com), PROJECT_ID, APP_ID, and redeploy.",
      );
      return;
    }

    setGoogleSubmitting(true);
    try {
      const { GoogleAuthProvider, signInWithPopup, signInWithRedirect } = await import("firebase/auth");
      const auth = getFirebaseAuth()!;
      const provider = new GoogleAuthProvider();
      provider.addScope("profile");
      provider.addScope("email");
      provider.setCustomParameters({ prompt: "select_account" });

      rememberPreferenceBeforeGoogleRedirect(rememberMe);

      // Popup sign-in polls `window.closed` on the opener; strict COOP (common on hosts like Vercel)
      // makes that unreliable and floods the console. Redirect works everywhere for production SPA.
      if (import.meta.env.PROD) {
        await signInWithRedirect(auth, provider);
        return;
      }

      try {
        const cred = await signInWithPopup(auth, provider);
        await completeGoogleOAuthSession(cred.user, navigate, { rememberMe });
      } catch (err) {
        const code = err && typeof err === "object" && "code" in err ? String((err as { code: string }).code) : "";
        if (code === "auth/popup-blocked") {
          toast("Popup blocked — redirecting to Google sign-in…");
          await signInWithRedirect(auth, provider);
          return;
        }
        throw err;
      }
    } catch (err) {
      toast.error(firebaseAuthErrorMessage(err));
    } finally {
      setGoogleSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-background font-headline">
      {/* Left branding panel */}
      <div className="hidden lg:flex lg:w-[45%] flex-col justify-between p-8 relative bg-sky-50 border-r border-sky-100">
        <div className="flex items-center gap-3 text-slate-900">
          <img src="/Praecantator.png" alt="Logo" className="w-10 h-10 object-contain" />
          <span className="font-headline text-xl font-bold">Praecantator</span>
        </div>

        <div className="-mt-8">
          <h1 className="text-display-lg leading-tight mb-4 text-slate-900">
            Securing the <span className="text-sentinel">Global Flow</span> of Kinetic Logistics.
          </h1>
          <p className="text-body-md text-slate-600 max-w-md">
            The Kinetic Fortress architecture provides real-time threat neutralization and exposure management for the world's most critical supply chains.
          </p>
        </div>

        <div className="flex gap-6 text-label-sm text-slate-500 uppercase tracking-widest">
          <span>Precision Logic</span>
          <span>Kinetic Fortress</span>
          <span>© 2026</span>
        </div>
      </div>

      {/* Right form panel */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-md glass-panel rounded-xl p-8">
          <h2 className="font-headline text-headline-md font-bold text-slate-800 mb-1">Welcome back</h2>
          <p className="text-body-md text-slate-600 mb-6">Sign in to your Praecantator workspace</p>

          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="text-label-sm uppercase tracking-widest text-slate-500 block mb-2">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
                className="input-sentinel w-full px-4 py-3 rounded-sm"
              />
            </div>

            <div>
              <label className="text-label-sm uppercase tracking-widest text-slate-500 block mb-2">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="input-sentinel w-full px-4 py-3 rounded-sm pr-12"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700 transition-colors"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-body-md text-slate-600 cursor-pointer">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="w-4 h-4 rounded-sm bg-surface border-border accent-sentinel-red"
                />
                Remember node
              </label>
              <Link to="/forgot-password" className="text-body-md text-sentinel hover:underline">Reset credentials</Link>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-foreground text-background py-3 rounded-sm font-medium flex items-center justify-center gap-2 hover:opacity-90 transition-opacity"
            >
              {submitting ? "Signing in…" : <>Sign In <span>→</span></>}
            </button>
          </form>

          <div className="flex items-center gap-4 my-5">
            <div className="flex-1 h-px bg-border" />
            <span className="text-label-sm text-slate-500 uppercase tracking-widest">Or continue with</span>
            <div className="flex-1 h-px bg-border" />
          </div>

          <button
            type="button"
            onClick={() => void onGoogleSignIn()}
            disabled={submitting || googleSubmitting}
            className="w-full glass-panel py-3 rounded-sm font-medium flex items-center justify-center gap-3 hover:bg-slate-50 transition-colors disabled:opacity-60"
          >
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden>
              <path
                d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"
                fill="#4285F4"
              />
              <path
                d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z"
                fill="#34A853"
              />
              <path
                d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"
                fill="#FBBC05"
              />
              <path
                d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"
                fill="#EA4335"
              />
            </svg>
            {googleSubmitting ? "Signing in…" : "Google Sign-In"}
          </button>

          <p className="text-center text-body-md text-slate-500 mt-5">
            Access restricted to authorized personnel.
            <br />
            Protected by <span className="text-slate-800 font-medium">Praecantator Kinetic Fortress</span> protocols.
          </p>

          <p className="text-center text-body-md text-slate-600 mt-4">
            Don't have an account?{" "}
            <Link to="/register" className="text-sentinel hover:underline">
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
