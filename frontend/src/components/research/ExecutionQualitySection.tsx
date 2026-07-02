// C-6.9: 체결 품질 — 신호가 vs 체결가 슬리피지·지연 집계 (read-only, 실전 준비도 근거)
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getExecutionQuality } from "../../api/research";

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${v.toFixed(3)}%`;
}

export default function ExecutionQualitySection() {
  const [days, setDays] = useState(30);
  const { data, isLoading, error } = useQuery({
    queryKey: ["execution-quality", days],
    queryFn: () => getExecutionQuality(days),
  });

  return (
    <div className="card">
      <h3>체결 품질 (슬리피지)</h3>
      <p className="muted">
        신호 가격 대비 실제 체결 가격의 차이. 양수 = 불리한 체결 (BUY는 비싸게, SELL은 싸게).
        실전 배치 판단의 근거 지표 — 조회 전용.
      </p>
      <div className="form-row">
        {[7, 30, 90].map((d) => (
          <button key={d} className={days === d ? "primary" : undefined} onClick={() => setDays(d)}>
            최근 {d}일
          </button>
        ))}
      </div>
      {isLoading && <p className="muted">불러오는 중…</p>}
      {error != null && <p className="error">조회 실패</p>}
      {data && data.pair_count === 0 && (
        <p className="muted">이 기간에 신호-체결 쌍이 없습니다 (자동매매 체결 기록 필요).</p>
      )}
      {data && data.pair_count > 0 && (
        <>
          <table className="compact-table">
            <thead>
              <tr>
                <th></th>
                <th>건수</th>
                <th>평균</th>
                <th>중앙값</th>
                <th>최대</th>
                <th>불리 비율</th>
                <th>평균 지연</th>
              </tr>
            </thead>
            <tbody>
              {[
                { name: "전체", agg: data.aggregate },
                { name: "매수", agg: data.by_side.buy },
                { name: "매도", agg: data.by_side.sell },
              ].map(({ name, agg }) => (
                <tr key={name}>
                  <td>{name}</td>
                  {agg.count === 0 ? (
                    <td colSpan={6} className="muted">
                      없음
                    </td>
                  ) : (
                    <>
                      <td>{agg.count}</td>
                      <td>{pct(agg.avg_slippage_pct)}</td>
                      <td>{pct(agg.median_slippage_pct)}</td>
                      <td>{pct(agg.max_slippage_pct)}</td>
                      <td>{((agg.adverse_fill_ratio ?? 0) * 100).toFixed(0)}%</td>
                      <td>
                        {agg.avg_latency_seconds === null ||
                        agg.avg_latency_seconds === undefined
                          ? "—"
                          : `${agg.avg_latency_seconds}s`}
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {data.worst.length > 0 && (
            <>
              <h4>가장 불리했던 체결</h4>
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>종목</th>
                    <th>방향</th>
                    <th>신호가</th>
                    <th>체결가</th>
                    <th>슬리피지</th>
                    <th>버전</th>
                  </tr>
                </thead>
                <tbody>
                  {data.worst.map((w) => (
                    <tr key={w.trade_id}>
                      <td>{w.symbol_code}</td>
                      <td>{w.side}</td>
                      <td>{w.signal_price.toLocaleString()}</td>
                      <td>{w.fill_price.toLocaleString()}</td>
                      <td>{pct(w.slippage_pct)}</td>
                      <td>{w.strategy_version_id ? `v${w.strategy_version_id}` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}
    </div>
  );
}
