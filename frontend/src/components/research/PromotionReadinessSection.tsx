import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getPromotionReadiness } from "../../api/research";
import LivePromotionReviewCard from "./LivePromotionReviewCard";

export default function PromotionReadinessSection() {
  const [reviewVersionId, setReviewVersionId] = useState<number | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["promotion-readiness"],
    queryFn: () => getPromotionReadiness(),
  });

  return (
    <div className="card">
      <h3>승격 준비 현황</h3>
      <p className="muted">
        활성/테스트 전략 버전이 승격 기준에 얼마나 근접했는지 봅니다. ⚠️ 통과는 '실전 적용 가능
        판단'일 뿐 — <strong>실거래 활성화는 사람만</strong> 합니다. read-only 평가입니다.
      </p>

      {isLoading && <p className="muted">불러오는 중…</p>}
      {data && (
        <>
          {data.criteria ? (
            <p className="action-result value">
              기준 「{data.criteria.name}」 — 최소 거래 {data.criteria.min_trade_count} ·
              최소 {data.criteria.min_days}일 · 기댓값 ≥ {data.criteria.min_expectancy}
              {data.criteria.max_drawdown !== null && ` · MDD ≤ ${data.criteria.max_drawdown}`}
            </p>
          ) : (
            <p className="muted">{data.note}</p>
          )}

          {data.rows.length > 0 && (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>전략 버전</th><th>상태</th><th>판정</th><th>충족</th>
                    <th>거래</th><th>일수</th><th>기댓값</th><th>MDD</th><th>실전 승격 검토</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r) => (
                    <tr key={r.strategy_version_id}>
                      <td>{r.label}</td>
                      <td>{r.status}</td>
                      <td>{r.passed ? "✅ 통과" : "⏳ 미달"}</td>
                      <td>{r.checks_passed}/{r.checks_total}</td>
                      <td>{r.trades_count}</td>
                      <td>{r.days}</td>
                      <td>{r.expectancy.toLocaleString()}</td>
                      <td>{r.max_drawdown.toLocaleString()}</td>
                      <td>
                        <button
                          onClick={() =>
                            setReviewVersionId(
                              reviewVersionId === r.strategy_version_id
                                ? null
                                : r.strategy_version_id,
                            )
                          }
                        >
                          {reviewVersionId === r.strategy_version_id ? "닫기" : "검토 승인"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {reviewVersionId !== null && (
            <LivePromotionReviewCard
              key={reviewVersionId}
              strategyVersionId={reviewVersionId}
              criteriaId={data.criteria?.id}
            />
          )}
        </>
      )}
    </div>
  );
}
