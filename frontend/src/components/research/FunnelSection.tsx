import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getProposalFunnel, getResearchFunnel } from "../../api/research";
import type { FunnelStage } from "../../api/research";

const DAY_OPTIONS = [7, 30, 90];

function rate(r: number | null): string {
  return r === null ? "-" : `${(r * 100).toFixed(0)}%`;
}

function StageRow({ label, s }: { label: string; s: FunnelStage }) {
  return (
    <tr>
      <td>{label}</td>
      <td>{s.generated}</td>
      <td>{s.pending}</td>
      <td>{s.approved}</td>
      <td>{s.rejected}</td>
      <td>{s.versions_created}</td>
      <td>{rate(s.approval_rate)}</td>
    </tr>
  );
}

export default function FunnelSection() {
  const [days, setDays] = useState(30);
  const { data, isLoading } = useQuery({
    queryKey: ["proposal-funnel", days],
    queryFn: () => getProposalFunnel(days),
  });
  const { data: research } = useQuery({
    queryKey: ["research-funnel", days],
    queryFn: () => getResearchFunnel(days),
  });

  return (
    <div className="card">
      <h3>연구 루프 퍼널 (ROI)</h3>
      <p className="muted">
        전반부(후보→배정→실험)와 후반부(AI 제안→승인→버전→회고)를 한 화면에서 봅니다.
        시장 스캔이 실험으로, 제안이 개선으로 얼마나 이어지는지가 연구 루프의 ROI입니다.
        승인은 사람만 합니다(여긴 집계만).
      </p>
      <div className="sub-nav">
        {DAY_OPTIONS.map((d) => (
          <button key={d} className={days === d ? "primary" : undefined}
            onClick={() => setDays(d)}>
            최근 {d}일
          </button>
        ))}
      </div>

      {research && (
        <p className="action-result value">
          전반부(후보→배정→실험): 후보 {research.candidates} → 배정 {research.candidates_assigned}
          {research.assignment_rate !== null && ` (전환 ${rate(research.assignment_rate)})`} →
          실험 {research.experiments} (진행 {research.experiments_running})
        </p>
      )}

      {isLoading && <p className="muted">불러오는 중…</p>}
      {data && (
        <>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>구분</th><th>생성</th><th>검토대기</th><th>승인</th>
                  <th>거절</th><th>버전생성</th><th>승인률</th>
                </tr>
              </thead>
              <tbody>
                <StageRow label="전략" s={data.strategy} />
                <StageRow label="스캐너" s={data.scanner} />
                <StageRow label="합계" s={data.combined} />
              </tbody>
            </table>
          </div>
          <p className="action-result value">
            회고: 총 {data.retrospective.total}건 — 개선 {data.retrospective.improved} ·
            악화 {data.retrospective.worse} · 판단보류 {data.retrospective.inconclusive}
          </p>
          {data.retrospective.worse > data.retrospective.improved && (
            <p className="muted">⚠️ 악화가 개선보다 많습니다 — 제안 기준을 보수적으로 재검토하세요.</p>
          )}
        </>
      )}
    </div>
  );
}
