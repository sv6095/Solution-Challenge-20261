import { Link } from "react-router-dom";
import heroGlobe from "@/assets/hero-globe.jpg";

const LandingPage = () => {
  return (
    <div className="min-h-screen bg-white text-slate-900">
      {/* Navbar */}
      <nav className="fixed top-0 w-full z-50 border border-slate-200 bg-white">
        <div className="container mx-auto flex items-center justify-between h-14 px-6">
          <div className="flex items-center gap-3">
            <img src="/Praecantator.png" alt="Logo" className="w-8 h-8 object-contain" />
            <span className="font-headline text-xl font-bold text-red-500">Praecantator</span>
          </div>
          <div className="hidden md:flex items-center gap-8 text-body-md text-slate-500">
            <a href="#features" className="hover:text-slate-900 transition-colors">Features</a>
            <a href="#how-it-works" className="hover:text-slate-900 transition-colors">How It Works</a>
            <a href="#pricing" className="hover:text-slate-900 transition-colors">Pricing</a>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/login" className="text-body-md text-slate-500 hover:text-slate-900 transition-colors">Sign In</Link>
            <Link to="/register" className="bg-foreground text-white px-4 py-2 rounded-sm text-body-md font-medium hover:opacity-90 transition-opacity">
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative pt-32 pb-20 bg-gradient-to-b from-white to-slate-50 overflow-hidden">
        <div className="container mx-auto px-6 grid lg:grid-cols-2 gap-12 items-center">
          <div>
            <div className="inline-flex items-center gap-2 border border-slate-200 bg-white px-3 py-1.5 rounded-sm mb-8">
              <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse-glow" />
              <span className="text-label-sm uppercase tracking-widest text-slate-500">Kinetic Fortress Activated</span>
            </div>
            <h1 className="text-display-lg leading-tight mb-6">
              Your Supply Chain{" "}
              <span className="text-red-500">Doesn't Stop.</span>{" "}
              Neither Should Your Defense.
            </h1>
            <p className="text-body-md text-slate-500 max-w-lg mb-10">
              Praecantator detects global disruptions and executes your response — automatically. From detection to action in minutes, not days.
            </p>
            <div className="flex items-center gap-4">
              <Link to="/register" className="bg-foreground text-white px-6 py-3 rounded-sm font-medium hover:opacity-90 transition-opacity">
                Get Started Free
              </Link>
              <a href="#how-it-works" className="border border-slate-200 bg-white px-6 py-3 rounded-sm font-medium hover:bg-slate-50 transition-colors">
                See it Live
              </a>
            </div>
          </div>
          <div className="relative">
            <div className="border border-slate-200 bg-white rounded-xl overflow-hidden">
              <img src={heroGlobe} alt="Global supply chain intelligence visualization" width={800} height={600} className="w-full" />
            </div>
            <div className="absolute -bottom-4 left-1/2 -translate-x-1/2 border border-slate-200 bg-white px-6 py-3 rounded-sm">
              <span className="text-headline-md text-red-500 font-bold">99.9%</span>
              <span className="text-label-sm text-slate-500 block uppercase tracking-widest">Threat Detection Rate</span>
            </div>
          </div>
        </div>
        {/* Trust stats */}
        <div className="container mx-auto px-6 mt-24 grid grid-cols-3 gap-8 max-w-2xl text-center">
          {[
            { value: "139", label: "Countries Monitored" },
            { value: "4", label: "Live Data Sources" },
            { value: "< 15 min", label: "Time to Response" },
          ].map((stat) => (
            <div key={stat.label}>
              <p className="font-headline text-3xl font-bold text-slate-900">{stat.value}</p>
              <p className="text-label-sm text-red-500 uppercase tracking-widest mt-1">{stat.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="py-24 border-t border-b border-slate-200 bg-slate-50/50">
        <div className="container mx-auto px-6">
          <div className="flex items-center gap-3 mb-12">
            <div className="sentinel-accent-bar h-8" />
            <h2 className="text-headline-md font-bold">How It Works</h2>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {[
              { num: "01", title: "DETECT", desc: "Real-time signals from global intelligence feeds." },
              { num: "02", title: "ASSESS", desc: "AI-driven impact analysis on your specific nodes." },
              { num: "03", title: "DECIDE", desc: "Protocol suggestions based on historical data." },
              { num: "04", title: "ACT", desc: "Automated workflows to reroute and secure." },
              { num: "05", title: "AUDIT", desc: "Immutable logs for full regulatory compliance." },
            ].map((step) => (
              <div key={step.num} className="border border-slate-200 bg-slate-50 rounded-lg p-5 relative group">
                <span className="text-label-sm font-bold text-red-500">{step.num}</span>
                <h3 className="font-headline text-lg font-bold mt-2 mb-2">{step.title}</h3>
                <p className="text-body-md text-slate-500">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-24">
        <div className="container mx-auto px-6">
          <div className="flex items-center justify-between mb-12">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <div className="sentinel-accent-bar h-8" />
                <h2 className="text-headline-md font-bold">Tactical Capabilities</h2>
              </div>
              <p className="text-body-md text-slate-500 ml-4">A complete arsenal of tools designed to outpace volatility and secure every link in your chain.</p>
            </div>
            <span className="text-label-sm text-red-500 uppercase tracking-widest hidden md:block">All Features</span>
          </div>
          <div className="grid md:grid-cols-3 gap-4">
            {[
              { icon: "🌐", title: "Geo-Spatial Intelligence", desc: "Real-time mapping of political, climate, and labor unrest risks globally." },
              { icon: "🛡️", title: "Counterparty Health", desc: "Continuous financial and operational vetting of tier 1 and tier 2 suppliers." },
              { icon: "🔄", title: "Dynamic Rerouting", desc: "Algorithmic route optimization when primary corridors are compromised." },
              { icon: "⚡", title: "API Integration Hub", desc: "Connect existing ERP and WMS data directly into the central fortress." },
              { icon: "🔒", title: "Quantum Encryption", desc: "Secure data transmission across all global logistics nodes." },
              { icon: "📡", title: "Signal Monitor", desc: "Dark web and specialized news tracking for early threat detection." },
            ].map((feat) => (
              <div key={feat.title} className="border border-slate-200 bg-slate-50 rounded-lg p-6 hover:bg-slate-100 transition-colors">
                <span className="text-2xl mb-4 block">{feat.icon}</span>
                <h3 className="font-headline font-bold mb-2">{feat.title}</h3>
                <p className="text-body-md text-slate-500">{feat.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-24 border-t border-b border-slate-200 bg-slate-50/50">
        <div className="container mx-auto px-6 text-center">
          <h2 className="text-headline-md font-bold mb-2">Deployment Tiers</h2>
          <p className="text-body-md text-slate-500 mb-12">Scalable protection for single-node operations to global enterprises.</p>
          <div className="grid md:grid-cols-3 gap-6 max-w-4xl mx-auto">
            {[
              {
                name: "STANDARD", price: "$2,400", period: "/mo", recommended: false,
                features: ["10 Monitored Nodes", "24/7 Intelligence Feed", "Standard API Access"],
                cta: "Select Deployment",
              },
              {
                name: "PROFESSIONAL", price: "$8,500", period: "/mo", recommended: true,
                features: ["50 Monitored Nodes", "Predictive Risk Modelling", "Priority Incident Response", "Full Audit History"],
                cta: "Launch Fortress",
              },
              {
                name: "ENTERPRISE", price: "CUSTOM", period: "", recommended: false,
                features: ["Unlimited Nodes", "Custom Signal Integration", "On-Prem Deployment Options"],
                cta: "Contact Command",
              },
            ].map((tier) => (
              <div key={tier.name} className={`border border-slate-200 bg-slate-50 rounded-lg p-8 text-left relative ${tier.recommended ? "ring-1 ring-red-500" : ""}`}>
                {tier.recommended && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-red-500 px-3 py-1 rounded-sm text-label-sm font-bold text-white uppercase">
                    Recommended
                  </span>
                )}
                <p className="text-label-sm uppercase tracking-widest text-slate-500 mb-4">{tier.name}</p>
                <p className="font-headline text-4xl font-bold mb-1">{tier.price}<span className="text-body-md text-slate-500">{tier.period}</span></p>
                <ul className="mt-6 space-y-3 mb-8">
                  {tier.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-body-md">
                      <span className="text-red-500">✓</span> {f}
                    </li>
                  ))}
                </ul>
                <Link
                  to="/register"
                  className={`block w-full text-center py-3 rounded-sm font-medium transition-all ${
                    tier.recommended
                      ? "bg-red-500 text-white hover:opacity-90"
                      : "border border-slate-200 bg-white hover:bg-slate-50"
                  }`}
                >
                  {tier.cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200 py-8">
        <div className="container mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-label-sm text-slate-500 uppercase tracking-widest">© 2026 Praecantator. All Rights Reserved.</p>
          <div className="flex gap-6 text-label-sm text-slate-500 uppercase tracking-widest">
            <a href="#" className="hover:text-slate-900 transition-colors">Terms of Service</a>
            <a href="#" className="hover:text-slate-900 transition-colors">Privacy Policy</a>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
