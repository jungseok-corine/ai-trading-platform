// 후보 종목 → 전략 제안 미리보기 (읽기 전용, 미저장).
// 이 패널은 "이 후보에 어떤 전략 템플릿을 실험해볼지"를 *제안*만 한다.
//   - 저장하지 않는다 (PENDING 개념의 미리보기일 뿐, DB 변경 없음).
//   - 자동 배정/버전 생성/자동매매/주문/실전 연결 없음.
//   - 확정 배정은 별도의 '전략 배정' 액션(배정 규칙 기반 로그)으로, 실험/실전은 사람이 별도 승인.
import type { CandidateEvent } from "../../types/research";

// 스캐너 매칭 조건(matched_conditions) → 검토해볼 만한 전략 템플릿 가이드.
// 이는 권위 있는 배정 알고리즘이 아니라, 후보 facts 기반의 *검토 힌트*다(읽기 전용).
const CONDITION_GUIDE: Record<string, { strategy: string; reason: string }> = {
  volume_spike: {
    strategy: "volume_confirmed_ma_cross",
    reason: "거래량 급증 신호 — 거래량 확인형 추세 전략을 실험 후보로 검토",
  },
  price_change_pct: {
    strategy: "momentum_surge",
    reason: "단기 상승률 신호 — 상승 모멘텀 전략을 실험 후보로 검토",
  },
  turnover_rank: {
    strategy: "breakout_high",
    reason: "거래대금 상위 — 신고가/돌파형 전략을 실험 후보로 검토",
  },
  investor_flow: {
    strategy: "flow_confirmed_volume_ma_cross",
    reason: "수급(외국인/기관) 신호 — 수급 확인형 전략을 실험 후보로 검토",
  },
  time_bucket: {
    strategy: "moving_average_cross",
    reason: "시간대 조건 — 단독으로는 방향성이 약해 기본 추세 전략부터 검토",
  },
};

const FALLBACK = {
  strategy: "moving_average_cross",
  reason: "특이 신호가 없어 기본 이동평균 교차 전략부터 검토",
};

export interface StrategyProposalPreview {
  strategy: string;
  reason: string;
}

// 후보의 matched_conditions로부터 중복 없는 전략 제안 목록을 만든다 (순수 함수, 부작용 없음).
export function buildProposalPreview(candidate: CandidateEvent): StrategyProposalPreview[] {
  const conds = candidate.matched_conditions ?? [];
  const seen = new Set<string>();
  const out: StrategyProposalPreview[] = [];
  for (const c of conds) {
    const guide = CONDITION_GUIDE[c];
    if (guide && !seen.has(guide.strategy)) {
      seen.add(guide.strategy);
      out.push(guide);
    }
  }
  if (out.length === 0) out.push(FALLBACK);
  return out;
}

interface Props {
  candidate: CandidateEvent;
  onClose: () => void;
}

export default function CandidateStrategyProposalPanel({ candidate, onClose }: Props) {
  const previews = buildProposalPreview(candidate);

  return (
    <div className="card proposal-preview" style={{ background: "#f1f5f9" }}>
      <div className="proposal-preview-head">
        <strong>전략 제안 (검토용 · 미저장)</strong>
        <span className="pending-badge">PENDING</span>
        <button className="link-button" onClick={onClose} style={{ marginLeft: "auto" }}>
          닫기 ✕
        </button>
      </div>

      <p className="muted" style={{ fontSize: "0.86em", margin: "4px 0" }}>
        후보 <strong>{candidate.symbol_code}</strong> · 점수 {candidate.score} · 조건{" "}
        <code>{(candidate.matched_conditions ?? []).join(", ") || "-"}</code>
      </p>

      <table>
        <thead>
          <tr><th>제안 전략 템플릿</th><th>근거</th></tr>
        </thead>
        <tbody>
          {previews.map((p) => (
            <tr key={p.strategy}>
              <td><code>{p.strategy}</code></td>
              <td>{p.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="muted safety-note" style={{ fontSize: "0.82em", marginTop: 8 }}>
        ⚠️ 이것은 <strong>제안(검토용)</strong>일 뿐입니다 — 저장하지 않으며 자동 배정·전략 버전 생성·
        자동매매·주문·실전 연결을 하지 않습니다. 확정 배정은 ‘전략 배정’(배정 규칙 기반 기록)으로,
        실험·실전 배치는 사람이 별도로 승인합니다.
      </p>
    </div>
  );
}
