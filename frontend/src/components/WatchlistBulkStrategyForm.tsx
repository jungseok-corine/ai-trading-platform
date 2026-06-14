import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createStrategyVersionsFromWatchlist, getStrategies } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";
import type { StrategyVersionStatus } from "../types";

interface WatchlistBulkStrategyFormProps {
  watchlistId: number;
}

const STATUS_OPTIONS: StrategyVersionStatus[] = ["draft", "testing", "active", "retired"];

export default function WatchlistBulkStrategyForm({ watchlistId }: WatchlistBulkStrategyFormProps) {
  const { t } = useSettings();
  const queryClient = useQueryClient();

  const { data: strategies } = useQuery({
    queryKey: ["strategies"],
    queryFn: getStrategies,
  });

  const [strategyId, setStrategyId] = useState<string>("");
  const [shortWindow, setShortWindow] = useState(5);
  const [longWindow, setLongWindow] = useState(20);
  const [timeframe, setTimeframe] = useState("5m");
  const [quantity, setQuantity] = useState(1);
  const [accountId, setAccountId] = useState<string>("");
  const [status, setStatus] = useState<StrategyVersionStatus>("testing");

  const bulkMutation = useMutation({
    mutationFn: () =>
      createStrategyVersionsFromWatchlist(watchlistId, {
        strategy_id: Number(strategyId),
        short_window: shortWindow,
        long_window: longWindow,
        timeframe,
        quantity,
        account_id: accountId === "" ? null : Number(accountId),
        status,
      }),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
      queryClient.invalidateQueries({ queryKey: ["strategy-versions", response.strategy_id] });
    },
  });

  const canSubmit = strategyId !== "" && !bulkMutation.isPending;

  return (
    <div className="card">
      <h3>{t.watchlists.bulkCreateTitle}</h3>
      <p className="section-description">{t.watchlists.bulkCreateDescription}</p>

      <div className="parameters-form">
        <div className="form-row">
          <label htmlFor={`watchlist-${watchlistId}-bulk-strategy`}>{t.watchlists.selectStrategy}</label>
          <select
            id={`watchlist-${watchlistId}-bulk-strategy`}
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
          >
            <option value="">{t.watchlists.selectStrategyPlaceholder}</option>
            {(strategies ?? []).map((strategy) => (
              <option key={strategy.id} value={strategy.id}>
                {strategy.name} (#{strategy.id})
              </option>
            ))}
          </select>
        </div>
        <div className="form-row">
          <label htmlFor={`watchlist-${watchlistId}-bulk-short-window`}>short_window</label>
          <input
            id={`watchlist-${watchlistId}-bulk-short-window`}
            type="number"
            min={1}
            value={shortWindow}
            onChange={(e) => setShortWindow(Number(e.target.value) || 0)}
          />
        </div>
        <div className="form-row">
          <label htmlFor={`watchlist-${watchlistId}-bulk-long-window`}>long_window</label>
          <input
            id={`watchlist-${watchlistId}-bulk-long-window`}
            type="number"
            min={1}
            value={longWindow}
            onChange={(e) => setLongWindow(Number(e.target.value) || 0)}
          />
        </div>
        <div className="form-row">
          <label htmlFor={`watchlist-${watchlistId}-bulk-timeframe`}>timeframe</label>
          <input
            id={`watchlist-${watchlistId}-bulk-timeframe`}
            type="text"
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
          />
        </div>
        <div className="form-row">
          <label htmlFor={`watchlist-${watchlistId}-bulk-quantity`}>quantity</label>
          <input
            id={`watchlist-${watchlistId}-bulk-quantity`}
            type="number"
            min={1}
            value={quantity}
            onChange={(e) => setQuantity(Number(e.target.value) || 0)}
          />
        </div>
        <div className="form-row">
          <label htmlFor={`watchlist-${watchlistId}-bulk-account-id`}>account_id</label>
          <input
            id={`watchlist-${watchlistId}-bulk-account-id`}
            type="number"
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
          />
        </div>
        <div className="form-row">
          <label htmlFor={`watchlist-${watchlistId}-bulk-status`}>status</label>
          <select
            id={`watchlist-${watchlistId}-bulk-status`}
            value={status}
            onChange={(e) => setStatus(e.target.value as StrategyVersionStatus)}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
      </div>

      <p className="section-description">{t.watchlists.autoTradeBulkDisabledHint}</p>

      <div className="actions">
        <button className="primary" disabled={!canSubmit} onClick={() => bulkMutation.mutate()}>
          {t.watchlists.bulkCreate}
        </button>
      </div>

      {bulkMutation.isError && (
        <p className="action-result value error">
          {(bulkMutation.error as Error)?.message ?? t.watchlists.bulkCreateFailed}
        </p>
      )}

      {bulkMutation.isSuccess && (
        <div className="action-result">
          <h4>{t.watchlists.bulkResultTitle}</h4>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>{t.watchlists.colSymbolCode}</th>
                  <th>{t.watchlists.colSymbolName}</th>
                  <th>{t.watchlists.bulkResultTitle}</th>
                  <th>strategy_version_id</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {bulkMutation.data.items.map((item) => (
                  <tr key={item.symbol_code}>
                    <td>{item.symbol_code}</td>
                    <td>{item.symbol_name ?? "-"}</td>
                    <td>
                      <span className={`pill ${item.created ? "off" : "on"}`}>
                        {item.created ? t.watchlists.bulkResultCreated : t.watchlists.bulkResultSkipped}
                      </span>
                    </td>
                    <td>{item.strategy_version_id ?? "-"}</td>
                    <td>{item.reason ? t.watchlists.bulkResultReason[item.reason] ?? item.reason : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
