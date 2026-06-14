import { useQuery } from "@tanstack/react-query";
import { getWatchlists } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";
import WatchlistCreateForm from "./WatchlistCreateForm";

interface WatchlistListProps {
  selectedWatchlistId: number | null;
  onSelect: (watchlistId: number) => void;
}

export default function WatchlistList({ selectedWatchlistId, onSelect }: WatchlistListProps) {
  const { t } = useSettings();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["watchlists"],
    queryFn: getWatchlists,
  });

  return (
    <div className="card">
      <h2>{t.watchlists.title}</h2>
      <p className="section-description">{t.watchlists.description}</p>
      {isLoading && <p className="muted">{t.common.loading}</p>}
      {isError && <p className="value error">{(error as Error)?.message ?? t.common.loadError}</p>}
      {data && data.length === 0 && <p className="muted">{t.watchlists.empty}</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th></th>
                <th>{t.watchlists.colId}</th>
                <th>{t.watchlists.colName}</th>
                <th>{t.watchlists.colDescription}</th>
                <th>{t.watchlists.colEnabled}</th>
                <th>{t.watchlists.colSymbolCount}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((watchlist) => (
                <tr
                  key={watchlist.id}
                  className={watchlist.id === selectedWatchlistId ? "selected" : undefined}
                  onClick={() => onSelect(watchlist.id)}
                  style={{ cursor: "pointer" }}
                >
                  <td>
                    <input
                      type="radio"
                      checked={watchlist.id === selectedWatchlistId}
                      onChange={() => onSelect(watchlist.id)}
                    />
                  </td>
                  <td>{watchlist.id}</td>
                  <td>{watchlist.name}</td>
                  <td>{watchlist.description ?? "-"}</td>
                  <td>
                    <span className={`pill ${watchlist.enabled ? "off" : "on"}`}>
                      {watchlist.enabled ? t.watchlists.enabledYes : t.watchlists.enabledNo}
                    </span>
                  </td>
                  <td>{watchlist.symbol_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <WatchlistCreateForm />
    </div>
  );
}
