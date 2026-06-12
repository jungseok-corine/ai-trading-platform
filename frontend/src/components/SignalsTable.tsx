import { useQuery } from "@tanstack/react-query";
import { getSignals } from "../api/client";

export default function SignalsTable() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["signals"],
    queryFn: getSignals,
  });

  return (
    <div className="card">
      <h2>Signals</h2>
      <p className="section-description">
        전략이 생성한 매수/매도 신호입니다. 실제 주문이 실행됐다는 뜻은 아니며, auto_trade_enabled=false인
        전략은 신호만 기록되고 자동 주문은 실행되지 않습니다.
      </p>
      {isLoading && <p className="muted">불러오는 중...</p>}
      {isError && <p className="value error">{(error as Error)?.message ?? "조회 실패"}</p>}
      {data && data.length === 0 && <p className="muted">생성된 시그널이 없습니다.</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Symbol</th>
                <th>Type</th>
                <th>Short MA</th>
                <th>Long MA</th>
                <th>Reason</th>
                <th>Generated At</th>
              </tr>
            </thead>
            <tbody>
              {data.map((signal) => (
                <tr key={signal.id}>
                  <td>{signal.id}</td>
                  <td>{signal.symbol_code}</td>
                  <td>{signal.signal_type}</td>
                  <td>{signal.short_ma ?? "-"}</td>
                  <td>{signal.long_ma ?? "-"}</td>
                  <td>{signal.reason ?? "-"}</td>
                  <td>{signal.generated_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
