import { useQuery } from "@tanstack/react-query";
import { getTrades } from "../api/client";

export default function TradesTable() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["trades"],
    queryFn: getTrades,
  });

  return (
    <div className="card">
      <h2>Trades</h2>
      {isLoading && <p className="muted">불러오는 중...</p>}
      {isError && <p className="value error">{(error as Error)?.message ?? "조회 실패"}</p>}
      {data && data.length === 0 && <p className="muted">거래 내역이 없습니다.</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Quantity</th>
                <th>Entry Price</th>
                <th>Exit Price</th>
                <th>Order Status</th>
                <th>Broker Order ID</th>
                <th>Position Applied Qty</th>
                <th>Created At</th>
              </tr>
            </thead>
            <tbody>
              {data.map((trade) => (
                <tr key={trade.id}>
                  <td>{trade.id}</td>
                  <td>{trade.symbol_code}</td>
                  <td>{trade.side}</td>
                  <td>{trade.quantity}</td>
                  <td>{trade.entry_price ?? "-"}</td>
                  <td>{trade.exit_price ?? "-"}</td>
                  <td>{trade.order_status}</td>
                  <td>{trade.broker_order_id ?? "-"}</td>
                  <td>{trade.position_applied_quantity}</td>
                  <td>{trade.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
