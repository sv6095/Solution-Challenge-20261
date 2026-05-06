import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { FirebaseRedirectResume } from "@/components/FirebaseRedirectResume";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import OnboardingPage from "./pages/OnboardingPage";
import DashboardLayout from "./components/DashboardLayout";
import NotFound from "./pages/NotFound";

// v4 Core Pages
import CommandCenter from "@/pages/dashboard/CommandCenter";
import NetworkView from "@/pages/dashboard/NetworkView";
import Incidents from "@/pages/dashboard/Incidents";
import IncidentSimulator from "@/pages/dashboard/IncidentSimulator";
import Intelligence from "@/pages/dashboard/Intelligence";
import Compliance from "@/pages/dashboard/Compliance";
import SettingsPage from "./pages/dashboard/SettingsPage";
import RouteViewer from "@/pages/dashboard/RouteViewer";
// Legacy pages removed in v4
const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Sonner />
      <BrowserRouter>
        <FirebaseRedirectResume />
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="/dashboard" element={<DashboardLayout />}>
            {/* ── v4 Core Routes ── */}
            <Route index element={<CommandCenter />} />
            <Route path="network" element={<NetworkView />} />
            <Route path="incidents" element={<Incidents />} />
            <Route path="incident-simulator" element={<IncidentSimulator />} />
            <Route path="intelligence" element={<Intelligence />} />
            <Route path="compliance" element={<Compliance />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="route-viewer" element={<RouteViewer />} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
