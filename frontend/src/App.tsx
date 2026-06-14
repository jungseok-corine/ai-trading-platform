import { useState } from "react";
import DashboardPage from "./pages/DashboardPage";
import StrategiesPage from "./pages/StrategiesPage";
import WatchlistsPage from "./pages/WatchlistsPage";
import { SettingsProvider, useSettings } from "./i18n/SettingsContext";
import SettingsBar from "./i18n/SettingsBar";

type Tab = "dashboard" | "strategies" | "watchlists";

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
        <SettingsBar />
      </nav>
      {tab === "dashboard" && <DashboardPage />}
      {tab === "strategies" && <StrategiesPage />}
      {tab === "watchlists" && <WatchlistsPage />}
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
