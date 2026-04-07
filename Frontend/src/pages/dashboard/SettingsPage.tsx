import { useState } from "react";
import { Loader2 } from "lucide-react";
import { useProfile, useUpdateProfile, useBilling } from "@/hooks/use-dashboard";

const TABS = ["Profile", "Supplier Graph", "Integrations", "Alerts", "Billing"];

const SettingsPage = () => {
  const [activeTab, setActiveTab] = useState("profile");
  const [alertToggles, setAlertToggles] = useState<Record<string, boolean>>({
    "Email Alerts": true,
    "Push Notifications": true,
    "Slack Webhook": false,
  });
  const [exposureThreshold, setExposureThreshold] = useState(65);

  const { data: profile, isLoading: pLoading } = useProfile();
  const { data: billing, isLoading: bLoading } = useBilling();
  const updateProfile = useUpdateProfile();

  const [form, setForm] = useState({ name: "", email: "", company: "", role: "" });
  const [formInit, setFormInit] = useState(false);

  if (profile && !formInit) {
    setForm({ name: profile.name, email: profile.email, company: profile.company, role: profile.role });
    setFormInit(true);
  }

  return (
    <div>
      <h1 className="font-headline text-3xl font-bold tracking-tight-sentinel mb-8">Configuration Matrix</h1>

      <div className="flex gap-2 mb-8 flex-wrap">
        {TABS.map((t) => {
          const key = t.toLowerCase().replace(" ", "-");
          return (
            <button
              key={t}
              onClick={() => setActiveTab(key)}
              className={`px-4 py-2 rounded-sm text-body-md transition-colors ${activeTab === key ? "bg-sentinel text-background" : "glass-panel text-secondary hover:bg-white/10"}`}
            >
              {t}
            </button>
          );
        })}
      </div>

      <div className="surface-container-high rounded-lg p-8 max-w-2xl">
        {/* Profile */}
        {activeTab === "profile" && (
          <div className="space-y-6">
            <h2 className="font-headline text-xl font-bold mb-4">Operator Profile</h2>
            {pLoading ? (
              <div className="flex justify-center py-8"><Loader2 className="animate-spin text-secondary" /></div>
            ) : (
              <>
                {(["name", "email", "company", "role"] as const).map((field) => (
                  <div key={field}>
                    <label htmlFor={`settings-${field}`} className="text-label-sm text-secondary uppercase tracking-widest block mb-2">{field}</label>
                    <input
                      id={`settings-${field}`}
                      value={form[field]}
                      onChange={(e) => setForm((f) => ({ ...f, [field]: e.target.value }))}
                      className="input-sentinel w-full px-4 py-3 rounded-sm"
                    />
                  </div>
                ))}
                <button
                  onClick={() => updateProfile.mutate(form)}
                  disabled={updateProfile.isPending}
                  className="bg-foreground text-background px-6 py-3 rounded-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-40 flex items-center gap-2"
                >
                  {updateProfile.isPending ? <><Loader2 size={14} className="animate-spin" /> Saving…</> : "Save Changes"}
                </button>
                {updateProfile.isSuccess && <p className="text-green-400 text-body-md">Profile saved successfully.</p>}
              </>
            )}
          </div>
        )}

        {/* Alerts */}
        {activeTab === "alerts" && (
          <div className="space-y-6">
            <h2 className="font-headline text-xl font-bold mb-4">Alert Configuration</h2>
            {Object.entries(alertToggles).map(([label, on]) => (
              <label key={label} className="flex items-center justify-between py-3 cursor-pointer">
                <span className="text-body-md">{label}</span>
                <button
                  type="button"
                  data-state={on ? "checked" : "unchecked"}
                  onClick={() => setAlertToggles((t) => ({ ...t, [label]: !t[label] }))}
                  className={`w-9 h-5 rounded-full relative transition-colors ${on ? "bg-sentinel" : "bg-surface-highest"}`}
                >
                  <div className={`w-4 h-4 rounded-full bg-foreground absolute top-0.5 transition-all ${on ? "left-4" : "left-0.5"}`} />
                </button>
              </label>
            ))}
            <div>
              <label htmlFor="exposure-threshold" className="text-label-sm text-secondary uppercase tracking-widest block mb-2">
                Exposure Threshold: <span className="text-foreground font-bold">{exposureThreshold}</span>
              </label>
              <input
                id="exposure-threshold"
                type="range"
                min="0"
                max="100"
                value={exposureThreshold}
                onChange={(e) => setExposureThreshold(Number(e.target.value))}
                className="w-full accent-sentinel-red"
              />
              <div className="flex justify-between text-label-sm text-secondary mt-1">
                <span>0</span><span>100</span>
              </div>
            </div>
          </div>
        )}

        {/* Billing */}
        {activeTab === "billing" && (
          <div className="space-y-6">
            <h2 className="font-headline text-xl font-bold mb-4">Deployment Tier</h2>
            {bLoading ? (
              <div className="flex justify-center py-8"><Loader2 className="animate-spin text-secondary" /></div>
            ) : billing ? (
              <>
                <div className="glass-panel rounded-lg p-6 flex items-center justify-between">
                  <div>
                    <span className="bg-sentinel/20 text-sentinel px-3 py-1 rounded-sm text-label-sm font-bold uppercase">{billing.plan}</span>
                    <p className="font-headline text-2xl font-bold mt-2">
                      ${billing.monthlyRate.toLocaleString()}<span className="text-body-md text-secondary">/mo</span>
                    </p>
                  </div>
                  <button className="glass-panel px-4 py-2 rounded-sm text-body-md hover:bg-white/10 transition-colors">Upgrade Plan</button>
                </div>
                <div className="grid grid-cols-3 gap-4">
                  <div className="surface-container rounded-lg p-4">
                    <p className="text-label-sm text-secondary uppercase tracking-widest">Workflow Runs</p>
                    <p className="font-headline text-xl font-bold mt-1">
                      {billing.workflowRunsUsed} <span className="text-body-md text-secondary">/ {billing.workflowRunsLimit === -1 ? "∞" : billing.workflowRunsLimit}</span>
                    </p>
                  </div>
                  <div className="surface-container rounded-lg p-4">
                    <p className="text-label-sm text-secondary uppercase tracking-widest">RFQs Sent</p>
                    <p className="font-headline text-xl font-bold mt-1">{billing.rfqsSent} <span className="text-body-md text-secondary">/ ∞</span></p>
                  </div>
                  <div className="surface-container rounded-lg p-4">
                    <p className="text-label-sm text-secondary uppercase tracking-widest">Suppliers</p>
                    <p className="font-headline text-xl font-bold mt-1">
                      {billing.suppliersUsed} <span className="text-body-md text-secondary">/ {billing.suppliersLimit}</span>
                    </p>
                  </div>
                </div>
              </>
            ) : null}
          </div>
        )}

        {!["profile", "alerts", "billing"].includes(activeTab) && (
          <div className="text-center py-12">
            <p className="text-secondary text-body-md">Configuration module loading…</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default SettingsPage;
