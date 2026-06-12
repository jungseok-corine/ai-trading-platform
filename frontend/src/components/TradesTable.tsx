import { useQuery } from "@tanstack/react-query";
import { getSchedulerRuns, getTrades } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";

const PENDING_STATUSES = new Set(["pending", "partial"]);

function ageMinutesSince(isoTime: string): number {
  return Math.max(0, Math.floor((Date.now() - new Date(isoTime).getTime()) / 60000));
}

export default function TradesTable() {
  const { t, formatDateTime } = useSettings();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["trades"],
    queryFn: getTrades,
  });
  const { data: schedulerRuns } = useQuery({
    queryKey: ["scheduler-runs"],
    queryFn: () => getSchedulerRuns(20),
  });

  const latestOrderSyncRun = schedulerRuns?.find((run) => run.job_id === "order_sync");
  const unmatchedOrderIds = new Set(latestOrderSyncRun?.summary?.unmatched_order_ids ?? []);

  return (
    <div className="card">
      <h2>{t.trades.title}</h2>
      <p className="section-description">{t.trades.description}</p>
      {isLoading && <p className="muted">{t.common.loading}</p>}
      {isError && <p className="value error">{(error as Error)?.message ?? t.common.loadError}</p>}
      {data && data.length === 0 && <p className="muted">{t.trades.empty}</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t.trades.colId}</th>
                <th>{t.trades.colSymbol}</th>
                <th>{t.trades.colSide}</th>
                <th>{t.trades.colOrderStatus}</th>
                <th>{t.trades.colBrokerOrder}</th>
                <th>{t.trades.colQuantity}</th>
                <th>{t.trades.colEntryPrice}</th>
                <th>{t.trades.colExitPrice}</th>
                <th>{t.trades.colPositionAppliedQty}</th>
                <th>{t.trades.colCreatedAt}</th>
                <th>{t.trades.colAge}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((trade) => (
                <tr key={trade.id}>
                  <td>{trade.id}</td>
                  <td>{trade.symbol_code}</td>
                  <td>
                    <span className={`badge side-${trade.side}`}>
                      {trade.side === "buy" ? t.common.buy : t.common.sell}
                    </span>
                  </td>
                  <td>
                    <span className={`badge order-status-${trade.order_status}`}>
                      {t.orderStatus[trade.order_status]}
                    </span>
                  </td>
                  <td>
                    {trade.broker_order_id ? (
                      <>
                        <span className="badge order-status-filled">{t.trades.brokerOrderPresent}</span>
                        <div className="muted">{trade.broker_order_id}</div>
                        {PENDING_STATUSES.has(trade.order_status) &&
                          unmatchedOrderIds.has(trade.broker_order_id) && (
                            <div className="value error">{t.trades.unmatchedIndicator}</div>
                          )}
                      </>
                    ) : (
                      <span className="badge neutral">{t.trades.brokerOrderAbsent}</span>
                    )}
                  </td>
                  <td>
                    <strong>{trade.quantity}</strong>
                  </td>
                  <td>
                    <strong>{trade.entry_price ?? "-"}</strong>
                  </td>
                  <td>{trade.exit_price ?? "-"}</td>
                  <td>{trade.position_applied_quantity}</td>
                  <td>{formatDateTime(trade.created_at)}</td>
                  <td>
                    {PENDING_STATUSES.has(trade.order_status)
                      ? t.trades.ageMinutes(ageMinutesSince(trade.created_at))
                      : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
