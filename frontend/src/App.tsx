import { useState } from "react";
import DashboardPage from "./pages/DashboardPage";
import StrategiesPage from "./pages/StrategiesPage";

type Tab = "dashboard" | "strategies";

function App() {
  const [tab, setTab] = useState<Tab>("dashboard");

  return (
    <div>
      <nav className="top-nav">
        <button
          className={tab === "dashboard" ? "primary" : undefined}
          onClick={() => setTab("dashboard")}
        >
          Dashboard
        </button>
        <button
          className={tab === "strategies" ? "primary" : undefined}
          onClick={() => setTab("strategies")}
        >
          Strategies
        </button>
      </nav>
      {tab === "dashboard" && <DashboardPage />}
      {tab === "strategies" && <StrategiesPage />}
    </div>
  );
}

export default App;
