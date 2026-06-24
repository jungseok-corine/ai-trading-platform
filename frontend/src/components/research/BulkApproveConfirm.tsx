// C-2.30.1: 일괄 승인 전 안전 확인 게이트.
//
// bulk approve가 C-2.30 단일 승인의 안전 UX(전환계획·안전 고지·확인)를 우회하지 못하도록,
// 실행 직전에 선택 개수 + 정적 안전 문구 + 확인 체크박스를 강제한다.
import { useState } from "react";
import { WillHappenBlock, WillNotHappenBlock } from "./approvalBlocks";
import {
  SCANNER_WILL_HAPPEN,
  SCANNER_WILL_NOT_HAPPEN,
  STRATEGY_WILL_HAPPEN,
  STRATEGY_WILL_NOT_HAPPEN,
} from "./safetyCopy";

interface Props {
  count: number;
  kind: "strategy" | "scanner";
  isPending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function BulkApproveConfirm({ count, kind, isPending, onConfirm, onCancel }: Props) {
  const [confirmed, setConfirmed] = useState(false);
  const willHappen = kind === "strategy" ? STRATEGY_WILL_HAPPEN : SCANNER_WILL_HAPPEN;
  const willNotHappen = kind === "strategy" ? STRATEGY_WILL_NOT_HAPPEN : SCANNER_WILL_NOT_HAPPEN;

  return (
    <div className="card approval-report-card bulk-confirm">
      <h4>일괄 승인 확인</h4>
      <p className="value">선택된 pending 제안 {count}건을 일괄 승인합니다.</p>
      <p className="muted">아래 내용을 확인해야 일괄 승인을 진행할 수 있습니다.</p>

      <WillHappenBlock items={willHappen} />
      <WillNotHappenBlock items={willNotHappen} />

      <div className="approval-actions">
        <label className="confirm-check">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          위 내용을 확인했습니다. 새 버전은 TESTING으로 생성되며 실거래는 켜지지 않습니다.
        </label>
        <div className="form-row">
          <button className="primary" disabled={!confirmed || isPending} onClick={onConfirm}>
            일괄 승인 확정 ({count}건)
          </button>
          <button disabled={isPending} onClick={onCancel}>
            취소
          </button>
        </div>
      </div>
    </div>
  );
}
