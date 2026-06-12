import { useQuery } from "@tanstack/react-query";
import { getPositions } from "../api/client";

export default function PositionsTable() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["positions"],
    queryFn: getPositions,
  });

  return (
    <div className="card">
      <h2>Positions</h2>
      <p className="section-description">체결 동기화 후 반영된 현재 보유 포지션과 손익입니다.</p>
      {isLoading && <p className="muted">불러오는 중...</p>}
      {isError && <p className="value error">{(error as Error)?.message ?? "조회 실패"}</p>}
      {data && data.length === 0 && <p className="muted">보유 포지션이 없습니다.</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Quantity</th>
                <th>Avg Entry Price</th>
                <th>Realized PnL</th>
                <th>Unrealized PnL</th>
                <th>Last Price</th>
                <th>Updated At</th>
              </tr>
            </thead>
            <tbody>
              {data.map((position) => (
                <tr key={position.id}>
                  <td>{position.symbol_name ? `${position.symbol_code} (${position.symbol_name})` : position.symbol_code}</td>
                  <td>{position.quantity}</td>
                  <td>{position.avg_entry_price}</td>
                  <td>{position.realized_pnl}</td>
                  <td>{position.unrealized_pnl}</td>
                  <td>{position.last_price ?? "-"}</td>
                  <td>{position.updated_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
