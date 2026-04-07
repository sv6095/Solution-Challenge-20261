import { Outlet, Link, useLocation } from "react-router-dom";
import { useState } from "react";
import {
  LayoutDashboard, Globe, Workflow, BarChart3, Navigation, FileText,
  Radio, ClipboardList, Settings, Bell, Search, Menu, X, ChevronLeft,
} from "lucide-react";

const navItems = [
  { title: "Dashboard", icon: LayoutDashboard, path: "/dashboard" },
  { title: "Risk Map", icon: Globe, path: "/dashboard/map" },
  { title: "Workflow Engine", icon: Workflow, path: "/dashboard/workflow" },
  { title: "Exposure Scores", icon: BarChart3, path: "/dashboard/exposure" },
  { title: "Route Intelligence", icon: Navigation, path: "/dashboard/routes" },
  { title: "RFQ Manager", icon: FileText, path: "/dashboard/rfq" },
  { title: "Signal Monitor", icon: Radio, path: "/dashboard/signals" },
  { title: "Audit Log", icon: ClipboardList, path: "/dashboard/audit" },
  { title: "Settings", icon: Settings, path: "/dashboard/settings" },
];

const DashboardLayout = () => {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="min-h-screen flex bg-background">
      {/* Sidebar */}
      <aside className={`${collapsed ? "w-16" : "w-56"} shrink-0 surface-container-low flex flex-col transition-all duration-200 sticky top-0 h-screen`}>
        <div className="p-4 flex items-center justify-between">
          {!collapsed && (
            <div>
              <span className="font-headline text-sm font-bold text-sentinel">Praecantator</span>
              <p className="text-label-sm text-secondary uppercase tracking-widest">Kinetic Fortress v1.0</p>
            </div>
          )}
          <button onClick={() => setCollapsed(!collapsed)} className="text-secondary hover:text-foreground transition-colors">
            {collapsed ? <Menu size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>

        <nav className="flex-1 px-2 py-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path || (item.path === "/dashboard" && location.pathname === "/dashboard");
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-sm text-body-md transition-colors relative ${
                  isActive
                    ? "surface-container-high text-foreground font-medium"
                    : "text-secondary hover:text-foreground hover:bg-surface-high/50"
                }`}
              >
                {isActive && <div className="absolute left-0 top-0 bottom-0 w-1 bg-sentinel rounded-r" />}
                <item.icon size={18} />
                {!collapsed && <span>{item.title}</span>}
              </Link>
            );
          })}
        </nav>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top navbar */}
        <header className="h-14 flex items-center justify-between px-6 surface-container-low shrink-0 sticky top-0 z-30">
          <div className="flex items-center gap-4">
            <span className="font-headline text-sm font-bold text-sentinel">Praecantator</span>
            <span className="text-label-sm text-sentinel uppercase tracking-widest">Workspaces</span>
          </div>
          <div className="flex items-center gap-4">
            <div className="hidden md:flex items-center gap-2 glass-panel px-3 py-1.5 rounded-sm">
              <Search size={14} className="text-secondary" />
              <input placeholder="Global node search..." className="bg-transparent border-0 text-body-md text-foreground placeholder:text-secondary focus:outline-none w-48" />
            </div>
            <button aria-label="Notifications" className="relative text-secondary hover:text-foreground transition-colors">
              <Bell size={18} />
              <span className="absolute -top-1 -right-1 w-2 h-2 bg-sentinel rounded-full" />
            </button>
            <Link to="/dashboard/settings">
              <Settings size={18} className="text-secondary hover:text-foreground transition-colors" />
            </Link>
          </div>
        </header>

        <main className="flex-1 p-6 overflow-y-auto">
          <Outlet />
        </main>

        <footer className="px-6 py-3 text-center text-label-sm text-secondary uppercase tracking-widest">
          © 2026 Praecantator. All Rights Reserved.
        </footer>
      </div>
    </div>
  );
};

export default DashboardLayout;
