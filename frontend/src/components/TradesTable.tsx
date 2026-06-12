import { useQuery } from "@tanstack/react-query";
import { getTrades } from "../api/client";
import type { OrderStatus } from "../types";

const ORDER_STATUS_LABEL: Record<OrderStatus, string> = {
  pending: "PENDING",
  filled: "FILLED",
  partial: "PARTIAL",
  cancelled: "CANCELLED",
  rejected: "REJECTED",
};

export default function TradesTable() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["trades"],
    queryFn: getTrades,
  });

  return (
    <div className="card">
      <h2>Trades</h2>
      <p className="section-description">
        KIS VTS로 주문이 전송되었거나 주문 기록으로 저장된 실제 거래 시도 내역입니다.
      </p>
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
                <th>Order Status</th>
                <th>Broker Order</th>
                <th>Quantity</th>
                <th>Entry Price</th>
                <th>Exit Price</th>
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
                  <td>
                    <span className={`badge order-status-${trade.order_status}`}>
                      {ORDER_STATUS_LABEL[trade.order_status]}
                    </span>
                  </td>
                  <td>
                    {trade.broker_order_id ? (
                      <>
                        <span className="badge order-status-filled">KIS 주문번호 있음</span>
                        <div className="muted">{trade.broker_order_id}</div>
                      </>
                    ) : (
                      <span className="badge neutral">주문 미전송</span>
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
