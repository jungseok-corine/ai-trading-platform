// C-OPS-3.1/3.2: 자율 잡 위험도/추천 상태/특성 라벨·배지 (정적 상수, 표시 전용).
import { AutonomousJob } from "../../api/client";

export const RISK_LABEL: Record<AutonomousJob["risk_level"], string> = {
  SAFE_ON: "상시 ON 가능",
  MANUAL_FIRST: "수동 실행 먼저 권장",
  KEEP_OFF: "기본 OFF 유지 권장",
  DO_NOT_ENABLE: "활성화 금지",
};

export const RECOMMENDED_LABEL: Record<AutonomousJob["recommended_state"], string> = {
  ON_OK: "추천: ON 가능",
  MANUAL_FIRST: "추천: 수동 우선",
  KEEP_OFF: "추천: OFF 유지",
};

export function CapabilityBadges({ job }: { job: AutonomousJob }) {
  return (
    <div className="badge-row">
      {job.writes_db && <span className="cap-badge">DB 기록 있음</span>}
      {(job.uses_llm || job.cost_risk) && (
        <span className="cap-badge cap-warn">LLM/비용 가능성</span>
      )}
      {job.external_network && <span className="cap-badge">외부 API 호출</span>}
      {job.creates_proposals && (
        <span className="cap-badge cap-warn">제안 생성 가능</span>
      )}
      {job.paper_action && <span className="cap-badge">Paper 상태 변경 가능</span>}
      {job.data_volume_risk && <span className="cap-badge">레코드 다량 생성</span>}
      {/* 안전 고지: 어떤 잡도 실전 거래에 영향 없음 */}
      <span className="cap-badge cap-safe">실전 주문 영향 없음</span>
    </div>
  );
}
