// C-6.7: AI 의사결정 피드 — "오늘 AI가 무엇을 분석했고, 무엇을 제안했고, 사람이 무엇을 결정했나"
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAiActivityFeed } from "../../api/research";

const KIND_BADGES: Record<string, { label: string; color: string }> = {
  analysis_run: { label: "분석", color: "#1565c0" },
  proposal_created: { label: "제안", color: "#6a1b9a" },
  proposal_approved: { label: "승인", color: "#2e7d32" },
  proposal_rejected: { label: "거절", color: "#c62828" },
  scanner_proposal_created: { label: "스캐너 제안", color: "#6a1b9a" },
  scanner_proposal_approved: { label: "승인", color: "#2e7d32" },
  scanner_proposal_rejected: { label: "거절", color: "#c62828" },
};

export default function AiActivityFeedSection() {
  const [days, setDays] = useState(1);
  const { data, isLoading, error } = useQuery({
    queryKey: ["ai-activity-feed", days],
    queryFn: () => getAiActivityFeed(days),
  });

  return (
    <div className="card">
      <h3>AI 의사결정 피드</h3>
      <p className="muted">
        AI가 분석·제안한 것과 사람이 결정한 것의 타임라인. 조회 전용 — 여기서 아무것도
        실행되지 않습니다.
      </p>
      <div className="form-row">
        {[1, 3, 7].map((d) => (
          <button
            key={d}
            className={days === d ? "primary" : undefined}
            onClick={() => setDays(d)}
          >
            최근 {d}일
          </button>
        ))}
      </div>
      {isLoading && <p className="muted">불러오는 중…</p>}
      {error != null && <p className="error">피드 조회 실패</p>}
      {data && data.events.length === 0 && (
        <p className="muted">이 기간에 기록된 AI 활동이 없습니다.</p>
      )}
      {data && data.events.length > 0 && (
        <ul className="feed-list">
          {data.events.map((e, i) => {
            const badge = KIND_BADGES[e.kind] ?? { label: e.kind, color: "#757575" };
            return (
              <li key={`${e.kind}-${e.ref.id}-${i}`} className="feed-item">
                <span className="feed-ts muted">
                  {new Date(e.ts).toLocaleString("ko-KR", {
                    month: "numeric",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
                <span className="badge" style={{ background: badge.color, color: "#fff" }}>
                  {badge.label}
                </span>
                <span>
                  <strong>{e.title}</strong>
                  {e.detail && <span className="muted"> — {e.detail}</span>}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
