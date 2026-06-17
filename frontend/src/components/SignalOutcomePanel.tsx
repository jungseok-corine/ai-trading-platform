import { useQuery } from "@tanstack/react-query";
import { getSignalOutcome } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";
import { formatPrice } from "../utils/format";
import type { SignalOutcomeHorizonResult } from "../types";

const HORIZONS = [5, 15, 30, 60];

function formatSignedPct(val: string | null): string {
  if (val === null) return "N/A";
  const n = parseFloat(val);
  if (isNaN(n)) return "N/A";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function HorizonCell({ h }: { h: SignalOutcomeHorizonResult }) {
  const { t } = useSettings();
  if (!h.available || h.directional_return_pct === null) {
    return (
      <td className="muted" style={{ textAlign: "center" }}>
        {t.signalOutcome.na}
      </td>
    );
  }
  const val = parseFloat(h.directional_return_pct);
  const cls = val > 0 ? "value ok" : val < 0 ? "value error" : "muted";
  return (
    <td style={{ textAlign: "center" }}>
      <span className={cls} style={{ fontSize: 12 }}>
        {formatSignedPct(h.directional_return_pct)}
      </span>
      <span
        style={{
          marginLeft: 4,
          fontSize: 10,
          color: h.is_win ? "#1a7f37" : "#cf222e",
          fontWeight: 600,
        }}
      >
        {h.is_win ? t.signalOutcome.win : t.signalOutcome.loss}
      </span>
    </td>
  );
}

export default function SignalOutcomePanel({ signalId }: { signalId: number }) {
  const { t } = useSettings();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["signal-outcome", signalId],
    queryFn: () => getSignalOutcome(signalId),
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="outcome-panel">
        <span className="muted">{t.common.loading}</span>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="outcome-panel">
        <span className="muted">{t.common.loadError}</span>
      </div>
    );
  }

  if (!data) return null;

  if (!data.available) {
    return (
      <div className="outcome-panel">
        <span className="muted">{data.note ?? t.signalOutcome.noData}</span>
      </div>
    );
  }

  return (
    <div className="outcome-panel">
      <div className="outcome-meta">
        {data.entry_price !== null && (
          <span className="muted">
            {t.signalOutcome.entryPrice}: <strong>{formatPrice(data.entry_price)}</strong>
          </span>
        )}
        {data.mfe_pct !== null && (
          <span className="muted" style={{ marginLeft: 12 }}>
            {t.signalOutcome.mfe}: <span className="value ok">+{parseFloat(data.mfe_pct).toFixed(2)}%</span>
          </span>
        )}
        {data.mae_pct !== null && (
          <span className="muted" style={{ marginLeft: 12 }}>
            {t.signalOutcome.mae}: <span className="value error">-{parseFloat(data.mae_pct).toFixed(2)}%</span>
          </span>
        )}
      </div>
      <table className="outcome-table">
        <thead>
          <tr>
            {HORIZONS.map((h) => (
              <th key={h} style={{ textAlign: "center", fontWeight: 500, fontSize: 11, color: "#888" }}>
                {h}{t.signalOutcome.colHorizonMin}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            {HORIZONS.map((h) => {
              const hr = data.horizons.find((r) => r.horizon_minutes === h);
              if (!hr) {
                return (
                  <td key={h} className="muted" style={{ textAlign: "center" }}>
                    {t.signalOutcome.na}
                  </td>
                );
              }
              return <HorizonCell key={h} h={hr} />;
            })}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
