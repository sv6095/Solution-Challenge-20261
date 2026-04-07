import { useState } from "react";
import { Link } from "react-router-dom";
import { Eye, EyeOff } from "lucide-react";

const LoginPage = () => {
  const [showPassword, setShowPassword] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  return (
    <div className="min-h-screen flex bg-background">
      {/* Left branding panel */}
      <div className="hidden lg:flex lg:w-[45%] flex-col justify-between p-12 relative kinetic-gradient">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-sentinel rounded-sm" />
          <span className="font-headline text-xl font-bold">Praecantator</span>
        </div>

        <div>
          <h1 className="text-display-lg leading-tight mb-6">
            Securing the <span className="text-sentinel">Global Flow</span> of Kinetic Logistics.
          </h1>
          <p className="text-body-md text-secondary max-w-md">
            The Kinetic Fortress architecture provides real-time threat neutralization and exposure management for the world's most critical supply chains.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="surface-container-high rounded-lg p-5 animate-float">
            <span className="text-label-sm text-sentinel uppercase tracking-widest">⚠ Disruptions Detected</span>
            <p className="font-headline text-3xl font-bold mt-2">340</p>
          </div>
          <div className="surface-container-high rounded-lg p-5 animate-float" ref={(el) => { if(el) el.style.animationDelay = "1s"; }}>
            <span className="text-label-sm text-sentinel uppercase tracking-widest">🛡 Exposure Prevented</span>
            <p className="font-headline text-3xl font-bold mt-2">$2.3M</p>
          </div>
          <div className="col-span-2 surface-container-high rounded-lg p-5 flex items-center justify-between animate-float" ref={(el) => { if(el) el.style.animationDelay = "2s"; }}>
            <div>
              <p className="font-headline text-xl font-bold">12 RFQs Sent</p>
              <span className="text-label-sm text-secondary uppercase tracking-widest">Active Route Intelligence</span>
            </div>
          </div>
        </div>

        <div className="flex gap-6 text-label-sm text-secondary uppercase tracking-widest">
          <span>Precision Logic</span>
          <span>Kinetic Fortress v1.0</span>
          <span>© 2026</span>
        </div>
      </div>

      {/* Right form panel */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-md glass-panel rounded-xl p-10">
          <h2 className="font-headline text-headline-md font-bold mb-2">Welcome back</h2>
          <p className="text-body-md text-secondary mb-8">Sign in to your Praecantator workspace</p>

          <form onSubmit={(e) => e.preventDefault()} className="space-y-6">
            <div>
              <label className="text-label-sm uppercase tracking-widest text-secondary block mb-2">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
                className="input-sentinel w-full px-4 py-3 rounded-sm"
              />
            </div>

            <div>
              <label className="text-label-sm uppercase tracking-widest text-secondary block mb-2">Password</label>
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
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-secondary hover:text-foreground transition-colors"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-body-md text-secondary cursor-pointer">
                <input type="checkbox" className="w-4 h-4 rounded-sm bg-surface border-border accent-sentinel-red" />
                Remember node
              </label>
              <Link to="/forgot-password" className="text-body-md text-sentinel hover:underline">Reset credentials</Link>
            </div>

            <button
              type="submit"
              className="w-full bg-foreground text-background py-3 rounded-sm font-medium flex items-center justify-center gap-2 hover:opacity-90 transition-opacity"
            >
              Sign In <span>→</span>
            </button>
          </form>

          <div className="flex items-center gap-4 my-6">
            <div className="flex-1 h-px bg-border" />
            <span className="text-label-sm text-secondary uppercase tracking-widest">Or continue with</span>
            <div className="flex-1 h-px bg-border" />
          </div>

          <button className="w-full glass-panel py-3 rounded-sm font-medium flex items-center justify-center gap-3 hover:bg-white/10 transition-colors">
            <svg width="18" height="18" viewBox="0 0 18 18"><path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/><path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" fill="#34A853"/><path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/><path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335"/></svg>
            Google Sign-In
          </button>

          <p className="text-center text-body-md text-secondary mt-6">
            Access restricted to authorized personnel.
            <br />Protected by <span className="text-foreground font-medium">Praecantator Kinetic Fortress</span> protocols.
          </p>

          <p className="text-center text-body-md text-secondary mt-4">
            Don't have an account?{" "}
            <Link to="/register" className="text-sentinel hover:underline">Create one</Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
