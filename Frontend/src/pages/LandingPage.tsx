import { Link } from "react-router-dom";
import heroGlobe from "@/assets/hero-globe.jpg";

const LandingPage = () => {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Navbar */}
      <nav className="fixed top-0 w-full z-50 glass-panel">
        <div className="container mx-auto flex items-center justify-between h-14 px-6">
          <span className="font-headline text-lg font-bold text-sentinel">Praecantator</span>
          <div className="hidden md:flex items-center gap-8 text-body-md text-secondary">
            <a href="#features" className="hover:text-foreground transition-colors">Features</a>
            <a href="#how-it-works" className="hover:text-foreground transition-colors">How It Works</a>
            <a href="#pricing" className="hover:text-foreground transition-colors">Pricing</a>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/login" className="text-body-md text-secondary hover:text-foreground transition-colors">Sign In</Link>
            <Link to="/register" className="bg-foreground text-background px-4 py-2 rounded-sm text-body-md font-medium hover:opacity-90 transition-opacity">
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative pt-32 pb-20 hero-gradient overflow-hidden">
        <div className="container mx-auto px-6 grid lg:grid-cols-2 gap-12 items-center">
          <div>
            <div className="inline-flex items-center gap-2 glass-panel px-3 py-1.5 rounded-sm mb-8">
              <span className="w-2 h-2 rounded-full bg-sentinel animate-pulse-glow" />
              <span className="text-label-sm uppercase tracking-widest text-secondary">Kinetic Fortress v1.0 Activated</span>
            </div>
            <h1 className="text-display-lg leading-tight mb-6">
              Your Supply Chain{" "}
              <span className="text-sentinel">Doesn't Stop.</span>{" "}
              Neither Should Your Defense.
            </h1>
            <p className="text-body-md text-secondary max-w-lg mb-10">
              Praecantator detects global disruptions and executes your response — automatically. From detection to action in minutes, not days.
            </p>
            <div className="flex items-center gap-4">
              <Link to="/register" className="bg-foreground text-background px-6 py-3 rounded-sm font-medium hover:opacity-90 transition-opacity">
                Get Started Free
              </Link>
              <a href="#how-it-works" className="glass-panel px-6 py-3 rounded-sm font-medium hover:bg-white/10 transition-colors">
                See it Live
              </a>
            </div>
          </div>
          <div className="relative">
            <div className="glass-panel rounded-xl overflow-hidden">
              <img src={heroGlobe} alt="Global supply chain intelligence visualization" width={800} height={600} className="w-full" />
            </div>
            <div className="absolute -bottom-4 left-1/2 -translate-x-1/2 glass-panel px-6 py-3 rounded-sm">
              <span className="text-headline-md text-sentinel font-bold">99.9%</span>
              <span className="text-label-sm text-secondary block uppercase tracking-widest">Threat Detection Rate</span>
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
              <p className="font-headline text-3xl font-bold text-foreground">{stat.value}</p>
              <p className="text-label-sm text-sentinel uppercase tracking-widest mt-1">{stat.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="py-24 surface-container-low">
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
              <div key={step.num} className="surface-container-high rounded-lg p-5 relative group">
                <span className="text-label-sm font-bold text-sentinel">{step.num}</span>
                <h3 className="font-headline text-lg font-bold mt-2 mb-2">{step.title}</h3>
                <p className="text-body-md text-secondary">{step.desc}</p>
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
              <p className="text-body-md text-secondary ml-4">A complete arsenal of tools designed to outpace volatility and secure every link in your chain.</p>
            </div>
            <span className="text-label-sm text-sentinel uppercase tracking-widest hidden md:block">All Features</span>
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
              <div key={feat.title} className="surface-container-high rounded-lg p-6 hover:bg-surface-highest transition-colors">
                <span className="text-2xl mb-4 block">{feat.icon}</span>
                <h3 className="font-headline font-bold mb-2">{feat.title}</h3>
                <p className="text-body-md text-secondary">{feat.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-24 surface-container-low">
        <div className="container mx-auto px-6 text-center">
          <h2 className="text-headline-md font-bold mb-2">Deployment Tiers</h2>
          <p className="text-body-md text-secondary mb-12">Scalable protection for single-node operations to global enterprises.</p>
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
              <div key={tier.name} className={`surface-container-high rounded-lg p-8 text-left relative ${tier.recommended ? "ring-1 ring-sentinel-red" : ""}`}>
                {tier.recommended && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-sentinel px-3 py-1 rounded-sm text-label-sm font-bold text-background uppercase">
                    Recommended
                  </span>
                )}
                <p className="text-label-sm uppercase tracking-widest text-secondary mb-4">{tier.name}</p>
                <p className="font-headline text-4xl font-bold mb-1">{tier.price}<span className="text-body-md text-secondary">{tier.period}</span></p>
                <ul className="mt-6 space-y-3 mb-8">
                  {tier.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-body-md">
                      <span className="text-sentinel">✓</span> {f}
                    </li>
                  ))}
                </ul>
                <Link
                  to="/register"
                  className={`block w-full text-center py-3 rounded-sm font-medium transition-all ${
                    tier.recommended
                      ? "bg-sentinel text-background hover:opacity-90"
                      : "glass-panel hover:bg-white/10"
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
      <footer className="border-t border-border py-8">
        <div className="container mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-label-sm text-secondary uppercase tracking-widest">© 2026 Praecantator. All Rights Reserved.</p>
          <div className="flex gap-6 text-label-sm text-secondary uppercase tracking-widest">
            <a href="#" className="hover:text-foreground transition-colors">Terms of Service</a>
            <a href="#" className="hover:text-foreground transition-colors">Privacy Policy</a>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
