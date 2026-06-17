import { useQuery } from "@tanstack/react-query";
import { getVersionPerformance } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";

interface Props {
  strategyId: number;
  versionId: number;
}

function fmtWinRate(val: string | null): string {
  if (val === null) return "-";
  return (parseFloat(val) * 100).toFixed(1) + "%";
}

function fmtSignedPct(val: string | null): string {
  if (val === null) return "-";
  const n = parseFloat(val);
  if (isNaN(n)) return "-";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function fmtPnl(val: string): string {
  const n = parseFloat(val);
  if (isNaN(n)) return val;
  return n.toLocaleString("ko-KR") + "원";
}

export default function StrategyVersionPerformancePanel({ strategyId, versionId }: Props) {
  const { t } = useSettings();
  const tp = t.performance;

  const { data, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ["version-performance", strategyId, versionId],
    queryFn: () => getVersionPerformance(strategyId, versionId),
    retry: false,
  });

  const refreshBtn = (
    <button
      className="outcome-refresh-btn"
      onClick={() => refetch()}
      disabled={isFetching}
    >
      {isFetching ? "..." : tp.refresh}
    </button>
  );

  if (isLoading) {
    return (
      <div className="outcome-panel">
        <p className="muted">{tp.loading}</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="outcome-panel">
        <p className="value error">{tp.loadError}</p>
        {refreshBtn}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="outcome-panel perf-panel">
      <div className="perf-overview">
        <span className="perf-stat">
          <strong>{tp.totalSignals}:</strong> {data.total_signals}
        </span>
        <span className="perf-stat">
          <strong>{tp.analyzedSignals}:</strong> {data.analyzed_signals}
        </span>
        <span className="perf-stat muted">
          <strong>{tp.skippedSignals}:</strong> {data.skipped_signals}
        </span>
        {refreshBtn}
      </div>

      {data.analyzed_signals > 0 && (
        <>
          <h5 className="perf-section-title">{tp.horizonTitle}</h5>
          <table className="outcome-table">
            <thead>
              <tr>
                <th>{tp.colHorizon}</th>
                <th>{tp.colCount}</th>
                <th>{tp.colWinRate}</th>
                <th>{tp.colAvgDirectional}</th>
                <th>{tp.colMfe}</th>
                <th>{tp.colMae}</th>
              </tr>
            </thead>
            <tbody>
              {data.by_horizon.map((h) => {
                const wr = parseFloat(h.win_rate);
                const dir = parseFloat(h.avg_directional_return_pct);
                return (
                  <tr key={h.horizon_minutes}>
                    <td>{h.horizon_minutes}m</td>
                    <td>{h.count}</td>
                    <td className={h.count > 0 ? (wr >= 0.5 ? "value ok" : "value error") : ""}>
                      {h.count > 0 ? fmtWinRate(h.win_rate) : "-"}
                    </td>
                    <td className={h.count > 0 ? (dir >= 0 ? "value ok" : "value error") : ""}>
                      {h.count > 0 ? fmtSignedPct(h.avg_directional_return_pct) : "-"}
                    </td>
                    <td>{fmtSignedPct(h.avg_mfe_pct)}</td>
                    <td>{fmtSignedPct(h.avg_mae_pct)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {data.by_signal_type.length > 0 && (
            <>
              <h5 className="perf-section-title">{tp.signalTypeTitle}</h5>
              <table className="outcome-table">
                <thead>
                  <tr>
                    <th>{tp.colSignalType}</th>
                    <th>{tp.colSignalCount}</th>
                    <th>{tp.colAnalyzedCount}</th>
                    <th>{tp.colWinRate5m}</th>
                    <th>{tp.colAvgDir5m}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_signal_type.map((st) => (
                    <tr key={st.signal_type}>
                      <td>{st.signal_type === "buy" ? t.common.buy : t.common.sell}</td>
                      <td>{st.signal_count}</td>
                      <td>{st.analyzed_count}</td>
                      <td>{fmtWinRate(st.win_rate_5m)}</td>
                      <td>{fmtSignedPct(st.avg_directional_return_pct_5m)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          {data.by_symbol.length > 0 && (
            <>
              <h5 className="perf-section-title">{tp.symbolTitle}</h5>
              <table className="outcome-table">
                <thead>
                  <tr>
                    <th>{tp.colSymbol}</th>
                    <th>{tp.colSignalCount}</th>
                    <th>{tp.colAnalyzedCount}</th>
                    <th>{tp.colWinRate5m}</th>
                    <th>{tp.colAvgDir5m}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_symbol.slice(0, 10).map((sym) => (
                    <tr key={sym.symbol_code}>
                      <td>{sym.symbol_code}</td>
                      <td>{sym.signal_count}</td>
                      <td>{sym.analyzed_count}</td>
                      <td>{fmtWinRate(sym.win_rate_5m)}</td>
                      <td>{fmtSignedPct(sym.avg_directional_return_pct_5m)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}

      {data.analyzed_signals === 0 && (
        <p className="muted">{tp.noSignalData}</p>
      )}

      {data.actual_trading && (
        <div className="perf-trading">
          <h5 className="perf-section-title">{tp.tradingTitle}</h5>
          <div className="perf-trading-grid">
            <span>
              <strong>{tp.tradeCount}:</strong> {data.actual_trading.trade_count}
            </span>
            <span>
              <strong>{tp.filledCount}:</strong> {data.actual_trading.filled_count}
            </span>
            {data.actual_trading.total_pnl_amount !== null ? (
              <>
                <span>
                  <strong>{tp.totalPnl}:</strong>{" "}
                  <span
                    className={
                      parseFloat(data.actual_trading.total_pnl_amount) >= 0
                        ? "value ok"
                        : "value error"
                    }
                  >
                    {fmtPnl(data.actual_trading.total_pnl_amount)}
                  </span>
                </span>
                {data.actual_trading.win_trade_count !== null && (
                  <span>
                    <strong>{tp.winTrades}:</strong> {data.actual_trading.win_trade_count}
                  </span>
                )}
                {data.actual_trading.loss_trade_count !== null && (
                  <span>
                    <strong>{tp.lossTrades}:</strong> {data.actual_trading.loss_trade_count}
                  </span>
                )}
              </>
            ) : (
              <span className="muted">{tp.noPnlData}</span>
            )}
          </div>
          <p className="muted perf-note">{data.actual_trading.note}</p>
        </div>
      )}
    </div>
  );
}
