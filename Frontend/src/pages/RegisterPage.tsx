import { useState } from "react";
import { Link } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import { toast } from "@/components/ui/sonner";
import { api } from "@/lib/api";

const RegisterPage = () => {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    fullName: "", company: "", email: "", password: "", confirmPassword: "", agreed: false,
  });
  const [submitting, setSubmitting] = useState(false);

  const getStrength = (pw: string) => {
    if (pw.length < 6) return { label: "Weak", color: "bg-sentinel", width: "w-1/3" };
    if (pw.length < 10 || !/[!@#$%^&*]/.test(pw)) return { label: "Medium", color: "bg-yellow-500", width: "w-2/3" };
    return { label: "Strong", color: "bg-green-500", width: "w-full" };
  };
  const strength = getStrength(form.password);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.agreed) {
      toast.error("Please accept the Service Protocols to continue.");
      return;
    }
    if (!form.email || !form.password) {
      toast.error("Email and password are required.");
      return;
    }
    if (form.password !== form.confirmPassword) {
      toast.error("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      await api.auth.register({
        email: form.email.trim(),
        password: form.password,
        company_name: form.company,
        full_name: form.fullName,
      });
      toast.success("Account created. Please sign in.");
      navigate("/login");
    } catch (err) {
      toast.error("Registration failed. Email may already be registered.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-background font-headline">
      {/* Left branding */}
      <div className="hidden lg:flex lg:w-[45%] flex-col justify-between p-8 bg-sky-50 border-r border-sky-100 relative overflow-hidden">
        <div className="flex items-center gap-3 text-slate-900">
          <img src="/Praecantator.png" alt="Logo" className="w-10 h-10 object-contain" />
          <span className="font-headline text-xl font-bold">Praecantator</span>
        </div>

        <div className="-mt-8">
          <h1 className="text-display-lg leading-tight mb-4 text-slate-900">
            Architecting <span className="text-sentinel">Kinetic Intelligence</span> for Global Trade.
          </h1>
          <p className="text-body-md text-slate-600 max-w-md">
            Praecantator provides an ironclad digital perimeter for your logistics network, utilizing real-time exposure scores and route intelligence.
          </p>
        </div>

        <div className="flex gap-6 text-label-sm text-slate-500 uppercase tracking-widest">
          <span>Precision Logic</span>
          <span>Kinetic Fortress</span>
          <span>© 2026</span>
        </div>
      </div>

      {/* Right form */}
      <div className="flex-1 flex items-center justify-center p-8 overflow-y-auto">
        <div className="w-full max-w-md">
          <h2 className="font-headline text-headline-md font-bold text-slate-800 mb-1">Create your workspace</h2>
          <p className="text-body-md text-slate-600 mb-5">Start protecting your supply chain in 15 minutes</p>

          <form onSubmit={onSubmit} className="space-y-3">
            {[
              { label: "Full Name", key: "fullName" as const, type: "text", placeholder: "Johnathan Sterling" },
              { label: "Company Name", key: "company" as const, type: "text", placeholder: "Sterling Logistics Corp" },
              { label: "Work Email", key: "email" as const, type: "email", placeholder: "j.sterling@praecantator.io" },
            ].map((field) => (
              <div key={field.key}>
                <label className="text-label-sm uppercase tracking-widest text-slate-500 block mb-2">{field.label}</label>
                <input
                  type={field.type}
                  value={form[field.key]}
                  onChange={(e) => setForm({ ...form, [field.key]: e.target.value })}
                  placeholder={field.placeholder}
                  className="input-sentinel w-full px-4 py-3 rounded-sm"
                />
              </div>
            ))}

            <div>
              <label className="text-label-sm uppercase tracking-widest text-slate-500 block mb-2">Password</label>
              <input
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                placeholder="••••••••••••"
                className="input-sentinel w-full px-4 py-3 rounded-sm"
              />
              {form.password && (
                <div className="mt-2">
                  <div className="h-1 bg-surface-highest rounded-full overflow-hidden">
                    <div className={`h-full ${strength.color} ${strength.width} transition-all`} />
                  </div>
                  <p className="text-label-sm text-sentinel mt-1 uppercase tracking-widest">
                    Security Grade: {strength.label}. Add specialized characters for sentinel protection.
                  </p>
                </div>
              )}
            </div>

            <div>
              <label className="text-label-sm uppercase tracking-widest text-slate-500 block mb-2">Confirm Password</label>
              <input
                type="password"
                value={form.confirmPassword}
                onChange={(e) => setForm({ ...form, confirmPassword: e.target.value })}
                placeholder="••••••••••••"
                className="input-sentinel w-full px-4 py-3 rounded-sm"
              />
            </div>

            <label className="flex items-start gap-3 text-body-md text-slate-600 cursor-pointer mt-1">
              <input
                type="checkbox"
                checked={form.agreed}
                onChange={(e) => setForm({ ...form, agreed: e.target.checked })}
                className="w-4 h-4 mt-0.5 rounded-sm bg-surface border-border accent-sentinel-red"
              />
              <span>
                I acknowledge that by creating a workspace, I agree to the{" "}
                <a href="#" className="text-foreground underline">Service Protocols</a> and{" "}
                <a href="#" className="text-foreground underline">Data Residency Policies</a>.
              </span>
            </label>

            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-foreground text-background py-3 rounded-sm font-medium uppercase tracking-widest hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {submitting ? "Creating…" : "Create Account"}
            </button>
          </form>

          <div className="flex items-center gap-4 my-5">
            <div className="flex-1 h-px bg-border" />
            <span className="text-label-sm text-slate-500 uppercase tracking-widest">Or continue with</span>
            <div className="flex-1 h-px bg-border" />
          </div>

          <button className="w-full glass-panel py-3 rounded-sm font-medium flex items-center justify-center gap-3 hover:bg-slate-50 transition-colors">
            <svg width="18" height="18" viewBox="0 0 18 18"><path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/><path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" fill="#34A853"/><path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/><path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335"/></svg>
            Google Sign-In
          </button>

          <p className="text-center text-body-md text-slate-600 mt-5">
            Already part of the network?{" "}
            <Link to="/login" className="text-sentinel hover:underline">Sign In to Sentinel</Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default RegisterPage;
