import { Outlet, Link, useLocation, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Crosshair, Network, AlertTriangle, Radar, Shield,
  Settings, Bell, ShieldAlert, Wifi, LogOut, User, Clock,
} from "lucide-react";
import { api, getAccessToken, getUserId, clearAuthSession } from "@/lib/api";
import { useWSQueryInvalidation } from "@/hooks/use-websocket";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const BASE = (import.meta.env.VITE_API_URL ?? "/api").replace(/\/+$/, "");

function authHeaders(): HeadersInit {
  const token  = getAccessToken();
  const userId = getUserId();
  return {
    "Content-Type": "application/json",
    "X-User-Id": userId,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const NAV_ITEMS = [
  { title: "Command",      icon: Crosshair,     path: "/dashboard",             description: "Live briefing" },
  { title: "Network",      icon: Network,       path: "/dashboard/network",     description: "Supplier graph" },
  { title: "Incidents",    icon: AlertTriangle, path: "/dashboard/incidents",   description: "Auto-analyzed" },
  { title: "Intelligence", icon: Radar,         path: "/dashboard/intelligence", description: "Signals & map" },
  { title: "Compliance",   icon: Shield,        path: "/dashboard/compliance",  description: "Audit & export" },
];

const PING_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

const DashboardLayout = () => {
  const location  = useLocation();
  const navigate  = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  void setCollapsed; // sidebar collapse reserved for future toggle
  const queryClient = useQueryClient();

  const tenantId = getUserId();
  const { isConnected: wsConnected } = useWSQueryInvalidation(tenantId, queryClient);
  const hasToken = Boolean(getAccessToken());

  // ── Keep Render backend alive — ping every 5 minutes ─────────────────────
  useEffect(() => {
    const ping = () => fetch(`${BASE}/ping`).catch(() => undefined);
    ping();
    const id = setInterval(ping, PING_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  // ── Data queries ──────────────────────────────────────────────────────────
  const { data: incidentSummary } = useQuery({
    queryKey: ["incident-summary-nav"],
    queryFn: api.incidents.summary,
    refetchInterval: 20_000,
    enabled: hasToken,
  });

  const { data: checkpointData } = useQuery({
    queryKey: ["governance-checkpoints-nav"],
    queryFn: async () => {
      const r = await fetch(`${BASE}/governance/checkpoints`, { headers: authHeaders() });
      if (!r.ok) return { count: 0, pending: [] };
      return r.json();
    },
    refetchInterval: 30_000,
    enabled: hasToken,
  });

  const critCount       = incidentSummary?.critical_count ?? 0;
  const totalNodes      = incidentSummary?.total_nodes ?? 850;
  const pendingChkCount = checkpointData?.count ?? 0;
  const pendingChks: { checkpoint_id: string; incident_id: string; risk_level: string; risk_trigger: string }[] =
    checkpointData?.pending ?? [];

  // ── Logout ────────────────────────────────────────────────────────────────
  function handleLogout() {
    clearAuthSession();
    navigate("/login");
  }

  const userId       = getUserId();
  const userInitial  = userId ? userId.charAt(0).toUpperCase() : "U";

  return (
    <div className="min-h-screen flex bg-background">
      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
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
                <item.icon size={16} className={isActive ? "text-red-500" : ""} />
                {!collapsed && (
                  <div className="flex flex-col min-w-0">
                    <span className="text-sm font-headline font-bold tracking-wide">{item.title}</span>
                    <span className="text-[10px] font-headline font-semibold text-slate-500 uppercase tracking-wider">
                      {item.description}
                    </span>
                  </div>
                )}
                {item.title === "Incidents" && !collapsed && critCount > 0 && (
                  <span className="ml-auto text-[10px] font-headline font-bold bg-red-500 text-white px-1.5 py-0.5 min-w-[1.25rem] text-center">
                    {critCount}
                  </span>
                )}
                {item.title === "Compliance" && !collapsed && pendingChkCount > 0 && (
                  <span className="ml-auto text-[10px] font-headline font-bold bg-orange-500 text-white px-1.5 py-0.5 min-w-[1.25rem] text-center animate-pulse">
                    {pendingChkCount}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

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

      {/* ── Main content ──────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 bg-background">
        {/* Top bar */}
        <header className="h-12 flex items-center justify-between px-6 bg-card shrink-0 sticky top-0 z-30 border-b border-border">
          {/* Left: live status */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className={`w-1.5 h-1.5 ${wsConnected ? "bg-green-500" : "bg-amber-500"} animate-pulse`} />
              <span className="text-[10px] font-headline font-bold uppercase tracking-[0.1em] text-slate-600">
                {wsConnected ? "Live" : "Polling"} · {totalNodes.toLocaleString()} nodes
              </span>
              {wsConnected && <Wifi size={10} className="text-green-500" />}
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

          {/* Right: notification bell + user menu */}
          <div className="flex items-center gap-3">

            {/* ── Notification bell ── */}
            <Popover>
              <PopoverTrigger asChild>
                <button
                  aria-label="Notifications"
                  className="relative text-muted-foreground hover:text-foreground transition-colors duration-150 cursor-pointer"
                >
                  <Bell size={16} />
                  {pendingChkCount > 0 && (
                    <span className="absolute -top-1 -right-1 w-1.5 h-1.5 bg-red-500 rounded-full animate-pulse" />
                  )}
                </button>
              </PopoverTrigger>
              <PopoverContent align="end" className="w-80 p-0">
                <div className="px-4 py-3 border-b border-border">
                  <p className="text-xs font-headline font-bold uppercase tracking-widest text-foreground">
                    Notifications
                  </p>
                </div>
                <div className="max-h-72 overflow-y-auto divide-y divide-border">
                  {pendingChks.length === 0 ? (
                    <div className="px-4 py-6 text-center">
                      <Bell size={20} className="mx-auto mb-2 text-muted-foreground/40" />
                      <p className="text-xs text-muted-foreground">No pending notifications</p>
                    </div>
                  ) : (
                    pendingChks.map((chk) => (
                      <Link
                        key={chk.checkpoint_id}
                        to="/dashboard/compliance"
                        className="flex items-start gap-3 px-4 py-3 hover:bg-muted transition-colors"
                      >
                        <ShieldAlert size={14} className="text-orange-500 mt-0.5 shrink-0" />
                        <div className="min-w-0">
                          <p className="text-xs font-semibold text-foreground truncate">
                            Checkpoint — {chk.risk_level}
                          </p>
                          <p className="text-[11px] text-muted-foreground truncate">{chk.risk_trigger}</p>
                          <p className="text-[10px] text-muted-foreground/60 mt-0.5 font-mono">
                            {chk.incident_id}
                          </p>
                        </div>
                      </Link>
                    ))
                  )}
                </div>
                <div className="px-4 py-2 border-t border-border flex items-center gap-1.5">
                  <Clock size={10} className="text-muted-foreground/50" />
                  <span className="text-[10px] text-muted-foreground/50 font-headline">
                    {wsConnected ? "Live updates on" : "Polling every 30 s"}
                  </span>
                </div>
              </PopoverContent>
            </Popover>

            {/* ── User menu / logout ── */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  aria-label="User menu"
                  className="w-7 h-7 rounded-full bg-muted border border-border flex items-center justify-center text-[11px] font-headline font-bold text-foreground hover:bg-muted/80 transition-colors cursor-pointer"
                >
                  {userInitial}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                <div className="px-3 py-2">
                  <p className="text-[10px] font-headline text-muted-foreground uppercase tracking-widest">
                    Signed in as
                  </p>
                  <p className="text-xs font-medium text-foreground truncate">{userId || "—"}</p>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem asChild>
                  <Link to="/dashboard/settings" className="flex items-center gap-2 cursor-pointer">
                    <User size={13} />
                    <span className="text-xs">Settings</span>
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={handleLogout}
                  className="flex items-center gap-2 text-red-500 focus:text-red-500 cursor-pointer"
                >
                  <LogOut size={13} />
                  <span className="text-xs">Sign out</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

          </div>
        </header>

        <main className="flex-1 p-6 overflow-y-auto">
          <Outlet />
        </main>

        <footer className="px-6 py-4 border-t border-border bg-card flex items-center justify-between">
          <div className="flex items-center gap-2 opacity-60">
            <span className="w-1 h-1 bg-red-500 animate-pulse" />
            <span className="text-[10px] font-headline font-bold tracking-widest text-slate-500 uppercase">
              Autonomous Pipeline Active
            </span>
          </div>
          <span className="text-[10px] font-headline font-bold text-slate-500 uppercase tracking-widest">
            © 2026 Praecantator
          </span>
        </footer>
      </div>
    </div>
  );
};

export default DashboardLayout;
