import { useQuery } from "@tanstack/react-query";
import { getOutcomesSummary } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";

function formatWinRate(val: string): string {
  const n = parseFloat(val);
  if (isNaN(n)) return "-";
  return `${(n * 100).toFixed(1)}%`;
}

function formatSignedPct(val: string): string {
  const n = parseFloat(val);
  if (isNaN(n)) return "-";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

export default function SignalOutcomeSummaryCard() {
  const { t } = useSettings();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["outcomes-summary"],
    queryFn: () => getOutcomesSummary(100),
  });

  return (
    <div className="card">
      <h2>{t.signalOutcome.summaryTitle}</h2>
      <p className="section-description">{t.signalOutcome.summaryDescription}</p>

      {isLoading && <p className="muted">{t.common.loading}</p>}
      {isError && <p className="value error">{t.common.loadError}</p>}

      {data && (
        <>
          <div style={{ display: "flex", gap: 16, marginBottom: 12, flexWrap: "wrap" }}>
            <span className="muted">
              {t.signalOutcome.analyzedCount}:{" "}
              <strong style={{ color: "#1a1a1a" }}>
                {data.analyzed_count} / {data.total_signals}
              </strong>
            </span>
            {data.skipped_count > 0 && (
              <span className="muted">
                {t.signalOutcome.skippedCount}: {data.skipped_count}
              </span>
            )}
          </div>

          {data.analyzed_count === 0 && (
            <p className="muted">{t.signalOutcome.noSummary}</p>
          )}

          {data.analyzed_count > 0 && (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>{t.signalOutcome.colHorizonMin}</th>
                    <th>{t.signalOutcome.colCount}</th>
                    <th>{t.signalOutcome.colWinRate}</th>
                    <th>{t.signalOutcome.colAvgReturn}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_horizon.map((h) => {
                    const winRateNum = parseFloat(h.win_rate);
                    const avgRetNum = parseFloat(h.avg_return_pct);
                    return (
                      <tr key={h.horizon_minutes}>
                        <td>{h.horizon_minutes}{t.signalOutcome.colHorizonMin}</td>
                        <td>{h.count}</td>
                        <td>
                          {h.count === 0 ? (
                            <span className="muted">-</span>
                          ) : (
                            <span className={winRateNum >= 0.5 ? "value ok" : "value error"}>
                              {formatWinRate(h.win_rate)}
                            </span>
                          )}
                        </td>
                        <td>
                          {h.count === 0 ? (
                            <span className="muted">-</span>
                          ) : (
                            <span className={avgRetNum >= 0 ? "value ok" : "value error"}>
                              {formatSignedPct(h.avg_return_pct)}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
