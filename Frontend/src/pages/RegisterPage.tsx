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
    <div className="min-h-screen flex bg-background">
      {/* Left branding */}
      <div className="hidden lg:flex lg:w-[45%] flex-col justify-between p-12 kinetic-gradient relative overflow-hidden">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-sentinel rounded-sm" />
          <span className="font-headline text-xl font-bold">Praecantator</span>
        </div>

        <div>
          <h1 className="text-display-lg leading-tight mb-6">
            Architecting <span className="text-sentinel">Kinetic Intelligence</span> for Global Trade.
          </h1>
          <p className="text-body-md text-secondary max-w-md">
            Praecantator provides an ironclad digital perimeter for your logistics network, utilizing real-time exposure scores and route intelligence.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="surface-container-high rounded-lg p-5">
            <span className="text-label-sm text-sentinel uppercase tracking-widest">📡 Signal Monitoring</span>
            <p className="font-headline text-3xl font-bold mt-2">99.98%</p>
            <p className="text-label-sm text-secondary uppercase tracking-widest">Uptime Reliability</p>
          </div>
          <div className="surface-container-high rounded-lg p-5">
            <span className="text-label-sm text-sentinel uppercase tracking-widest">🛡 Threat Mitigation</span>
            <p className="font-headline text-3xl font-bold mt-2 text-sentinel">Active</p>
            <p className="text-label-sm text-secondary uppercase tracking-widest">Global Sentinel Mode</p>
          </div>
        </div>

        <div className="flex gap-6 text-label-sm text-secondary uppercase tracking-widest">
          <span>Precision Logic</span>
          <span>Kinetic Fortress v1.0</span>
          <span>© 2026</span>
        </div>
      </div>

      {/* Right form */}
      <div className="flex-1 flex items-center justify-center p-8 overflow-y-auto">
        <div className="w-full max-w-md">
          <h2 className="font-headline text-headline-md font-bold mb-2">Create your workspace</h2>
          <p className="text-body-md text-secondary mb-8">Start protecting your supply chain in 15 minutes</p>

          <form onSubmit={onSubmit} className="space-y-5">
            {[
              { label: "Full Name", key: "fullName" as const, type: "text", placeholder: "Johnathan Sterling" },
              { label: "Company Name", key: "company" as const, type: "text", placeholder: "Sterling Logistics Corp" },
              { label: "Work Email", key: "email" as const, type: "email", placeholder: "j.sterling@praecantator.io" },
            ].map((field) => (
              <div key={field.key}>
                <label className="text-label-sm uppercase tracking-widest text-secondary block mb-2">{field.label}</label>
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
              <label className="text-label-sm uppercase tracking-widest text-secondary block mb-2">Password</label>
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
              <label className="text-label-sm uppercase tracking-widest text-secondary block mb-2">Confirm Password</label>
              <input
                type="password"
                value={form.confirmPassword}
                onChange={(e) => setForm({ ...form, confirmPassword: e.target.value })}
                placeholder="••••••••••••"
                className="input-sentinel w-full px-4 py-3 rounded-sm"
              />
            </div>

            <label className="flex items-start gap-3 text-body-md text-secondary cursor-pointer">
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

          <div className="flex items-center gap-4 my-6">
            <div className="flex-1 h-px bg-border" />
            <span className="text-label-sm text-secondary uppercase tracking-widest">Or authorize with</span>
            <div className="flex-1 h-px bg-border" />
          </div>

          <button className="w-full glass-panel py-3 rounded-sm font-medium flex items-center justify-center gap-3 hover:bg-white/10 transition-colors uppercase tracking-widest">
            🔐 Enterprise SSO
          </button>

          <p className="text-center text-body-md text-secondary mt-6">
            Already part of the network?{" "}
            <Link to="/login" className="text-sentinel hover:underline">Sign In to Sentinel</Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default RegisterPage;
