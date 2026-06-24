// C-2.30: 상태 전환 계획(transition plan)을 사람이 읽기 쉬운 형태로 표시하는 공용 컴포넌트.
import type { TransitionPlan } from "../../types/research";

function statusLabel(status: string): string {
  // TESTING이 실거래로 오해되지 않도록 항상 안내 문구를 덧붙인다.
  if (status.toLowerCase() === "testing") return "TESTING (실거래·자동매매 아님)";
  return status.toUpperCase();
}

export default function TransitionPlanView({ plan }: { plan: TransitionPlan }) {
  const nv = plan.new_version;
  return (
    <div className="transition-plan">
      <div className="approval-block">
        <strong>새 버전</strong>
        <ul className="approval-list">
          <li>
            상태: <span className="badge badge-testing">{statusLabel(nv.status)}</span>
          </li>
          {nv.auto_trade_enabled !== undefined && (
            <li>
              자동매매: <strong>{nv.auto_trade_enabled ? "ON" : "OFF (false 고정)"}</strong>
            </li>
          )}
          {nv.reason && <li className="muted">{nv.reason}</li>}
        </ul>
      </div>

      <div className="approval-block">
        <strong>기존 버전 ({plan.previous_versions.length})</strong>
        {plan.previous_versions.length === 0 ? (
          <p className="muted">기존 버전 없음</p>
        ) : (
          <ul className="approval-list">
            {plan.previous_versions.map((v) => (
              <li key={v.version_id}>
                #{v.version_id} ({v.current_status}) →{" "}
                <strong>{v.proposed_action === "KEEP" ? "유지(KEEP)" : v.proposed_action}</strong>
                {v.running_experiment_ids.length > 0 && (
                  <span className="muted">
                    {" "}· 실행 중 실험 {v.running_experiment_ids.join(", ")}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {plan.blocked_actions.length > 0 && (
        <div className="approval-block warn">
          <strong>차단된 동작</strong>
          <ul className="approval-list">
            {plan.blocked_actions.map((b, i) => (
              <li key={`${b.version_id}-${i}`}>
                {b.action} (#{b.version_id}): {b.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {plan.safety_warnings.length > 0 && (
        <div className="approval-block warn">
          <strong>안전 경고</strong>
          <ul className="approval-list">
            {plan.safety_warnings.map((w, i) => (
              <li key={i}>⚠️ {w}</li>
            ))}
          </ul>
        </div>
      )}

      {!plan.plan_valid && (
        <p className="value error">
          ⚠️ 이 전환 계획은 안전 검증을 통과하지 못했습니다. 승인할 수 없습니다.
        </p>
      )}
    </div>
  );
}
