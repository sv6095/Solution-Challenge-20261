import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import OnboardingPage from "./pages/OnboardingPage";
import DashboardLayout from "./components/DashboardLayout";
import DashboardHome from "./pages/dashboard/DashboardHome";
import RiskMap from "./pages/dashboard/RiskMap";
import ExposureScores from "./pages/dashboard/ExposureScores";
import RouteIntelligence from "./pages/dashboard/RouteIntelligence";
import RFQManager from "./pages/dashboard/RFQManager";
import SignalMonitor from "./pages/dashboard/SignalMonitor";
import AuditLog from "./pages/dashboard/AuditLog";
import SettingsPage from "./pages/dashboard/SettingsPage";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="/dashboard" element={<DashboardLayout />}>
            <Route index element={<DashboardHome />} />
            <Route path="map" element={<RiskMap />} />
            <Route path="exposure" element={<ExposureScores />} />
            <Route path="routes" element={<RouteIntelligence />} />
            <Route path="rfq" element={<RFQManager />} />
            <Route path="signals" element={<SignalMonitor />} />
            <Route path="audit" element={<AuditLog />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
