import { Outlet, Link, useLocation } from "react-router-dom";
import { useState, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Crosshair, Network, AlertTriangle, Radar, Shield,
  Settings, Bell, Menu, ChevronLeft, ShieldAlert, Wifi, WifiOff,
} from "lucide-react";
import { api, getAccessToken, getUserId } from "@/lib/api";
import { useWSQueryInvalidation } from "@/hooks/use-websocket";

const BASE = (import.meta.env.VITE_API_URL ?? "/api").replace(/\/+$/, "");
void BASE; // referenced by authHeaders fetch calls below

function authHeaders(): HeadersInit {
  const token  = getAccessToken();
  const userId = getUserId();
  return {
    "Content-Type": "application/json",
    "X-User-Id": userId,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

/* ── Autonomous Navigation: 5 items, system drives ── */
const NAV_ITEMS = [
  {
    title: "Command",
    icon: Crosshair,
    path: "/dashboard",
    description: "Live briefing",
  },
  {
    title: "Network",
    icon: Network,
    path: "/dashboard/network",
    description: "Supplier graph",
  },
  {
    title: "Incidents",
    icon: AlertTriangle,
    path: "/dashboard/incidents",
    description: "Auto-analyzed",
  },
  {
    title: "Intelligence",
    icon: Radar,
    path: "/dashboard/intelligence",
    description: "Signals & map",
  },
  {
    title: "Compliance",
    icon: Shield,
    path: "/dashboard/compliance",
    description: "Audit & export",
  },
];

const DashboardLayout = () => {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const queryClient = useQueryClient();

  // ── WebSocket: auto-invalidate React Query caches on push events ──────
  const tenantId = getUserId();  // tenant = user in single-tenant dev mode
  const { isConnected: wsConnected } = useWSQueryInvalidation(tenantId, queryClient);

  const { data: incidentSummary } = useQuery({
    queryKey: ["incident-summary-nav"],
    queryFn: api.incidents.summary,
    refetchInterval: 20_000,
  });

  const { data: checkpointData } = useQuery({
    queryKey: ["governance-checkpoints-nav"],
    queryFn: async () => {
      const r = await fetch(`${BASE}/governance/checkpoints`, { headers: authHeaders() });
      if (!r.ok) return { count: 0 };
      return r.json();
    },
    refetchInterval: 30_000,
  });

  const critCount       = incidentSummary?.critical_count ?? 0;
  const totalNodes      = incidentSummary?.total_nodes ?? 850;
  const pendingChkCount = checkpointData?.count ?? 0;

  return (
    <div className="min-h-screen flex bg-background">
      {/* Sidebar */}
      <aside
        className={`${
          collapsed ? "w-14" : "w-56"
        } shrink-0 bg-card flex flex-col transition-all duration-150 sticky top-0 h-screen border-r border-border`}
      >
        <div className="px-4 py-4 flex items-center justify-between">
          {!collapsed && (
            <div className="flex items-center gap-3">
              <img src="/Praecantator.png" alt="Logo" className="w-8 h-8 object-contain" />
              <span className="font-headline text-xl font-bold text-foreground tracking-tight">
                Praecantator
              </span>
            </div>
          )}
        </div>

        {!collapsed && (
          <div className="px-4 pb-3 border-b border-border">
            <p className="text-[10px] font-headline font-bold uppercase tracking-[0.15em] text-slate-600">
              Autonomous SCRM
            </p>
          </div>
        )}

        <nav className="flex-1 px-2 py-3 overflow-y-auto space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.path === "/dashboard"
                ? location.pathname === "/dashboard"
                : location.pathname.startsWith(item.path);
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-3 py-2.5 text-sm transition-colors duration-150 relative group ${
                  isActive
                    ? "bg-muted text-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted"
                }`}
              >
                {isActive && (
                  <div className="absolute left-0 top-1 bottom-1 w-0.5 bg-red-500" />
                )}
                <item.icon
                  size={16}
                  className={isActive ? "text-red-500" : ""}
                />
                {!collapsed && (
                  <div className="flex flex-col min-w-0">
                    <span className="text-sm font-headline font-bold tracking-wide">{item.title}</span>
                    <span className="text-[10px] font-headline font-semibold text-slate-500 uppercase tracking-wider">
                      {item.description}
                    </span>
                  </div>
                )}
                {/* Incident badge */}
                {item.title === "Incidents" && !collapsed && critCount > 0 && (
                  <span className="ml-auto text-[10px] font-headline font-bold bg-red-500 text-white px-1.5 py-0.5 min-w-[1.25rem] text-center">
                    {critCount}
                  </span>
                )}
                {/* Checkpoint badge on Compliance */}
                {item.title === "Compliance" && !collapsed && pendingChkCount > 0 && (
                  <span className="ml-auto text-[10px] font-headline font-bold bg-orange-500 text-white px-1.5 py-0.5 min-w-[1.25rem] text-center animate-pulse">
                    {pendingChkCount}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Settings at bottom */}
        <div className="px-2 py-2 border-t border-border">
          <Link
            to="/dashboard/settings"
            className={`flex items-center gap-3 px-3 py-2 text-sm transition-colors duration-150 ${
              location.pathname === "/dashboard/settings"
                ? "text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Settings size={14} />
            {!collapsed && <span className="text-xs font-headline">Settings</span>}
          </Link>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 bg-background">
        {/* Top bar */}
        <header className="h-12 flex items-center justify-between px-6 bg-card shrink-0 sticky top-0 z-30 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className={`w-1.5 h-1.5 ${wsConnected ? 'bg-green-500' : 'bg-amber-500'} animate-pulse`} />
              <span className="text-[10px] font-headline font-bold uppercase tracking-[0.1em] text-slate-600">
                {wsConnected ? 'Live' : 'Polling'} · {totalNodes.toLocaleString()} nodes
              </span>
              {wsConnected && (
                <Wifi size={10} className="text-green-500" />
              )}
            </div>
            {pendingChkCount > 0 && (
              <Link
                to="/dashboard/compliance"
                className="flex items-center gap-1.5 text-[10px] font-headline font-bold text-orange-500 hover:text-orange-400 transition-colors"
              >
                <ShieldAlert size={12} className="animate-pulse" />
                {pendingChkCount} checkpoint{pendingChkCount > 1 ? "s" : ""} pending
              </Link>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              aria-label="Notifications"
              className="relative text-muted-foreground hover:text-foreground transition-colors duration-150"
            >
              <Bell size={16} />
              <span className="absolute -top-1 -right-1 w-1.5 h-1.5 bg-red-500 rounded-full" />
            </button>
          </div>
        </header>

        <main className="flex-1 p-6 overflow-y-auto">
          <Outlet />
        </main>

        <footer className="px-6 py-4 border-t border-border bg-card flex items-center justify-between">
           <div className="flex items-center gap-2 opacity-60">
              <span className="w-1 h-1 bg-red-500 animate-pulse" />
              <span className="text-[10px] font-headline font-bold tracking-widest text-slate-500 uppercase">Autonomous Pipeline Active</span>
           </div>
           <span className="text-[10px] font-headline font-bold text-slate-500 uppercase tracking-widest">© 2026 Praecantator</span>
        </footer>
      </div>
    </div>
  );
};

export default DashboardLayout;
