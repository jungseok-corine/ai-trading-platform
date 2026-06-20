import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getTradeActivity, getEquityCurve } from "../../api/research";
import type { TradeBucket, EquityPoint } from "../../api/research";

function EquityChart({ points }: { points: EquityPoint[] }) {
  if (points.length < 2) return <p className="muted">에쿼티 곡선을 그리려면 2일 이상 거래가 필요합니다.</p>;
  const w = 560, h = 120, pad = 4;
  const vals = points.map((p) => p.cumulative_pnl);
  const min = Math.min(0, ...vals), max = Math.max(0, ...vals);
  const span = max - min || 1;
  const x = (i: number) => pad + (i / (points.length - 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - ((v - min) / span) * (h - 2 * pad);
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.cumulative_pnl).toFixed(1)}`).join(" ");
  const last = vals[vals.length - 1];
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="에쿼티 곡선">
      <line x1={pad} y1={y(0)} x2={w - pad} y2={y(0)} stroke="#555" strokeDasharray="3 3" />
      <path d={d} fill="none" stroke={last >= 0 ? "#2e9e5b" : "#c0392b"} strokeWidth="2" />
    </svg>
  );
}

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
  const { data: equity } = useQuery({
    queryKey: ["equity-curve", days],
    queryFn: () => getEquityCurve(days),
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

      {equity && equity.length > 0 && (
        <>
          <h4>누적 손익(에쿼티)</h4>
          <EquityChart points={equity} />
        </>
      )}

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
