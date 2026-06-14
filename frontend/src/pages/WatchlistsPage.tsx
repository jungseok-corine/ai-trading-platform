import { useState } from "react";
import WatchlistList from "../components/WatchlistList";
import WatchlistSymbolsCard from "../components/WatchlistSymbolsCard";
import WatchlistBulkStrategyForm from "../components/WatchlistBulkStrategyForm";
import { useSettings } from "../i18n/SettingsContext";

export default function WatchlistsPage() {
  const { t } = useSettings();
  const [selectedWatchlistId, setSelectedWatchlistId] = useState<number | null>(null);

  return (
    <div className="app">
      <h1>{t.watchlists.title}</h1>

      <WatchlistList selectedWatchlistId={selectedWatchlistId} onSelect={setSelectedWatchlistId} />

      {selectedWatchlistId === null && (
        <div className="card">
          <p className="muted">{t.watchlists.selectWatchlistPrompt}</p>
        </div>
      )}

      {selectedWatchlistId !== null && (
        <>
          <WatchlistSymbolsCard watchlistId={selectedWatchlistId} />
          <WatchlistBulkStrategyForm watchlistId={selectedWatchlistId} />
        </>
      )}
    </div>
  );
}
