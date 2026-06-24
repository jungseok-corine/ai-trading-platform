// C-2.30: AI 스캐너 제안 승인 전 리포트 카드.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getScannerProposal, getScannerTransitionPlan } from "../../api/research";
import type { ProposalStatus } from "../../types/research";
import TransitionPlanView from "./TransitionPlanView";
import { RawJsonDetails, WillHappenBlock, WillNotHappenBlock } from "./approvalBlocks";
import { SCANNER_WILL_HAPPEN, SCANNER_WILL_NOT_HAPPEN } from "./safetyCopy";

interface Props {
  proposalId: number;
  status: ProposalStatus;
  onApprove: () => void;
  onReject: () => void;
  approving?: boolean;
  rejecting?: boolean;
}

export default function ScannerProposalReportCard({
  proposalId,
  status,
  onApprove,
  onReject,
  approving,
  rejecting,
}: Props) {
  const [confirmed, setConfirmed] = useState(false);

  const detailQ = useQuery({
    queryKey: ["scanner-proposal", proposalId],
    queryFn: () => getScannerProposal(proposalId),
  });
  const planQ = useQuery({
    queryKey: ["scanner-transition-plan", proposalId],
    queryFn: () => getScannerTransitionPlan(proposalId),
  });

  const detail = detailQ.data;
  const plan = planQ.data;
  const isPending = status === "pending";
  const planOk = !!plan && plan.plan_valid;
  const canApprove = isPending && confirmed && planOk && !approving;

  return (
    <div className="card approval-report-card">
      <h4>스캐너 제안 #{proposalId} 승인 리포트</h4>

      {detail && (
        <div className="approval-summary">
          <p>
            <strong>{detail.title}</strong>{" "}
            <span className={`badge badge-${detail.status}`}>{detail.status}</span>
          </p>
          {detail.summary && <p>{detail.summary}</p>}
          {detail.rationale && (
            <p>
              <strong>근거:</strong> {detail.rationale}
            </p>
          )}
          {detail.expected_effect && (
            <p>
              <strong>예상 효과:</strong> {detail.expected_effect}
            </p>
          )}
          {detail.risk_notes && (
            <p>
              <strong>리스크:</strong> {detail.risk_notes}
            </p>
          )}

          <div className="approval-block">
            <strong>조건 변경 (before → after)</strong>
            {detail.diff.length === 0 ? (
              <p className="muted">변경 없음</p>
            ) : (
              <ul className="approval-list">
                {detail.diff.map((d) => (
                  <li key={d.type}>
                    {d.type}: <span className="muted">{JSON.stringify(d.before)}</span> →{" "}
                    <strong>{JSON.stringify(d.after)}</strong>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {planQ.isLoading && <p className="muted">전환 계획 불러오는 중…</p>}
      {planQ.isError && (
        <p className="value error">
          ⚠️ 전환 계획을 불러오지 못했습니다. 안전을 위해 승인할 수 없습니다.
        </p>
      )}
      {plan && <TransitionPlanView plan={plan} />}

      <WillHappenBlock items={SCANNER_WILL_HAPPEN} />
      <WillNotHappenBlock items={SCANNER_WILL_NOT_HAPPEN} />

      {plan && <RawJsonDetails label="transition_plan" data={plan} />}

      {isPending ? (
        <div className="approval-actions">
          <label className="confirm-check">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            위 내용을 확인했습니다. 새 룰 버전은 TESTING으로 생성되며 자동 활성화되지 않습니다.
          </label>
          <div className="form-row">
            <button className="primary" disabled={!canApprove} onClick={onApprove}>
              승인
            </button>
            <button className="danger" disabled={rejecting} onClick={onReject}>
              거절
            </button>
          </div>
          {!planOk && !planQ.isLoading && (
            <p className="muted">전환 계획이 유효하지 않거나 로드되지 않아 승인이 비활성화됩니다.</p>
          )}
        </div>
      ) : (
        <p className="muted">검토 완료 ({detail?.reviewed_by ?? "-"})</p>
      )}
    </div>
  );
}
