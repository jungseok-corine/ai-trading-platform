import { useState } from "react";
import DashboardPage from "./pages/DashboardPage";
import StrategiesPage from "./pages/StrategiesPage";
import WatchlistsPage from "./pages/WatchlistsPage";
import ResearchPage from "./pages/ResearchPage";
import { SettingsProvider, useSettings } from "./i18n/SettingsContext";
import SettingsBar from "./i18n/SettingsBar";

type Tab = "dashboard" | "strategies" | "watchlists" | "research";

function AppContent() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const { t } = useSettings();

  return (
    <div>
      <nav className="top-nav">
        <button
          className={tab === "dashboard" ? "primary" : undefined}
          onClick={() => setTab("dashboard")}
        >
          {t.nav.dashboard}
        </button>
        <button
          className={tab === "strategies" ? "primary" : undefined}
          onClick={() => setTab("strategies")}
        >
          {t.nav.strategies}
        </button>
        <button
          className={tab === "watchlists" ? "primary" : undefined}
          onClick={() => setTab("watchlists")}
        >
          {t.nav.watchlists}
        </button>
        <button
          className={tab === "research" ? "primary" : undefined}
          onClick={() => setTab("research")}
        >
          {t.nav.research}
        </button>
        <SettingsBar />
      </nav>
      {tab === "dashboard" && <DashboardPage />}
      {tab === "strategies" && <StrategiesPage />}
      {tab === "watchlists" && <WatchlistsPage />}
      {tab === "research" && <ResearchPage />}
    </div>
  );
}

function App() {
  return (
    <SettingsProvider>
      <AppContent />
    </SettingsProvider>
  );
}

export default App;
