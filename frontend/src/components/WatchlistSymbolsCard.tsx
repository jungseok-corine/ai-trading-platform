import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import {
  addWatchlistSymbol,
  deleteWatchlistSymbol,
  getWatchlistSymbols,
  updateWatchlistSymbol,
} from "../api/client";
import { useSettings } from "../i18n/SettingsContext";
import type { WatchlistSymbol } from "../types";

interface WatchlistSymbolsCardProps {
  watchlistId: number;
}

function SymbolRow({ watchlistId, symbol }: { watchlistId: number; symbol: WatchlistSymbol }) {
  const { t } = useSettings();
  const queryClient = useQueryClient();

  const toggleMutation = useMutation({
    mutationFn: () => updateWatchlistSymbol(watchlistId, symbol.id, { enabled: !symbol.enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlist-symbols", watchlistId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteWatchlistSymbol(watchlistId, symbol.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlist-symbols", watchlistId] });
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
    },
  });

  return (
    <tr>
      <td>{symbol.symbol_code}</td>
      <td>{symbol.symbol_name ?? "-"}</td>
      <td>
        <span className={`pill ${symbol.enabled ? "off" : "on"}`}>
          {symbol.enabled ? t.watchlists.enabledYes : t.watchlists.enabledNo}
        </span>
      </td>
      <td>{symbol.note ?? "-"}</td>
      <td>
        <div className="actions">
          <button disabled={toggleMutation.isPending} onClick={() => toggleMutation.mutate()}>
            {symbol.enabled ? t.watchlists.disable : t.watchlists.enable}
          </button>
          <button
            className="danger"
            disabled={deleteMutation.isPending}
            onClick={() => deleteMutation.mutate()}
          >
            {t.watchlists.delete}
          </button>
        </div>
        {deleteMutation.isError && (
          <p className="action-result value error">
            {(deleteMutation.error as Error)?.message ?? t.watchlists.deleteFailed}
          </p>
        )}
      </td>
    </tr>
  );
}

function AddSymbolForm({ watchlistId }: { watchlistId: number }) {
  const { t } = useSettings();
  const [symbolCode, setSymbolCode] = useState("");
  const [symbolName, setSymbolName] = useState("");
  const [note, setNote] = useState("");
  const queryClient = useQueryClient();

  const addMutation = useMutation({
    mutationFn: () =>
      addWatchlistSymbol(watchlistId, {
        symbol_code: symbolCode.trim(),
        symbol_name: symbolName.trim() || null,
        note: note.trim() || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlist-symbols", watchlistId] });
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
      setSymbolCode("");
      setSymbolName("");
      setNote("");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbolCode.trim()) return;
    addMutation.mutate();
  };

  const errorMessage = (() => {
    if (!addMutation.isError) return null;
    if (axios.isAxiosError(addMutation.error) && addMutation.error.response?.status === 409) {
      return t.watchlists.duplicateSymbol;
    }
    return (addMutation.error as Error)?.message ?? t.watchlists.addSymbolFailed;
  })();

  return (
    <form className="strategy-version-create-form" onSubmit={handleSubmit}>
      <h4>{t.watchlists.addSymbolTitle}</h4>
      <div className="form-row">
        <label htmlFor={`watchlist-${watchlistId}-symbol-code`}>{t.watchlists.symbolCode}</label>
        <input
          id={`watchlist-${watchlistId}-symbol-code`}
          type="text"
          value={symbolCode}
          placeholder={t.watchlists.symbolCodePlaceholder}
          onChange={(e) => setSymbolCode(e.target.value)}
          required
        />
      </div>
      <div className="form-row">
        <label htmlFor={`watchlist-${watchlistId}-symbol-name`}>{t.watchlists.symbolName}</label>
        <input
          id={`watchlist-${watchlistId}-symbol-name`}
          type="text"
          value={symbolName}
          onChange={(e) => setSymbolName(e.target.value)}
        />
      </div>
      <div className="form-row">
        <label htmlFor={`watchlist-${watchlistId}-note`}>{t.watchlists.note}</label>
        <input
          id={`watchlist-${watchlistId}-note`}
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
      <div className="actions">
        <button className="primary" type="submit" disabled={addMutation.isPending}>
          {t.watchlists.addSymbol}
        </button>
      </div>
      {errorMessage && <p className="action-result value error">{errorMessage}</p>}
    </form>
  );
}

export default function WatchlistSymbolsCard({ watchlistId }: WatchlistSymbolsCardProps) {
  const { t } = useSettings();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["watchlist-symbols", watchlistId],
    queryFn: () => getWatchlistSymbols(watchlistId),
  });

  return (
    <div className="card">
      <h3>{t.watchlists.symbolsTitle}</h3>
      {isLoading && <p className="muted">{t.common.loading}</p>}
      {isError && <p className="value error">{(error as Error)?.message ?? t.common.loadError}</p>}
      {data && data.length === 0 && <p className="muted">{t.watchlists.symbolsEmpty}</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t.watchlists.colSymbolCode}</th>
                <th>{t.watchlists.colSymbolName}</th>
                <th>{t.watchlists.colEnabled}</th>
                <th>{t.watchlists.colNote}</th>
                <th>{t.watchlists.colActions}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((symbol) => (
                <SymbolRow key={symbol.id} watchlistId={watchlistId} symbol={symbol} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <AddSymbolForm watchlistId={watchlistId} />
    </div>
  );
}
