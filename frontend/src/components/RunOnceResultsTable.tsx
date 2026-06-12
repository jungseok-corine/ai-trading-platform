import type { StrategyRunResult } from "../types";

function describeResult(result: StrategyRunResult): string {
  if (!result.signal_created) {
    return "신호 없음 (매수/매도 조건 미충족)";
  }
  if (!result.auto_trade_enabled) {
    return "신호만 생성됨 / 자동주문 비활성화 (auto_trade_enabled=false)";
  }
  if (!result.trade_attempted) {
    return result.error ? `자동주문 미실행: ${result.error}` : "자동주문 미실행";
  }
  if (result.trade_approved === true) {
    return `주문 승인됨 (trade_id=${result.trade_id ?? "-"})`;
  }
  if (result.trade_approved === false) {
    return `주문 거부됨${result.rejection_reason ? `: ${result.rejection_reason}` : ""}`;
  }
  return result.error ? `주문 오류: ${result.error}` : "주문 처리 중 오류";
}

export default function RunOnceResultsTable({ results }: { results: StrategyRunResult[] }) {
  if (results.length === 0) {
    return <p className="muted">실행할 활성 전략이 없습니다.</p>;
  }

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Strategy Version</th>
            <th>Symbol</th>
            <th>Signal</th>
            <th>Auto Trade</th>
            <th>결과</th>
          </tr>
        </thead>
        <tbody>
          {results.map((result, i) => (
            <tr key={`${result.strategy_version_id ?? "unknown"}-${i}`}>
              <td>{result.strategy_version_id ?? "-"}</td>
              <td>{result.symbol_code}</td>
              <td>{result.signal_created ? `생성됨 (id=${result.signal_id ?? "-"})` : "없음"}</td>
              <td>
                <span className={`pill ${result.auto_trade_enabled ? "on" : "off"}`}>
                  {result.auto_trade_enabled ? "ON" : "OFF"}
                </span>
              </td>
              <td>{describeResult(result)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
