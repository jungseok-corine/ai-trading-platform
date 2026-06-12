import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getPortfolioSummary, refreshAllPrices } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";

type AutoRefreshOption = "off" | "30" | "60";

export default function PortfolioSummaryCard() {
  const { t, formatDateTime, accountId, setAccountId } = useSettings();
  const queryClient = useQueryClient();
  const [autoRefresh, setAutoRefresh] = useState<AutoRefreshOption>("off");
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["portfolio-summary", accountId],
    queryFn: () => getPortfolioSummary(accountId),
  });

  const refreshMutation = useMutation({
    mutationFn: () => refreshAllPrices(accountId),
    onSuccess: () => {
      setLastRefreshedAt(new Date().toISOString());
      queryClient.invalidateQueries({ queryKey: ["positions"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-summary", accountId] });
    },
  });

  useEffect(() => {
    if (autoRefresh === "off") return;
    const intervalMs = Number(autoRefresh) * 1000;
    const id = window.setInterval(() => {
      refreshMutation.mutate();
    }, intervalMs);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, accountId]);

  return (
    <div className="card">
      <h2>{t.portfolio.title}</h2>
      <div className="form-row">
        <label htmlFor="portfolio-account-id">{t.risk.accountId}</label>
        <input
          id="portfolio-account-id"
          type="text"
          inputMode="numeric"
          value={String(accountId)}
          onChange={(e) => {
            const next = e.target.value;
            if (/^\d+$/.test(next) && Number(next) > 0) {
              setAccountId(Number(next));
            }
          }}
        />
      </div>

      {isLoading && <p className="muted">{t.common.loading}</p>}
      {isError && <p className="value error">{(error as Error)?.message ?? t.common.loadError}</p>}

      {data && (
        <div className="status-grid">
          <div className="status-item">
            <span className="label">{t.portfolio.positionCount}</span>
            <span className="value">{data.position_count}</span>
          </div>
          <div className="status-item">
            <span className="label">{t.portfolio.totalQuantity}</span>
            <span className="value">{data.total_quantity}</span>
          </div>
          <div className="status-item">
            <span className="label">{t.portfolio.totalCostAmount}</span>
            <span className="value">{data.total_cost_amount}</span>
          </div>
          <div className="status-item">
            <span className="label">{t.portfolio.totalEvalAmount}</span>
            <span className="value">{data.total_eval_amount}</span>
          </div>
          <div className="status-item">
            <span className="label">{t.portfolio.totalUnrealizedPnl}</span>
            <span className={`value ${Number(data.total_unrealized_pnl) >= 0 ? "ok" : "error"}`}>
              {data.total_unrealized_pnl}
            </span>
          </div>
          <div className="status-item">
            <span className="label">{t.portfolio.totalUnrealizedPnlPct}</span>
            <span className={`value ${Number(data.total_unrealized_pnl_pct) >= 0 ? "ok" : "error"}`}>
              {data.total_unrealized_pnl_pct}%
            </span>
          </div>
          <div className="status-item">
            <span className="label">{t.portfolio.totalRealizedPnl}</span>
            <span className={`value ${Number(data.total_realized_pnl) >= 0 ? "ok" : "error"}`}>
              {data.total_realized_pnl}
            </span>
          </div>
          <div className="status-item">
            <span className="label">{t.portfolio.totalPnl}</span>
            <span className={`value ${Number(data.total_pnl) >= 0 ? "ok" : "error"}`}>
              {data.total_pnl}
            </span>
          </div>
        </div>
      )}

      <div className="actions" style={{ marginTop: 16 }}>
        <button
          className="primary"
          disabled={refreshMutation.isPending}
          onClick={() => refreshMutation.mutate()}
        >
          {refreshMutation.isPending ? t.portfolio.refreshing : t.portfolio.refreshPrices}
        </button>
        <label className="auto-refresh-select">
          {t.portfolio.autoRefresh}
          <select value={autoRefresh} onChange={(e) => setAutoRefresh(e.target.value as AutoRefreshOption)}>
            <option value="off">{t.portfolio.autoRefreshOff}</option>
            <option value="30">{t.portfolio.autoRefresh30s}</option>
            <option value="60">{t.portfolio.autoRefresh60s}</option>
          </select>
        </label>
        {lastRefreshedAt && (
          <span className="muted">
            {t.portfolio.lastRefreshedAt}: {formatDateTime(lastRefreshedAt)}
          </span>
        )}
      </div>
      {refreshMutation.isError && (
        <p className="action-result value error">
          {(refreshMutation.error as Error)?.message ?? t.portfolio.refreshFailed}
        </p>
      )}
      <p className="section-description">{t.portfolio.disclaimer}</p>
    </div>
  );
}
