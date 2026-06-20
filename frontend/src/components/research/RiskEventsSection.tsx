import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getRiskEventSummary } from "../../api/research";

const DAY_OPTIONS = [7, 30, 90];

export default function RiskEventsSection() {
  const [days, setDays] = useState(30);
  const { data, isLoading } = useQuery({
    queryKey: ["risk-events", days],
    queryFn: () => getRiskEventSummary(days),
  });

  return (
    <div className="card">
      <h3>리스크 이벤트</h3>
      <p className="muted">
        리스크 레이어가 신호를 승인/차단한 기록입니다. 차단이 잦거나 특정 룰에 몰리면 전략/리스크
        설정을 점검할 신호입니다. read-only 집계입니다.
      </p>
      <div className="sub-nav">
        {DAY_OPTIONS.map((d) => (
          <button key={d} className={days === d ? "primary" : undefined}
            onClick={() => setDays(d)}>최근 {d}일</button>
        ))}
      </div>

      {isLoading && <p className="muted">불러오는 중…</p>}
      {data && (
        <>
          <p className="action-result value">
            총 {data.total}건 — 승인 {data.approved} · 차단 {data.rejected}
            {data.rejection_rate !== null && ` (차단률 ${data.rejection_rate}%)`}
          </p>

          {data.by_rule.length > 0 && (
            <>
              <h4>룰별</h4>
              <div className="table-wrapper">
                <table>
                  <thead><tr><th>룰</th><th>승인</th><th>차단</th></tr></thead>
                  <tbody>
                    {data.by_rule.map((r) => (
                      <tr key={r.rule_name}>
                        <td>{r.rule_name}</td><td>{r.approved}</td><td>{r.rejected}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {data.recent_rejections.length > 0 && (
            <>
              <h4>최근 차단</h4>
              <div className="table-wrapper">
                <table>
                  <thead><tr><th>일시</th><th>룰</th><th>사유</th></tr></thead>
                  <tbody>
                    {data.recent_rejections.map((r, i) => (
                      <tr key={i}>
                        <td>{r.created_at?.slice(0, 16).replace("T", " ") ?? "-"}</td>
                        <td>{r.rule_name ?? "-"}</td>
                        <td>{r.reason ?? "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
