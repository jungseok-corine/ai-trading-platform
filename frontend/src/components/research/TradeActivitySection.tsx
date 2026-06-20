import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getTradeActivity } from "../../api/research";
import type { TradeBucket } from "../../api/research";

const DAY_OPTIONS = [7, 30, 90];

function pnl(n: number): string {
  const s = `₩${Math.round(Math.abs(n)).toLocaleString()}`;
  return n >= 0 ? `+${s}` : `-${s}`;
}

function cells(b: TradeBucket) {
  return (
    <>
      <td>{b.trades}</td>
      <td>{b.closed}</td>
      <td>{b.wins}/{b.losses}</td>
      <td>{b.win_rate !== null ? `${b.win_rate}%` : "-"}</td>
      <td>{pnl(b.total_pnl)}</td>
      <td>{b.avg_pnl !== null ? pnl(b.avg_pnl) : "-"}</td>
    </>
  );
}

export default function TradeActivitySection() {
  const [days, setDays] = useState(30);
  const { data, isLoading } = useQuery({
    queryKey: ["trade-activity", days],
    queryFn: () => getTradeActivity(days),
  });

  return (
    <div className="card">
      <h3>거래 활동 요약</h3>
      <p className="muted">
        최근 거래의 건수·승패·손익을 전체/전략별로 봅니다. 청산 손익이 기록된 거래만 승패·손익에
        반영합니다(미청산은 건수만). read-only 집계입니다.
      </p>
      <div className="sub-nav">
        {DAY_OPTIONS.map((d) => (
          <button key={d} className={days === d ? "primary" : undefined}
            onClick={() => setDays(d)}>최근 {d}일</button>
        ))}
      </div>

      {isLoading && <p className="muted">불러오는 중…</p>}
      {data && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>구분</th><th>거래</th><th>청산</th><th>승/패</th>
                <th>승률</th><th>총손익</th><th>평균손익</th>
              </tr>
            </thead>
            <tbody>
              <tr><td><strong>전체</strong></td>{cells(data.overall)}</tr>
              {data.by_strategy.map((s) => (
                <tr key={s.strategy_version_id ?? "none"}>
                  <td>{s.label}</td>{cells(s)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
