import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, Settings, ChevronLeft, Upload, Plus, X } from "lucide-react";
import { toast } from "@/components/ui/sonner";
import { api, getUserId } from "@/lib/api";
import { useSearchParams } from "react-router-dom";

const steps = ["Company Profile", "Logistics Nodes", "Supplier Relationships"];

interface LogisticsNode {
  name: string;
  type: string;
  address: string;
  tier: string;
  modes: { sea: boolean; air: boolean; land: boolean };
  lat?: number;
  lng?: number;
  dunsNumber?: string;
  dailyThroughputUsd: string;
  safetyStockDays: string;
  criticalThresholdPct: string;
}

interface SupplierRel {
  name: string;
  email: string;
  products: string;
  originNodes: string;
  slaDays: string;
  backup: boolean;
  incoterm: string;
  country: string;
  category: string;
  tier: string;
  dunsNumber?: string;
}

type Props = {
  embedded?: boolean;
  returnTo?: string;
};

const OnboardingPage = (props: Props) => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const embedded = props.embedded ?? searchParams.get("embedded") === "1";
  const returnTo = (props.returnTo ?? searchParams.get("returnTo")) || "/dashboard";
  const [currentStep, setCurrentStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);

  // Step 1
  const [companyName, setCompanyName] = useState("");
  const [industry, setIndustry] = useState("Manufacturing");
  const [region, setRegion] = useState("Asia Pacific");
  const [companySize, setCompanySize] = useState("51-200");
  const [primaryContactName, setPrimaryContactName] = useState("");
  const [primaryContactEmail, setPrimaryContactEmail] = useState("");

  // Step 2
  const [nodes, setNodes] = useState<LogisticsNode[]>([]);
  const [newNode, setNewNode] = useState<LogisticsNode>({
    name: "",
    type: "factory",
    address: "",
    tier: "Tier 1",
    modes: { sea: true, air: true, land: true },
    dailyThroughputUsd: "",
    safetyStockDays: "",
    criticalThresholdPct: "60",
  });

  // Step 3
  const [suppliers, setSuppliers] = useState<SupplierRel[]>([]);
  const [newSupplier, setNewSupplier] = useState<SupplierRel>({
    name: "",
    email: "",
    products: "",
    originNodes: "",
    slaDays: "",
    backup: false,
    incoterm: "FOB",
    country: "",
    category: "",
    tier: "Tier 1",
  });

  const userId = useMemo(() => getUserId(), []);
  const [prefilled, setPrefilled] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<string>("");
  const [registrationLoaded, setRegistrationLoaded] = useState(false);

  // ── Auto-populate from registration data ──
  useEffect(() => {
    if (registrationLoaded) return;
    api.auth
      .profile(userId)
      .then((reg) => {
        // Only set if not already filled by context
        if (!companyName && reg.company_name) setCompanyName(reg.company_name);
        if (!primaryContactName && reg.full_name) setPrimaryContactName(reg.full_name);
        if (!primaryContactEmail && reg.email) setPrimaryContactEmail(reg.email);
      })
      .catch(() => {
        // Profile endpoint may not exist for legacy users — that's fine
      })
      .finally(() => setRegistrationLoaded(true));
  }, [registrationLoaded, userId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Load existing onboarding context (edit mode / re-visit) ──
  useEffect(() => {
    if (prefilled) return;
    api.contexts
      .get(userId)
      .then((res) => {
        const ctx = (res.context ?? {}) as Record<string, unknown>;
        if (ctx.company_name) setCompanyName(String(ctx.company_name));
        if (ctx.industry) setIndustry(String(ctx.industry));
        if (ctx.region) setRegion(String(ctx.region));
        if (ctx.primary_contact_name) setPrimaryContactName(String(ctx.primary_contact_name));
        if (ctx.primary_contact_email) setPrimaryContactEmail(String(ctx.primary_contact_email));
        if (ctx.company_size) setCompanySize(String(ctx.company_size));
        if (Array.isArray(ctx.logistics_nodes) && ctx.logistics_nodes.length) {
          setNodes(
            (ctx.logistics_nodes as Record<string, unknown>[]).map((n) => ({
              name: String(n.name ?? ""),
              type: String(n.node_type ?? n.type ?? "factory"),
              address: String(n.address ?? ""),
              tier: String(n.tier ?? "Tier 1"),
              modes: (n.transport_modes ?? n.modes ?? { sea: true, air: true, land: true }) as LogisticsNode["modes"],
              lat: typeof n.lat === "number" ? n.lat : undefined,
              lng: typeof n.lng === "number" ? n.lng : undefined,
              dailyThroughputUsd: String(n.daily_throughput_usd ?? ""),
              safetyStockDays: String(n.safety_stock_days ?? ""),
              criticalThresholdPct: String(n.critical_threshold_pct ?? "60"),
            })),
          );
        }
        if (Array.isArray(ctx.suppliers) && ctx.suppliers.length) {
          setSuppliers(
            (ctx.suppliers as Record<string, unknown>[]).map((s) => ({
              name: String(s.name ?? ""),
              email: String(s.email ?? ""),
              products: String(s.products ?? ""),
              originNodes: String(s.origin_nodes ?? ""),
              slaDays: String(s.contract_sla_days ?? ""),
              backup: Boolean(s.backup_supplier ?? false),
              incoterm: String(s.incoterm ?? "FOB"),
              country: String(s.country ?? ""),
              category: String(s.category ?? ""),
              tier: String(s.tier ?? "Tier 1"),
            })),
          );
        }
      })
      .finally(() => setPrefilled(true));
  }, [prefilled, userId]);

  const geocodePlace = async (query: string) => {
    try {
      const response = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=1`,
      );
      const data = (await response.json()) as Array<{ lat: string; lon: string }>;
      if (!data?.length) return null;
      return { lat: Number(data[0].lat), lng: Number(data[0].lon) };
    } catch {
      return null;
    }
  };

  const addNode = () => {
    if (!newNode.name.trim() || !newNode.address.trim()) {
      toast.error("Node name and address are required.");
      return;
    }
    if (newNode.lat !== undefined && newNode.lng !== undefined) {
      setNodes((prev) => [...prev, newNode]);
    } else {
      geocodePlace(newNode.address).then((geo) => {
        if (!geo) toast.warning("Could not auto-fetch coordinates. Added without them.");
        setNodes((prev) => [...prev, geo ? { ...newNode, ...geo } : newNode]);
      });
    }
    setNewNode({
      name: "",
      type: "factory",
      address: "",
      tier: "Tier 1",
      modes: { sea: true, air: true, land: true },
      lat: undefined,
      lng: undefined,
      dailyThroughputUsd: "",
      safetyStockDays: "",
      criticalThresholdPct: "60",
    });
  };

  const addSupplier = () => {
    if (!newSupplier.name.trim() || !newSupplier.country.trim()) {
      toast.error("Supplier name and country are required.");
      return;
    }
    if (!newSupplier.email.trim()) {
      toast.error("Supplier email is required.");
      return;
    }
    setSuppliers((prev) => [...prev, newSupplier]);
    setNewSupplier({
      name: "",
      email: "",
      products: "",
      originNodes: "",
      slaDays: "",
      backup: false,
      incoterm: "FOB",
      country: "",
      category: "",
      tier: "Tier 1",
    });
  };

  const parseCsv = async (file: File) => {
    const text = await file.text();
    const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    if (lines.length < 2) return { headers: [], rows: [] as string[][] };
    const headers = lines[0].split(",").map((h) => h.trim());
    const rows = lines.slice(1).map((l) => l.split(",").map((v) => v.trim()));
    return { headers, rows };
  };

  const onNodesCsv = async (file: File | null) => {
    if (!file) return;
    try {
      const { headers, rows } = await parseCsv(file);
      const idx = (name: string) => headers.findIndex((h) => h.toLowerCase() === name.toLowerCase());
      const nameI = idx("node_name");
      const typeI = idx("node_type");
      const addressI = idx("address");
      const tierI = idx("tier");
      const throughputI = idx("daily_throughput_usd");
      const safetyI = idx("safety_stock_days");
      const thresholdI = idx("critical_threshold_pct");
      if (nameI < 0 || addressI < 0) {
        toast.error("CSV must include headers: node_name,address (optional: node_type,tier,daily_throughput_usd,safety_stock_days,critical_threshold_pct)");
        return;
      }
      const parsed: LogisticsNode[] = rows
        .map((r) => ({
          name: r[nameI] || "",
          type: typeI >= 0 ? (r[typeI] || "factory") : "factory",
          address: r[addressI] || "",
          tier: tierI >= 0 ? (r[tierI] || "Tier 1") : "Tier 1",
          modes: { sea: true, air: true, land: true },
          lat: undefined,
          lng: undefined,
          dailyThroughputUsd: throughputI >= 0 ? (r[throughputI] || "") : "",
          safetyStockDays: safetyI >= 0 ? (r[safetyI] || "") : "",
          criticalThresholdPct: thresholdI >= 0 ? (r[thresholdI] || "60") : "60",
        }))
        .filter((n) => n.name && n.address);
      // Best-effort geocode first 10 imported nodes (keeps demo snappy).
      const firstBatch = parsed.slice(0, 10);
      for (const n of firstBatch) {
        const geo = await geocodePlace(n.address);
        if (geo) {
          n.lat = geo.lat;
          n.lng = geo.lng;
        }
      }
      setNodes((prev) => [...prev, ...parsed]);
      toast.success(`Imported ${parsed.length} nodes.`);
    } catch {
      toast.error("Failed to parse nodes CSV.");
    }
  };

  const onSuppliersCsv = async (file: File | null) => {
    if (!file) return;
    try {
      const { headers, rows } = await parseCsv(file);
      const idx = (name: string) => headers.findIndex((h) => h.toLowerCase() === name.toLowerCase());
      const nameI = idx("supplier_name");
      const countryI = idx("country");
      const emailI = idx("email");
      const productsI = idx("products");
      const categoryI = idx("category");
      const tierI = idx("tier");
      const slaI = idx("sla_days");
      if (nameI < 0 || countryI < 0) {
        toast.error("CSV must include headers: supplier_name,country (optional: email,products,category,tier,sla_days)");
        return;
      }
      const parsed: SupplierRel[] = rows
        .map((r) => ({
          name: r[nameI] || "",
          country: r[countryI] || "",
          email: emailI >= 0 ? (r[emailI] || "") : "",
          products: productsI >= 0 ? (r[productsI] || "") : "",
          originNodes: "",
          slaDays: slaI >= 0 ? (r[slaI] || "") : "",
          backup: false,
          incoterm: "FOB",
          category: categoryI >= 0 ? (r[categoryI] || "") : "",
          tier: tierI >= 0 ? (r[tierI] || "Tier 1") : "Tier 1",
        }))
        .filter((s) => s.name && s.country);
      setSuppliers((prev) => [...prev, ...parsed]);
      toast.success(`Imported ${parsed.length} suppliers.`);
    } catch {
      toast.error("Failed to parse suppliers CSV.");
    }
  };

  const launch = async () => {
    if (!companyName.trim()) {
      toast.error("Company name is required.");
      setCurrentStep(0);
      return;
    }
    if (!primaryContactEmail.trim()) {
      toast.error("Primary contact email is required.");
      setCurrentStep(0);
      return;
    }
    if (nodes.length === 0) {
      toast.error("Add at least 1 logistics node.");
      setCurrentStep(1);
      return;
    }
    if (suppliers.length === 0) {
      toast.error("Add at least 1 supplier.");
      setCurrentStep(2);
      return;
    }
    // Validate all suppliers have email
    const missingEmails = suppliers.filter((s) => !s.email.trim());
    if (missingEmails.length > 0) {
      toast.error(`${missingEmails.length} supplier(s) missing email. All suppliers require an email address.`);
      setCurrentStep(2);
      return;
    }
    setSubmitting(true);
    try {
      await api.onboarding.complete({
        user_id: userId,
        company_name: companyName,
        industry,
        region,
        primary_contact_name: primaryContactName,
        primary_contact_email: primaryContactEmail,
        company_size: companySize,
        logistics_nodes: nodes.map((n) => ({
          name: n.name,
          node_type: n.type,
          address: n.address,
          tier: n.tier,
          lat: n.lat,
          lng: n.lng,
          transport_modes: n.modes,
          daily_throughput_usd: n.dailyThroughputUsd,
          safety_stock_days: n.safetyStockDays,
          critical_threshold_pct: n.criticalThresholdPct,
        })),
        suppliers: suppliers.map((s, idx) => ({
          id: s.dunsNumber || `sup_${idx + 1}`,
          supplier_id: s.dunsNumber || `sup_${idx + 1}`,
          name: s.name,
          email: s.email,
          city: "",
          country: s.country,
          tier: s.tier,
          transport_mode: "mixed",
          category: s.category || "General",
          products: s.products,
          origin_nodes: s.originNodes,
          contract_sla_days: s.slaDays,
          backup_supplier: s.backup,
          incoterm: s.incoterm,
          lat: 0.0,
          lng: 0.0,
        })),
        backup_suppliers: suppliers.filter((s) => s.backup).map((s) => ({ name: s.name, email: s.email, city: "", country: s.country, category: s.category })),
        alert_threshold: 60,
        transport_preferences: { sea: true, air: true, land: true },
        gmail_oauth_token: null,
        slack_webhook: null,
      });
      toast.success("Onboarding complete.");
      setLastSavedAt(new Date().toISOString());
      if (embedded) {
        // In embedded mode we stay on the same page; force a refresh from persisted context
        // so users can immediately see that the save actually stuck.
        setPrefilled(false);
        setCurrentStep(0);
        return;
      }
      navigate(returnTo);
    } catch {
      toast.error("Failed to save onboarding.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={embedded ? "bg-slate-50 font-headline" : "min-h-screen bg-slate-50 font-headline"}>
      {/* Navbar */}
      {!embedded && (
        <nav className="h-14 flex items-center justify-between px-6 bg-white border-b border-slate-200">
          <div className="flex items-center gap-3">
            <img src="/Praecantator.png" alt="Logo" className="w-8 h-8 object-contain" />
            <span className="font-headline text-xl font-bold text-red-500">Praecantator</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-label-sm text-slate-500 uppercase tracking-widest">Onboarding Protocol</span>
            <Bell size={18} className="text-slate-500" />
            <Settings size={18} className="text-slate-500" />
          </div>
        </nav>
      )}

      {/* Progress bar */}
      <div className="flex items-center justify-center gap-4 py-8 max-w-2xl mx-auto">
        {steps.map((step, i) => (
          <div key={step} className="flex items-center gap-4">
            <div className="flex flex-col items-center gap-2">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center font-headline font-bold ${
                i <= currentStep ? "bg-red-500 text-white" : "bg-slate-100 text-slate-500"
              }`}>
                {i + 1}
              </div>
              <span className={`text-label-sm uppercase tracking-widest ${
                i <= currentStep ? "text-red-500" : "text-slate-500"
              }`}>
                {step}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div className={`w-32 h-0.5 ${i < currentStep ? "bg-red-500" : "bg-slate-100"}`} />
            )}
          </div>
        ))}
      </div>

      {embedded && lastSavedAt ? (
        <div className="max-w-2xl mx-auto -mt-2 mb-4 text-label-sm text-slate-500 uppercase tracking-widest">
          Saved: <span className="text-red-500">{lastSavedAt}</span>
        </div>
      ) : null}

      <div className={embedded ? "grid lg:grid-cols-1 gap-0" : "grid lg:grid-cols-[45%_55%] gap-0 min-h-[calc(100vh-10rem)]"}>
        {/* Left branding */}
        {!embedded && (
        <div className="p-12 flex flex-col justify-center bg-sky-50 border-r border-sky-100">
          <h1 className="text-display-lg leading-tight mb-6 text-slate-900">
            Fortify Your <span className="text-sentinel">Infrastructure.</span>
          </h1>
          <p className="text-body-md text-slate-600 max-w-md mb-10">
            Complete the structural configuration to initialize the Kinetic Fortress. Your data will be processed through our neural risk mapping engine.
          </p>
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-white border border-sky-100 rounded-lg p-5 shadow-sm">
              <p className="font-headline text-2xl font-bold text-sentinel">99.9%</p>
              <p className="text-label-sm text-slate-500 uppercase tracking-widest">Uptime Monitoring</p>
            </div>
            <div className="bg-white border border-sky-100 rounded-lg p-5 shadow-sm">
              <p className="font-headline text-2xl font-bold text-sentinel">ZERO</p>
              <p className="text-label-sm text-slate-500 uppercase tracking-widest">Latency Lag</p>
            </div>
          </div>
        </div>
        )}

        {/* Right form */}
        <div className="p-12 bg-white border-b border-slate-200 overflow-y-auto">
          {/* Step 1: Company Profile */}
          {currentStep === 0 && (
            <div className="space-y-6">
              <div>
                <h2 className="font-headline text-xl font-bold mb-1">Company Profile</h2>
                <p className="text-body-md text-slate-500">Define your operational theater and scale.</p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="text-label-sm text-slate-500 uppercase tracking-widest block mb-2">Company name *</label>
                  <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} className="input-sentinel w-full px-4 py-3 rounded-sm" placeholder="Acme Manufacturing" required />
                </div>
                <div>
                  <label className="text-label-sm text-slate-500 uppercase tracking-widest block mb-2">Primary contact name</label>
                  <input value={primaryContactName} onChange={(e) => setPrimaryContactName(e.target.value)} className="input-sentinel w-full px-4 py-3 rounded-sm" placeholder="Jane Doe" />
                  {primaryContactName && (
                    <p className="text-[9px] font-headline font-semibold text-red-500 mt-1 opacity-60 uppercase tracking-widest">Auto-filled from registration</p>
                  )}
                </div>
                <div>
                  <label className="text-label-sm text-slate-500 uppercase tracking-widest block mb-2">Primary contact email *</label>
                  <input value={primaryContactEmail} onChange={(e) => setPrimaryContactEmail(e.target.value)} className="input-sentinel w-full px-4 py-3 rounded-sm" placeholder="jane@acme.com" type="email" required />
                  {primaryContactEmail && (
                    <p className="text-[9px] font-headline font-semibold text-red-500 mt-1 opacity-60 uppercase tracking-widest">Auto-filled from registration</p>
                  )}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-label-sm text-slate-500 uppercase tracking-widest block mb-2">Primary Industry</label>
                  <select value={industry} onChange={(e) => setIndustry(e.target.value)} aria-label="Primary Industry" className="input-sentinel w-full px-4 py-3 rounded-sm bg-surface">
                    <option>Manufacturing</option>
                    <option>Pharma</option>
                    <option>Electronics</option>
                    <option>Food &amp; Beverage</option>
                    <option>Retail</option>
                    <option>Other</option>
                  </select>
                </div>
                <div>
                  <label className="text-label-sm text-slate-500 uppercase tracking-widest block mb-2">Operational Region</label>
                  <select value={region} onChange={(e) => setRegion(e.target.value)} aria-label="Operational Region" className="input-sentinel w-full px-4 py-3 rounded-sm bg-surface">
                    <option>Asia Pacific</option>
                    <option>Europe</option>
                    <option>North America</option>
                    <option>Latin America</option>
                    <option>Middle East &amp; Africa</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="text-label-sm text-slate-500 uppercase tracking-widest block mb-2">Company Size (Employee Count)</label>
                <div className="grid grid-cols-4 gap-2">
                  {["1-50", "51-200", "201-1000", "1000+"].map((size) => (
                    <button
                      key={size}
                      onClick={() => setCompanySize(size)}
                      className={`py-3 rounded-sm font-medium transition-colors ${
                        companySize === size ? "bg-red-500 text-white" : "border border-slate-200 bg-white text-slate-500 hover:bg-white/10"
                      }`}
                    >
                      {size}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Step 2: Logistics Nodes — ALL fields exposed */}
          {currentStep === 1 && (
            <div className="space-y-6">
              <div>
                <h2 className="font-headline text-xl font-bold mb-1">Logistics Nodes</h2>
                <p className="text-body-md text-slate-500">Define origin locations (factories, ports, warehouses) with full operational parameters.</p>
              </div>
              <label className="border border-slate-200 bg-white rounded-lg p-8 text-center cursor-pointer hover:bg-white/10 transition-colors block">
                <Upload size={32} className="mx-auto text-slate-500 mb-3" />
                <p className="text-body-md font-medium">Import nodes CSV</p>
                <p className="text-label-sm text-slate-500 mt-1">Headers: node_name,address (optional: node_type,tier,daily_throughput_usd,safety_stock_days,critical_threshold_pct)</p>
                <input type="file" accept=".csv" className="hidden" onChange={(e) => onNodesCsv(e.target.files?.[0] ?? null)} />
              </label>
              <div className="text-center text-label-sm text-slate-500 uppercase tracking-widest">— or add manually —</div>

              {/* Row 1: Name, Type, Address */}
              <div className="grid grid-cols-4 gap-3">
                <input placeholder="Node name *" value={newNode.name} onChange={(e) => setNewNode({ ...newNode, name: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm" />
                <select value={newNode.type} onChange={(e) => setNewNode({ ...newNode, type: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm bg-surface" aria-label="Node type">
                  <option value="factory">Factory</option>
                  <option value="port">Port</option>
                  <option value="warehouse">Warehouse</option>
                  <option value="distribution_center">Distribution Center</option>
                  <option value="airport">Airport</option>
                  <option value="hub">Hub</option>
                </select>
                <input placeholder="Address *" value={newNode.address} onChange={(e) => setNewNode({ ...newNode, address: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm col-span-2" />
              </div>

              {/* Row 1.5: Geo Coordinates & Entity ID */}
              <div className="grid grid-cols-4 gap-3">
                <input placeholder="Latitude (optional)" value={newNode.lat ?? ""} onChange={(e) => setNewNode({ ...newNode, lat: e.target.value ? parseFloat(e.target.value) : undefined })} className="input-sentinel px-3 py-2 rounded-sm" type="number" step="0.0001" />
                <input placeholder="Longitude (optional)" value={newNode.lng ?? ""} onChange={(e) => setNewNode({ ...newNode, lng: e.target.value ? parseFloat(e.target.value) : undefined })} className="input-sentinel px-3 py-2 rounded-sm" type="number" step="0.0001" />
                <input placeholder="DUNS / LEI Number (optional)" value={newNode.dunsNumber ?? ""} onChange={(e) => setNewNode({ ...newNode, dunsNumber: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm col-span-2" />
              </div>

              {/* Row 2: Tier, Throughput, Safety Stock, Threshold */}
              <div className="grid grid-cols-4 gap-3">
                <select value={newNode.tier} onChange={(e) => setNewNode({ ...newNode, tier: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm bg-surface" aria-label="Node tier">
                  <option>Tier 1</option>
                  <option>Tier 2</option>
                  <option>Tier 3</option>
                </select>
                <input placeholder="Daily throughput (USD)" value={newNode.dailyThroughputUsd} onChange={(e) => setNewNode({ ...newNode, dailyThroughputUsd: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm" type="number" />
                <input placeholder="Safety stock (days)" value={newNode.safetyStockDays} onChange={(e) => setNewNode({ ...newNode, safetyStockDays: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm" type="number" />
                <input placeholder="Critical threshold (%)" value={newNode.criticalThresholdPct} onChange={(e) => setNewNode({ ...newNode, criticalThresholdPct: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm" type="number" />
              </div>

              {/* Row 3: Transport Modes + Add button */}
              <div className="flex items-center gap-4">
                <span className="text-label-sm text-slate-500 uppercase tracking-widest shrink-0">Transport Modes:</span>
                {(["sea", "air", "land"] as const).map((mode) => (
                  <label key={mode} className="flex items-center gap-1.5 text-body-md text-slate-500 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={newNode.modes[mode]}
                      onChange={(e) => setNewNode({ ...newNode, modes: { ...newNode.modes, [mode]: e.target.checked } })}
                      className="w-4 h-4 rounded-sm bg-surface border-slate-200 bg-red-50"
                    />
                    {mode.charAt(0).toUpperCase() + mode.slice(1)}
                  </label>
                ))}
                <button onClick={addNode} className="ml-auto bg-red-500 text-white rounded-sm flex items-center justify-center gap-1 hover:opacity-90 transition-opacity px-4 py-2">
                  <Plus size={16} /> Add Node
                </button>
              </div>

              {nodes.length > 0 && (
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                  <p className="text-label-sm text-slate-500 uppercase tracking-widest mb-3">{nodes.length} nodes added</p>
                  {nodes.map((n, i) => (
                    <div key={i} className="flex items-center justify-between py-2 border-b border-slate-200 last:border-0">
                      <div className="flex flex-col">
                        <span className="text-body-md">{n.name} — <span className="text-slate-500">{n.type}</span></span>
                        <span className="text-[10px] font-headline font-medium text-slate-500 mt-1 leading-relaxed">
                          {n.tier} · {n.address} {n.lat && n.lng ? `(${n.lat.toFixed(4)}, ${n.lng.toFixed(4)})` : "(No Coords)"}
                          {n.dunsNumber && ` · DUNS: ${n.dunsNumber}`}
                          {n.dailyThroughputUsd && ` · $${Number(n.dailyThroughputUsd).toLocaleString()}/day`}
                          {n.safetyStockDays && ` · ${n.safetyStockDays}d safety stock`}
                          {` · Threshold: ${n.criticalThresholdPct}%`}
                          {` · Modes: ${Object.entries(n.modes).filter(([,v]) => v).map(([k]) => k).join(", ")}`}
                        </span>
                      </div>
                      <button aria-label="Remove Node" onClick={() => setNodes(nodes.filter((_, idx) => idx !== i))} className="text-slate-500 hover:text-red-500">
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Step 3: Supplier Relationships — email REQUIRED */}
          {currentStep === 2 && (
            <div className="space-y-6">
              <div>
                <h2 className="font-headline text-xl font-bold mb-1">Supplier Relationships</h2>
                <p className="text-body-md text-slate-500">Add supplier contacts and relationships (used for RFQs). Email is required for all suppliers.</p>
              </div>
              <label className="border border-slate-200 bg-white rounded-lg p-8 text-center cursor-pointer hover:bg-white/10 transition-colors block">
                <Upload size={32} className="mx-auto text-slate-500 mb-3" />
                <p className="text-body-md font-medium">Import suppliers CSV</p>
                <p className="text-label-sm text-slate-500 mt-1">Headers: supplier_name,country (optional: email,products,category,tier,sla_days)</p>
                <input type="file" accept=".csv" className="hidden" onChange={(e) => onSuppliersCsv(e.target.files?.[0] ?? null)} />
              </label>

              <div className="text-center text-label-sm text-slate-500 uppercase tracking-widest">— or add manually —</div>

              {/* Row 1: Core fields */}
              <div className="grid grid-cols-3 gap-3">
                <input placeholder="Supplier name *" value={newSupplier.name} onChange={(e) => setNewSupplier({ ...newSupplier, name: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm" />
                <input placeholder="Country *" value={newSupplier.country} onChange={(e) => setNewSupplier({ ...newSupplier, country: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm" />
                <input placeholder="Email *" value={newSupplier.email} onChange={(e) => setNewSupplier({ ...newSupplier, email: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm" type="email" required />
              </div>

              {/* Row 2: Products, Category, Tier */}
              <div className="grid grid-cols-3 gap-3">
                <input placeholder="Products/categories" value={newSupplier.products} onChange={(e) => setNewSupplier({ ...newSupplier, products: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm" />
                <input placeholder="Category" value={newSupplier.category} onChange={(e) => setNewSupplier({ ...newSupplier, category: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm" />
                <select value={newSupplier.tier} onChange={(e) => setNewSupplier({ ...newSupplier, tier: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm bg-surface" aria-label="Supplier tier">
                  <option>Tier 1</option>
                  <option>Tier 2</option>
                  <option>Tier 3</option>
                </select>
              </div>

              {/* Row 3: Origin, SLA, Incoterm */}
              <div className="grid grid-cols-3 gap-3">
                <input placeholder="Origin node(s)" value={newSupplier.originNodes} onChange={(e) => setNewSupplier({ ...newSupplier, originNodes: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm" />
                <input placeholder="SLA days" value={newSupplier.slaDays} onChange={(e) => setNewSupplier({ ...newSupplier, slaDays: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm" type="number" />
                <select aria-label="Incoterm" value={newSupplier.incoterm} onChange={(e) => setNewSupplier({ ...newSupplier, incoterm: e.target.value })} className="input-sentinel px-3 py-2 rounded-sm bg-surface">
                  {["EXW", "FOB", "CIF", "DDP"].map((v) => <option key={v}>{v}</option>)}
                </select>
              </div>

              {/* Row 4: Backup + Add */}
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 text-body-md text-slate-500 cursor-pointer">
                  <input type="checkbox" checked={newSupplier.backup} onChange={(e) => setNewSupplier({ ...newSupplier, backup: e.target.checked })} className="w-4 h-4 rounded-sm bg-surface border-slate-200 bg-red-50" />
                  Backup supplier
                </label>
                <button onClick={addSupplier} className="ml-auto bg-red-500 text-white rounded-sm flex items-center justify-center gap-1 hover:opacity-90 transition-opacity px-4 py-2">
                  <Plus size={16} /> Add supplier
                </button>
              </div>

              {suppliers.length > 0 && (
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                  <p className="text-label-sm text-slate-500 uppercase tracking-widest mb-3">{suppliers.length} suppliers added</p>
                  {suppliers.map((s, i) => (
                    <div key={i} className="flex items-center justify-between py-2 border-b border-slate-200 last:border-0">
                      <div className="flex flex-col">
                        <span className="text-body-md">{s.name} — {s.country}{s.backup ? " (backup)" : ""}</span>
                        <span className="text-[10px] font-headline font-medium text-slate-500 mt-1 leading-relaxed">
                          {s.email} · {s.tier}{s.category && ` · ${s.category}`}{s.products && ` · ${s.products}`}{s.slaDays && ` · SLA: ${s.slaDays}d`} · {s.incoterm}
                        </span>
                      </div>
                      <button aria-label="Remove Supplier" onClick={() => setSuppliers(suppliers.filter((_, idx) => idx !== i))} className="text-slate-500 hover:text-red-500">
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Navigation */}
          <div className="flex items-center justify-between mt-10 pt-6 border-t border-slate-200">
            {currentStep > 0 ? (
              <button onClick={() => setCurrentStep(currentStep - 1)} className="flex items-center gap-2 text-body-md text-slate-500 hover:text-slate-900 transition-colors">
                <ChevronLeft size={16} /> Previous Step
              </button>
            ) : <div />}
            {currentStep < 2 ? (
              <button
                onClick={() => setCurrentStep(currentStep + 1)}
                className="bg-foreground text-white px-6 py-3 rounded-sm font-medium hover:opacity-90 transition-opacity"
              >
                Next Step →
              </button>
            ) : (
              <button
                onClick={launch}
                disabled={submitting}
                className="bg-red-500 text-white px-6 py-3 rounded-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {submitting ? "Launching…" : "Launch Praecantator"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default OnboardingPage;
