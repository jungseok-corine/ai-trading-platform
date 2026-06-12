import { useQuery } from "@tanstack/react-query";
import { getSignals } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";

export default function SignalsTable() {
  const { t, formatDateTime } = useSettings();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["signals"],
    queryFn: getSignals,
  });

  return (
    <div className="card">
      <h2>{t.signals.title}</h2>
      <p className="section-description">{t.signals.description}</p>
      {isLoading && <p className="muted">{t.common.loading}</p>}
      {isError && <p className="value error">{(error as Error)?.message ?? t.common.loadError}</p>}
      {data && data.length === 0 && <p className="muted">{t.signals.empty}</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t.signals.colId}</th>
                <th>{t.signals.colSymbol}</th>
                <th>{t.signals.colType}</th>
                <th>{t.signals.colShortMa}</th>
                <th>{t.signals.colLongMa}</th>
                <th>{t.signals.colReason}</th>
                <th>{t.signals.colGeneratedAt}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((signal) => (
                <tr key={signal.id}>
                  <td>{signal.id}</td>
                  <td>{signal.symbol_code}</td>
                  <td>
                    <span className={`badge side-${signal.signal_type}`}>
                      {signal.signal_type === "buy" ? t.common.buy : t.common.sell}
                    </span>
                  </td>
                  <td>{signal.short_ma ?? "-"}</td>
                  <td>{signal.long_ma ?? "-"}</td>
                  <td>{signal.reason ?? "-"}</td>
                  <td>{formatDateTime(signal.generated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
