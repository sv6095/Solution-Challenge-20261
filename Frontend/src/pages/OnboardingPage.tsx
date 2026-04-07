import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, Settings, ChevronLeft, Upload, Plus, X } from "lucide-react";

const steps = ["Company Profile", "Supplier Graph", "Alert Preferences"];

interface Supplier {
  name: string;
  country: string;
  category: string;
  tier: string;
}

const OnboardingPage = () => {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(0);
  const [companySize, setCompanySize] = useState("51-200");
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [newSupplier, setNewSupplier] = useState<Supplier>({ name: "", country: "", category: "", tier: "Tier 1" });

  const addSupplier = () => {
    if (newSupplier.name && newSupplier.country) {
      setSuppliers([...suppliers, newSupplier]);
      setNewSupplier({ name: "", country: "", category: "", tier: "Tier 1" });
    }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Navbar */}
      <nav className="h-14 flex items-center justify-between px-6 surface-container-low">
        <span className="font-headline text-sm font-bold text-sentinel">Praecantator</span>
        <div className="flex items-center gap-4">
          <span className="text-label-sm text-secondary uppercase tracking-widest">Onboarding Protocol v1.0</span>
          <Bell size={18} className="text-secondary" />
          <Settings size={18} className="text-secondary" />
        </div>
      </nav>

      {/* Progress bar */}
      <div className="flex items-center justify-center gap-4 py-8 max-w-2xl mx-auto">
        {steps.map((step, i) => (
          <div key={step} className="flex items-center gap-4">
            <div className="flex flex-col items-center gap-2">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center font-headline font-bold ${
                i <= currentStep ? "bg-sentinel text-background" : "bg-surface-highest text-secondary"
              }`}>
                {i + 1}
              </div>
              <span className={`text-label-sm uppercase tracking-widest ${
                i <= currentStep ? "text-sentinel" : "text-secondary"
              }`}>
                {step}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div className={`w-32 h-0.5 ${i < currentStep ? "bg-sentinel" : "bg-surface-highest"}`} />
            )}
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-[45%_55%] gap-0 min-h-[calc(100vh-10rem)]">
        {/* Left branding */}
        <div className="p-12 flex flex-col justify-center kinetic-gradient">
          <h1 className="text-display-lg leading-tight mb-6">
            Fortify Your <span className="text-sentinel">Infrastructure.</span>
          </h1>
          <p className="text-body-md text-secondary max-w-md mb-10">
            Complete the structural configuration to initialize the Kinetic Fortress. Your data will be processed through our neural risk mapping engine.
          </p>
          <div className="grid grid-cols-2 gap-4">
            <div className="surface-container-high rounded-lg p-5">
              <p className="font-headline text-2xl font-bold text-sentinel">99.9%</p>
              <p className="text-label-sm text-secondary uppercase tracking-widest">Uptime Monitoring</p>
            </div>
            <div className="surface-container-high rounded-lg p-5">
              <p className="font-headline text-2xl font-bold text-sentinel">ZERO</p>
              <p className="text-label-sm text-secondary uppercase tracking-widest">Latency Lag</p>
            </div>
          </div>
        </div>

        {/* Right form */}
        <div className="p-12 surface-container-low overflow-y-auto">
          {/* Step 1: Company Profile */}
          {currentStep === 0 && (
            <div className="space-y-6">
              <div>
                <h2 className="font-headline text-xl font-bold mb-1">Company Profile</h2>
                <p className="text-body-md text-secondary">Define your operational theater and scale.</p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-label-sm text-secondary uppercase tracking-widest block mb-2">Primary Industry</label>
                  <select aria-label="Primary Industry" className="input-sentinel w-full px-4 py-3 rounded-sm bg-surface">
                    <option>Aerospace & Defense</option>
                    <option>Manufacturing</option>
                    <option>Electronics</option>
                    <option>Pharma</option>
                    <option>Retail</option>
                    <option>Food & Beverage</option>
                  </select>
                </div>
                <div>
                  <label className="text-label-sm text-secondary uppercase tracking-widest block mb-2">Operational Region</label>
                  <select aria-label="Operational Region" className="input-sentinel w-full px-4 py-3 rounded-sm bg-surface">
                    <option>North America (EMEA)</option>
                    <option>Europe</option>
                    <option>Asia Pacific</option>
                    <option>Latin America</option>
                    <option>Middle East & Africa</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="text-label-sm text-secondary uppercase tracking-widest block mb-2">Company Size (Employee Count)</label>
                <div className="grid grid-cols-4 gap-2">
                  {["1-50", "51-200", "201-1000", "1000+"].map((size) => (
                    <button
                      key={size}
                      onClick={() => setCompanySize(size)}
                      className={`py-3 rounded-sm font-medium transition-colors ${
                        companySize === size ? "bg-sentinel text-background" : "glass-panel text-secondary hover:bg-white/10"
                      }`}
                    >
                      {size}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Step 2: Supplier Graph */}
          {currentStep === 1 && (
            <div className="space-y-6">
              <div>
                <h2 className="font-headline text-xl font-bold mb-1">Supplier Graph</h2>
                <p className="text-body-md text-secondary">Upload CSV or Add Manually to map dependencies.</p>
              </div>
              <div className="glass-panel rounded-lg p-8 text-center cursor-pointer hover:bg-white/10 transition-colors">
                <Upload size={32} className="mx-auto text-secondary mb-3" />
                <p className="text-body-md font-medium">Drop CSV file here or click to upload</p>
                <p className="text-label-sm text-secondary mt-1">Download template for correct formatting</p>
              </div>
              <div className="text-center text-label-sm text-secondary uppercase tracking-widest">— or add manually —</div>
              <div className="grid grid-cols-4 gap-3">
                <input placeholder="Supplier Name" value={newSupplier.name} onChange={(e) => setNewSupplier({ ...newSupplier, name: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm" />
                <input placeholder="Country" value={newSupplier.country} onChange={(e) => setNewSupplier({ ...newSupplier, country: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm" />
                <input placeholder="Category" value={newSupplier.category} onChange={(e) => setNewSupplier({ ...newSupplier, category: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm" />
                <button onClick={addSupplier} className="bg-sentinel text-background rounded-sm flex items-center justify-center gap-1 hover:opacity-90 transition-opacity">
                  <Plus size={16} /> Add
                </button>
              </div>
              {suppliers.length > 0 && (
                <div className="surface-container-high rounded-lg p-4">
                  <p className="text-label-sm text-secondary uppercase tracking-widest mb-3">{suppliers.length} suppliers added</p>
                  {suppliers.map((s, i) => (
                    <div key={i} className="flex items-center justify-between py-2">
                      <span className="text-body-md">{s.name} — {s.country}</span>
                      <button aria-label="Remove Supplier" onClick={() => setSuppliers(suppliers.filter((_, idx) => idx !== i))} className="text-secondary hover:text-sentinel">
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Step 3: Alert Preferences */}
          {currentStep === 2 && (
            <div className="space-y-6">
              <div>
                <h2 className="font-headline text-xl font-bold mb-1">Alert Preferences</h2>
                <p className="text-body-md text-secondary">Configure real-time intelligence channels.</p>
              </div>
              {["Email Alerts", "Push Notifications", "Slack Webhook"].map((a, i) => (
                <label key={a} className="flex items-center justify-between py-3 cursor-pointer">
                  <span className="text-body-md">{a}</span>
                  <div className={`w-9 h-5 rounded-full relative ${i < 2 ? "bg-sentinel" : "bg-surface-highest"}`}>
                    <div className={`w-4 h-4 rounded-full bg-foreground absolute top-0.5 transition-all ${i < 2 ? "left-4" : "left-0.5"}`} />
                  </div>
                </label>
              ))}
              <div>
                <label className="text-label-sm text-secondary uppercase tracking-widest block mb-2">Exposure Threshold</label>
                <input aria-label="Exposure Threshold" type="range" min="0" max="100" defaultValue="65" className="w-full accent-sentinel-red" />
                <p className="text-body-md text-secondary mt-1">Alert me when exposure score exceeds 65</p>
              </div>
            </div>
          )}

          {/* Navigation */}
          <div className="flex items-center justify-between mt-10 pt-6 border-t border-border">
            {currentStep > 0 ? (
              <button onClick={() => setCurrentStep(currentStep - 1)} className="flex items-center gap-2 text-body-md text-secondary hover:text-foreground transition-colors">
                <ChevronLeft size={16} /> Previous Step
              </button>
            ) : <div />}
            {currentStep < 2 ? (
              <button
                onClick={() => setCurrentStep(currentStep + 1)}
                className="bg-foreground text-background px-6 py-3 rounded-sm font-medium hover:opacity-90 transition-opacity"
              >
                Next Step →
              </button>
            ) : (
              <button
                onClick={() => navigate("/dashboard")}
                className="bg-sentinel text-background px-6 py-3 rounded-sm font-medium hover:opacity-90 transition-opacity"
              >
                Launch Praecantator
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default OnboardingPage;
