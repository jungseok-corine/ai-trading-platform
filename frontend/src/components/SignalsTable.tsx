import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getSignals } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";
import SignalOutcomePanel from "./SignalOutcomePanel";
import { formatPrice } from "../utils/format";

const PAGE_SIZE = 50;

export default function SignalsTable() {
  const { t, formatDateTime } = useSettings();
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const [page, setPage] = useState(0);
  const [filterSymbol, setFilterSymbol] = useState("");
  const [filterType, setFilterType] = useState<"" | "buy" | "sell">("");
  const [filterDateFrom, setFilterDateFrom] = useState("");
  const [filterDateTo, setFilterDateTo] = useState("");

  const params = {
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    signal_type: filterType || null,
    symbol_code: filterSymbol.trim() || null,
    date_from: filterDateFrom || null,
    date_to: filterDateTo ? `${filterDateTo}T23:59:59` : null,
  };

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["signals", params],
    queryFn: () => getSignals(params),
  });

  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleFilterChange = () => {
    setPage(0);
  };

  const hasMore = (data?.length ?? 0) === PAGE_SIZE;

  return (
    <div className="card">
      <h2>{t.signals.title}</h2>
      <p className="section-description">{t.signals.description}</p>

      <div className="filter-row" style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <input
          type="text"
          placeholder={t.signals.filterSymbol}
          value={filterSymbol}
          onChange={(e) => { setFilterSymbol(e.target.value); handleFilterChange(); }}
          style={{ width: 120 }}
        />
        <select
          value={filterType}
          onChange={(e) => { setFilterType(e.target.value as "" | "buy" | "sell"); handleFilterChange(); }}
        >
          <option value="">{t.signals.filterAll}</option>
          <option value="buy">{t.signals.filterBuy}</option>
          <option value="sell">{t.signals.filterSell}</option>
        </select>
        <input
          type="date"
          title={t.signals.filterDateFrom}
          value={filterDateFrom}
          onChange={(e) => { setFilterDateFrom(e.target.value); handleFilterChange(); }}
        />
        <span className="muted" style={{ lineHeight: "30px" }}>~</span>
        <input
          type="date"
          title={t.signals.filterDateTo}
          value={filterDateTo}
          onChange={(e) => { setFilterDateTo(e.target.value); handleFilterChange(); }}
        />
        {(filterSymbol || filterType || filterDateFrom || filterDateTo) && (
          <button
            onClick={() => {
              setFilterSymbol("");
              setFilterType("");
              setFilterDateFrom("");
              setFilterDateTo("");
              setPage(0);
            }}
          >
            ✕
          </button>
        )}
      </div>

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
                <th>{t.signals.colSignalPrice}</th>
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
                    <td>{signal.signal_price != null ? formatPrice(signal.signal_price) : "-"}</td>
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
                        colSpan={9}
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

      <div className="pagination-row" style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
        <button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
          {t.signals.pagePrev}
        </button>
        <span className="muted">
          {t.signals.pageInfo(page + 1, data?.length ?? 0)}
        </span>
        <button disabled={!hasMore} onClick={() => setPage((p) => p + 1)}>
          {t.signals.pageNext}
        </button>
      </div>
    </div>
  );
}
