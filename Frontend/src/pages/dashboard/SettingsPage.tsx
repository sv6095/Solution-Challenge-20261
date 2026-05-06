import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  User, Save, MapPin, Truck, ChevronDown, ChevronUp,
} from "lucide-react";
import OnboardingPage from "@/pages/OnboardingPage";

const BASE = (import.meta.env.VITE_API_URL ?? "/api").replace(/\/+$/, "");

import { getAccessToken, getUserId } from "@/lib/api";

function authHeaders(): HeadersInit {
  const token = getAccessToken();
  const userId = getUserId();
  return {
    "Content-Type": "application/json",
    "X-User-Id": userId,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const fetchProfile = () =>
  fetch(`${BASE}/settings/profile`, { headers: authHeaders() }).then((r) => r.json());
const SettingsPage = () => {
  const qc = useQueryClient();
  const { data: profile } = useQuery({ queryKey: ["settings-profile"], queryFn: fetchProfile });

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [dirty, setDirty] = useState(false);

  // Panel toggle states
  const [showOnboarding, setShowOnboarding] = useState(false);

  // Sync initial values when profile loads
  const loaded = !!profile;
  if (loaded && !dirty) {
    if (name !== (profile.name || "")) setName(profile.name || "");
    if (email !== (profile.email || "")) setEmail(profile.email || "");
    if (company !== (profile.company || "")) setCompany(profile.company || "");
    if (role !== (profile.role || "Admin")) setRole(profile.role || "Admin");
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      fetch(`${BASE}/settings/profile`, {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify({ name, email, company, role }),
      }).then((r) => r.json()),
    onSuccess: () => {
      setDirty(false);
      qc.invalidateQueries({ queryKey: ["settings-profile"] });
    },
  });

  const handleChange = (setter: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setter(e.target.value);
    setDirty(true);
  };

  return (
    <div className="h-[calc(100vh-120px)] flex flex-col min-h-0 bg-slate-50 text-slate-900">
      <div className="px-6 py-8 flex-1 overflow-y-auto custom-scrollbar">
        <h1 className="font-headline text-2xl font-bold tracking-tight uppercase mb-6">
          Settings
        </h1>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl">
          {/* ── Account ── */}
          <div className="border border-slate-200 bg-white p-6">
            <div className="flex items-center gap-3 mb-4">
              <User size={18} className="text-slate-500" />
              <h2 className="font-headline uppercase tracking-widest text-sm text-slate-500">Account</h2>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-[9px] font-headline uppercase tracking-widest text-slate-500 block mb-1">Name</label>
                <input
                  value={name}
                  onChange={handleChange(setName)}
                  className="w-full input-sentinel text-sm px-3 py-2"
                  placeholder="Operator name"
                />
              </div>
              <div>
                <label className="text-[9px] font-headline uppercase tracking-widest text-slate-500 block mb-1">Email *</label>
                <input
                  value={email}
                  onChange={handleChange(setEmail)}
                  className="w-full input-sentinel text-sm px-3 py-2"
                  placeholder="Email address"
                  type="email"
                  required
                />
              </div>
              <div>
                <label className="text-[9px] font-headline uppercase tracking-widest text-slate-500 block mb-1">Company</label>
                <input
                  value={company}
                  onChange={handleChange(setCompany)}
                  className="w-full input-sentinel text-sm px-3 py-2"
                  placeholder="Company name"
                />
              </div>
              <div>
                <label className="text-[9px] font-headline uppercase tracking-widest text-slate-500 block mb-1">Role</label>
                <input
                  value={role}
                  onChange={handleChange(setRole)}
                  className="w-full input-sentinel text-sm px-3 py-2"
                  placeholder="Role"
                />
              </div>
              {dirty && (
                <button
                  onClick={() => saveMutation.mutate()}
                  disabled={saveMutation.isPending}
                  className="flex items-center gap-2 px-4 py-2 bg-red-500 text-white text-xs font-headline uppercase tracking-widest hover:bg-red-500/80 transition-colors mt-2"
                >
                  <Save size={12} />
                  {saveMutation.isPending ? "Saving..." : "Save Profile"}
                </button>
              )}
            </div>
          </div>

        </div>

        {/* ── Supply Chain Configuration (Embedded Onboarding) ── */}
        <div className="max-w-4xl mt-8">
          <button
            onClick={() => setShowOnboarding(!showOnboarding)}
            className="w-full border border-slate-200 bg-white p-6 flex items-center justify-between hover:bg-slate-100 transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <MapPin size={18} className="text-red-500" />
                <Truck size={18} className="text-red-500" />
              </div>
              <div className="text-left">
                <h2 className="font-headline font-bold uppercase tracking-widest text-sm text-slate-600">
                  Supply Chain Configuration
                </h2>
                <p className="text-[10px] font-headline font-semibold text-slate-500 mt-1 uppercase tracking-wider">
                  Edit company profile, logistics nodes, and supplier relationships
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-headline font-bold text-red-500 uppercase tracking-widest">
                {showOnboarding ? "Collapse" : "Expand"}
              </span>
              {showOnboarding ? <ChevronUp size={16} className="text-red-500" /> : <ChevronDown size={16} className="text-red-500" />}
            </div>
          </button>

          {showOnboarding && (
            <div className="border border-t-0 border-border bg-surface">
              <OnboardingPage embedded returnTo="/dashboard/settings" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SettingsPage;
