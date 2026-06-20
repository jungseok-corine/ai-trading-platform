import { useQuery } from "@tanstack/react-query";
import { getRetroSummary, getScannerRetros, getStrategyRetros } from "../../api/research";
import type { RetroEntry } from "../../api/research";

const VERDICT_LABEL: Record<string, string> = {
  improved: "✅ 개선", worse: "❌ 악화", inconclusive: "⏳ 판단보류",
};

function RetroTable({ rows, metric }: { rows: RetroEntry[]; metric: string }) {
  if (rows.length === 0) return <p className="muted">회고 대상 제안이 없습니다.</p>;
  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>제안</th><th>판정</th><th>{metric}(base→new)</th><th>표본(base/new)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.proposal_id}>
              <td>#{r.proposal_id}</td>
              <td>{VERDICT_LABEL[r.verdict] ?? r.verdict}</td>
              <td>{r.base_metric ?? "-"} → <strong>{r.new_metric ?? "-"}</strong></td>
              <td>{r.base_samples} / {r.new_samples}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function RetrospectiveSection() {
  const { data: summary } = useQuery({ queryKey: ["retro-summary"], queryFn: getRetroSummary });
  const { data: strat } = useQuery({ queryKey: ["retro-strategy"], queryFn: getStrategyRetros });
  const { data: scan } = useQuery({ queryKey: ["retro-scanner"], queryFn: getScannerRetros });

  return (
    <div className="card">
      <h3>제안 회고 (효과 검증)</h3>
      <p className="muted">
        승인된 AI 제안이 실제로 나아졌는지 base 버전과 비교합니다. (전략=기대값, 스캐너=승률)
        표본이 부족하면 판단보류. 이 결과는 다음 AI 분석에도 피드백됩니다.
      </p>
      {summary && (
        <p className="action-result value">
          총 {summary.total}건 — 개선 {summary.improved} · 악화 {summary.worse} · 판단보류 {summary.inconclusive}
        </p>
      )}
      <h4>전략 제안</h4>
      <RetroTable rows={strat ?? []} metric="기대값" />
      <h4>스캐너 제안</h4>
      <RetroTable rows={scan ?? []} metric="승률%" />
    </div>
  );
}
