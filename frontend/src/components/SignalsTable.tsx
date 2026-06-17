import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getSignals } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";
import SignalOutcomePanel from "./SignalOutcomePanel";

export default function SignalsTable() {
  const { t, formatDateTime } = useSettings();
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["signals"],
    queryFn: getSignals,
  });

  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

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
                <th>{t.signalOutcome.panelTitle}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((signal) => (
                <React.Fragment key={signal.id}>
                  <tr>
                    <td>{signal.id}</td>
                    <td>
                      {signal.symbol_display ??
                        (signal.symbol_name
                          ? `${signal.symbol_name} (${signal.symbol_code})`
                          : signal.symbol_code)}
                    </td>
                    <td>
                      <span className={`badge side-${signal.signal_type}`}>
                        {signal.signal_type === "buy" ? t.common.buy : t.common.sell}
                      </span>
                    </td>
                    <td>{signal.short_ma ?? "-"}</td>
                    <td>{signal.long_ma ?? "-"}</td>
                    <td>{signal.reason ?? "-"}</td>
                    <td>{formatDateTime(signal.generated_at)}</td>
                    <td>
                      <button
                        className="outcome-expand-btn"
                        onClick={() => toggleExpand(signal.id)}
                      >
                        {expandedIds.has(signal.id)
                          ? t.signalOutcome.hideOutcome
                          : t.signalOutcome.showOutcome}
                      </button>
                    </td>
                  </tr>
                  {expandedIds.has(signal.id) && (
                    <tr>
                      <td
                        colSpan={8}
                        style={{ padding: 0, background: "#f8f9fa", borderBottom: "1px solid #e0e0e0" }}
                      >
                        <SignalOutcomePanel signalId={signal.id} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
