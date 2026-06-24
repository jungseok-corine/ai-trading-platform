// C-OPS-3.2: 위험도 있는 자율 잡을 ON 하기 전 확인 게이트.
//
// recommended_state !== "ON_OK" (= SAFE_ON 이외) 잡을 켤 때만 표시된다.
// 실제 활성화는 기존 toggle mutation이 담당하며, 이 패널은 확인 단계만 추가한다.
import { useState } from "react";
import { AutonomousJob } from "../../api/client";
import { CapabilityBadges, RECOMMENDED_LABEL, RISK_LABEL } from "./jobRiskLabels";

interface Props {
  job: AutonomousJob;
  isPending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function JobEnableConfirm({ job, isPending, onConfirm, onCancel }: Props) {
  const [confirmed, setConfirmed] = useState(false);
  const keepOff = job.risk_level === "KEEP_OFF";

  // 조건부 경고 문구 (메타데이터 기반).
  const warnings: string[] = ["이 작업은 활성화되면 일정에 따라 자동으로 실행될 수 있습니다."];
  if (job.uses_llm || job.cost_risk) warnings.push("LLM/API 비용이 발생할 수 있습니다.");
  if (job.external_network) warnings.push("외부 API 호출이 발생할 수 있습니다.");
  if (job.creates_proposals) warnings.push("검토가 필요한 제안이 자동 생성될 수 있습니다.");
  if (job.paper_action)
    warnings.push("Paper 실험 상태가 자동 변경될 수 있습니다. 실전 거래는 아닙니다.");
  if (job.data_volume_risk) warnings.push("많은 레코드가 생성될 수 있습니다.");

  return (
    <div className={`card approval-report-card job-enable-confirm ${keepOff ? "keep-off" : "manual-first"}`}>
      <h4>{keepOff ? "기본 OFF 유지 권장 작업입니다" : "먼저 수동 실행으로 확인하는 것이 권장됩니다"}</h4>

      <p>
        <strong>{job.label}</strong>{" "}
        <span className="muted" style={{ fontSize: "0.85em" }}>{job.job_id}</span>
      </p>
      {job.description && <p>{job.description}</p>}

      <div className="badge-row">
        <span className={`risk-badge risk-${job.risk_level}`}>{RISK_LABEL[job.risk_level]}</span>
        <span className="risk-badge risk-rec">{RECOMMENDED_LABEL[job.recommended_state]}</span>
      </div>
      <CapabilityBadges job={job} />

      {job.safety_notes.length > 0 && (
        <ul className="job-safety-notes">
          {job.safety_notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}

      <div className="approval-block warn">
        <strong>활성화 시 유의사항</strong>
        <ul className="approval-list">
          {warnings.map((w) => (
            <li key={w}>⚠️ {w}</li>
          ))}
        </ul>
      </div>

      <div className="approval-block safe">
        <ul className="approval-list">
          <li>🚫 실전 주문은 실행되지 않습니다.</li>
          <li>🚫 proposal 승인 / ACTIVE 전환 / 자동매매 활성화는 수행되지 않습니다.</li>
        </ul>
      </div>

      <div className="approval-actions">
        <label className="confirm-check">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          이 내용을 확인했습니다.
        </label>
        <div className="form-row">
          <button className="primary" disabled={!confirmed || isPending} onClick={onConfirm}>
            활성화 확정
          </button>
          <button disabled={isPending} onClick={onCancel}>
            취소
          </button>
        </div>
      </div>
    </div>
  );
}
