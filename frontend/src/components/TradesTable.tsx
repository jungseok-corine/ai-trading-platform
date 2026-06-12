import { useQuery } from "@tanstack/react-query";
import { getTrades } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";

export default function TradesTable() {
  const { t, formatDateTime } = useSettings();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["trades"],
    queryFn: getTrades,
  });

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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
