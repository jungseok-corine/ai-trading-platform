// 후보 종목 → 전략 제안 (검토용 미리보기 + PENDING 제안 저장).
// 이 패널은 "이 후보에 어떤 전략 템플릿을 실험해볼지"를 *제안*만 한다.
//   - '제안 저장'은 PENDING 제안 레코드만 만든다 (전략 적용/배정 실행/자동매매 아님).
//   - 자동 배정/버전 생성/자동매매/주문/실전 연결 없음.
//   - 확정 배정은 별도의 '전략 배정' 액션, 실험/실전은 사람이 별도 승인.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  approvePaperReadiness,
  createCandidateStrategyProposal,
  createPaperSignalAnalysisRun,
  getPaperSignalAnalysisRuns,
  getCandidateStrategyProposals,
  getExperiment,
  getPaperSignalSessionAnalysisInput,
  getPaperSignalSessionOutcomes,
  getPaperSignalSessions,
  preparePaperExperiment,
  reviewCandidateStrategyProposal,
  startPaperSignalSession,
  stopPaperSignalSession,
} from "../../api/research";
import { useSettings } from "../../i18n/SettingsContext";
import type { CandidateEvent, CandidateStrategyProposal } from "../../types/research";

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

const STATUS_LABEL: Record<string, string> = {
  pending: "검토 대기",
  approved: "승인됨 (APPROVED)",
  rejected: "거절됨 (REJECTED)",
};

// 세션 AI 분석 입력 미리보기(읽기 전용). AI 호출/제안 생성 없음 — payload만 본다.
function SessionAnalysisInputPreview({ sessionId }: { sessionId: number }) {
  const [show, setShow] = useState(false);
  const { data } = useQuery({
    queryKey: ["paper-signal-analysis-input", sessionId],
    queryFn: () => getPaperSignalSessionAnalysisInput(sessionId, 30),
    enabled: show,
  });
  return (
    <div style={{ marginTop: 2 }}>
      <button className="link-button" onClick={() => setShow((v) => !v)}>
        {show ? "AI 분석 입력 닫기" : "AI 분석 입력 보기"}
      </button>
      {show && (
        <>
          <div className="muted" style={{ fontSize: "0.75em" }}>
            읽기 전용 payload — AI 호출/제안 생성 없음
          </div>
          {data && (
            <pre className="parameters-cell" style={{ maxHeight: 220, overflow: "auto" }}>
              {JSON.stringify(data, null, 2)}
            </pre>
          )}
        </>
      )}
    </div>
  );
}

// 세션 AI 분석 리포트(V1). 사람 확인 후 fake provider로 리포트 생성 — 전략/세션/주문 변경 없음.
function SessionAnalysisRuns({ sessionId }: { sessionId: number }) {
  const queryClient = useQueryClient();
  const { formatDateTime } = useSettings();
  const [confirm, setConfirm] = useState(false);
  const { data: runs } = useQuery({
    queryKey: ["paper-signal-analysis-runs", sessionId],
    queryFn: () => getPaperSignalAnalysisRuns(sessionId),
  });
  const genMut = useMutation({
    // 분석 리포트만 생성 — 제안·전략·자동매매에 영향 없음.
    mutationFn: () =>
      createPaperSignalAnalysisRun(sessionId, {
        confirmed: true,
        confirmed_by: "manual_user",
        provider: "fake",
        horizon_minutes: 30,
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["paper-signal-analysis-runs", sessionId] }),
  });
  const latest = (runs ?? [])[0];
  const latestReport = latest?.responses?.find((r) => r.content)?.content ?? null;

  return (
    <div style={{ marginTop: 4 }}>
      <label style={{ display: "block", fontSize: "0.8em" }}>
        <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />{" "}
        AI 분석만 생성하며 전략/주문/세션 상태는 변경하지 않습니다
      </label>
      <button
        disabled={!confirm || genMut.isPending}
        onClick={() => genMut.mutate()}
        style={{ marginTop: 2 }}
      >
        {genMut.isPending ? "생성 중…" : "AI 분석 리포트 생성"}
      </button>
      <span className="muted" style={{ fontSize: "0.75em", marginLeft: 8 }}>
        분석 리포트 · 제안 생성 아님 · 자동매매 아님
      </span>
      {genMut.isError && (
        <span className="muted" style={{ fontSize: "0.78em", color: "#b91c1c", marginLeft: 8 }}>
          생성 실패 — 다시 시도하세요.
        </span>
      )}

      {runs && runs.length > 0 && (
        <div className="muted" style={{ fontSize: "0.78em", marginTop: 4 }}>
          이전 분석 {runs.length}건:{" "}
          {runs
            .slice(0, 5)
            .map((r) => `#${r.id} ${r.provider}/${r.model}(${r.status}, ${formatDateTime(r.created_at)})`)
            .join(" · ")}
        </div>
      )}
      {latestReport && (
        <details style={{ marginTop: 2 }}>
          <summary className="link-button" style={{ fontSize: "0.8em" }}>최근 분석 리포트 보기</summary>
          <pre className="parameters-cell" style={{ maxHeight: 240, overflow: "auto", whiteSpace: "pre-wrap" }}>
            {latestReport}
          </pre>
        </details>
      )}
    </div>
  );
}

// 세션 outcome 요약(읽기 전용). SignalLog + market_data forward 수익률 — 주문/실행 아님.
function SessionOutcomeSummary({ sessionId }: { sessionId: number }) {
  const { data } = useQuery({
    queryKey: ["paper-signal-outcomes", sessionId],
    queryFn: () => getPaperSignalSessionOutcomes(sessionId, 30),
  });
  if (!data) return null;
  if (data.signal_count === 0) {
    return <div className="muted" style={{ fontSize: "0.8em" }}>아직 기록된 SignalLog가 없습니다</div>;
  }
  const fmt = (v: number | null) => (v == null ? "-" : v);
  return (
    <>
      <div className="muted" style={{ fontSize: "0.8em" }}>
        신호 {data.signal_count}건 · 분석 {data.analyzed_count} · 대기 {data.pending_count} · 승률{" "}
        {fmt(data.win_rate)}% · 평균 {fmt(data.avg_return_pct)}% · 최고 {fmt(data.best_return_pct)}% ·
        최저 {fmt(data.worst_return_pct)}% <span style={{ fontSize: "0.92em" }}>(30분 forward)</span>
      </div>
      <SessionAnalysisInputPreview sessionId={sessionId} />
      <SessionAnalysisRuns sessionId={sessionId} />
    </>
  );
}

// 준비·준비승인된 제안에 대한 Paper 신호 기록 세션 제어(signal-only).
// 시작/중지만 — 주문/자동매매/상태전환 없음. SignalLog만 쌓인다. + 세션 outcome 요약(읽기 전용).
function PaperSignalSessionControl({
  proposal,
}: {
  proposal: CandidateStrategyProposal;
}) {
  const queryClient = useQueryClient();
  const { formatDateTime } = useSettings();
  const [confirm, setConfirm] = useState(false);
  const { data: sessions } = useQuery({
    queryKey: ["paper-signal-sessions"],
    queryFn: () => getPaperSignalSessions(),
  });
  const mine = (sessions ?? []).filter((s) => s.candidate_strategy_proposal_id === proposal.id);
  const active = mine.find((s) => s.status === "active");
  const latest = mine[0]; // 목록은 id desc → 가장 최근 세션

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["paper-signal-sessions"] });

  const startMut = useMutation({
    // 신호 기록 세션 시작 — SignalLog만, 주문/자동매매 없음.
    mutationFn: () =>
      startPaperSignalSession(proposal.id, { confirmed: true, confirmed_by: "manual_user" }),
    onSuccess: invalidate,
  });
  const stopMut = useMutation({
    mutationFn: (sessionId: number) =>
      stopPaperSignalSession(sessionId, { confirmed_by: "manual_user" }),
    onSuccess: invalidate,
  });

  if (active) {
    return (
      <div className="paper-signal-session" style={{ marginTop: 6 }}>
        <div>
          <span className="proposal-status status-running">Paper 신호 기록 중</span>
          <span className="muted"> · 주문 없음 · 자동매매 아님 · SignalLog 기록</span>
        </div>
        <div className="muted" style={{ fontSize: "0.8em" }}>
          세션 #{active.id} · 신호 {active.signal_count}건 · 실행 {active.run_count}회
          {active.last_run_at ? ` · 최근 ${formatDateTime(active.last_run_at)}` : ""}
        </div>
        <SessionOutcomeSummary sessionId={active.id} />
        <button
          disabled={stopMut.isPending}
          onClick={() => stopMut.mutate(active.id)}
          style={{ marginTop: 4 }}
        >
          {stopMut.isPending ? "중지 중…" : "신호 기록 중지"}
        </button>
      </div>
    );
  }

  return (
    <div className="paper-signal-session" style={{ marginTop: 6 }}>
      {latest && latest.status === "stopped" && (
        <div style={{ marginBottom: 4 }}>
          <span className="proposal-status status-draft">신호 기록 중지됨</span>
          <span className="muted"> · 세션 #{latest.id}</span>
          <SessionOutcomeSummary sessionId={latest.id} />
        </div>
      )}
      <label style={{ display: "block", fontSize: "0.82em" }}>
        <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />{" "}
        주문 없이 SignalLog만 기록합니다 (자동매매 아님 · DRAFT 유지)
      </label>
      <button
        disabled={!confirm || startMut.isPending}
        onClick={() => startMut.mutate()}
        style={{ marginTop: 4 }}
      >
        {startMut.isPending ? "시작 중…" : "Paper 신호 기록 시작"}
      </button>
      {startMut.isError && (
        <span className="muted" style={{ fontSize: "0.8em", color: "#b91c1c", marginLeft: 8 }}>
          시작 실패 — 다시 시도하세요.
        </span>
      )}
    </div>
  );
}

// 준비된 DRAFT paper 실험을 읽기 전용으로 보여준다(검토용). 실행/시작/활성 버튼 없음.
// 실제 실험 상태는 GET /experiments/{id}로 읽어 그대로 표시한다(상태 변경 안 함).
function PreparedExperimentView({
  experimentId,
  proposal,
}: {
  experimentId: number;
  proposal: CandidateStrategyProposal;
}) {
  const queryClient = useQueryClient();
  const { formatDateTime } = useSettings();
  const [confirm, setConfirm] = useState(false);
  const { data: exp } = useQuery({
    queryKey: ["prepared-experiment", experimentId],
    queryFn: () => getExperiment(experimentId),
  });
  // 준비 승인 메타는 제안의 suggested_parameters에 남는다(상태 전환 없음).
  const readyAt =
    (proposal.suggested_parameters?.["_paper_testing_ready_at"] as string | undefined) ?? null;

  const approveMut = useMutation({
    // 준비됨 승인만 기록 — 상태 전환/실행/자동매매/주문/신호 기록 시작 없음.
    mutationFn: () =>
      approvePaperReadiness(proposal.id, { confirmed: true, confirmed_by: "manual_user" }),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ["candidate-proposals", proposal.candidate_event_id],
      }),
  });
  const isReady = readyAt !== null || approveMut.isSuccess;

  return (
    <div className="prepared-exp">
      <div>
        <strong>Paper 실험 준비됨</strong>{" "}
        <span className="proposal-status status-draft">DRAFT 유지</span>
        <span className="muted"> · 아직 실행 전</span>
      </div>
      <div className="muted">
        실험 #{experimentId} · 전략 <code>{proposal.suggested_strategy_type}</code> ·{" "}
        {proposal.symbol_code}
        {exp ? ` · variant ${exp.variants.length}개` : ""}
      </div>
      {proposal.prepared_at && (
        <div className="muted">준비 시각: {formatDateTime(proposal.prepared_at)}</div>
      )}

      {/* 준비 승인 게이트(상태 전환 없음). 이미 승인됐으면 승인 결과 + 신호 세션 제어. */}
      {isReady ? (
        <>
          <div className="muted" style={{ fontSize: "0.82em", marginTop: 4 }}>
            ✓ 준비 승인됨 — DRAFT 유지 · 자동매매 아님 · 주문 없음
            {readyAt && ` (${formatDateTime(readyAt)})`}
          </div>
          <PaperSignalSessionControl proposal={proposal} />
        </>
      ) : (
        <div style={{ marginTop: 6 }}>
          <label style={{ display: "block", fontSize: "0.82em" }}>
            <input
              type="checkbox"
              checked={confirm}
              onChange={(e) => setConfirm(e.target.checked)}
            />{" "}
            자동매매 없이 paper 테스트 준비만 승인합니다 (DRAFT 유지 · 신호 기록 시작 아님)
          </label>
          <button
            disabled={!confirm || approveMut.isPending}
            onClick={() => approveMut.mutate()}
            style={{ marginTop: 4 }}
          >
            {approveMut.isPending ? "승인 중…" : "Paper 테스트 준비 승인"}
          </button>
          {approveMut.isError && (
            <span className="muted" style={{ fontSize: "0.8em", color: "#b91c1c", marginLeft: 8 }}>
              승인 실패 — 다시 시도하세요.
            </span>
          )}
        </div>
      )}

      <div className="muted" style={{ marginTop: 4 }}>
        자동매매 아님 · 주문 없음 · 검토용 (실제 신호 기록 시작·전략 버전 승격·실전은 다음 단계에서 별도로 진행)
      </div>
    </div>
  );
}

// 저장된 제안 한 건. PENDING이면 승인/거절(상태만) 버튼을 보여준다. 어떤 실행도 하지 않는다.
function SavedProposalRow({
  proposal,
  candidateId,
}: {
  proposal: CandidateStrategyProposal;
  candidateId: number;
}) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const reviewMut = useMutation({
    // 상태만 approved/rejected로 변경 — 전략 생성/배정/실험/매매 없음.
    mutationFn: (status: "approved" | "rejected") =>
      reviewCandidateStrategyProposal(proposal.id, {
        status,
        reviewed_by: "manual_user",
        review_note: note || undefined,
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["candidate-proposals", candidateId] }),
  });
  const prepareMut = useMutation({
    // DRAFT paper 실험 골격만 준비 — 실행/자동매매/주문 없음.
    mutationFn: () => preparePaperExperiment(proposal.id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["candidate-proposals", candidateId] }),
  });
  const isPending = proposal.status === "pending";
  const isApproved = proposal.status === "approved";

  return (
    <li className="proposal-review-row">
      <div>
        <strong>#{proposal.id}</strong> <code>{proposal.suggested_strategy_type}</code>{" "}
        <span className={`proposal-status status-${proposal.status}`}>
          {STATUS_LABEL[proposal.status] ?? proposal.status}
        </span>
      </div>

      {isPending ? (
        <div className="form-row" style={{ marginTop: 4, alignItems: "center", gap: 6 }}>
          <input
            type="text"
            placeholder="검토 메모(선택)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            style={{ flex: "1 1 160px" }}
          />
          <button disabled={reviewMut.isPending} onClick={() => reviewMut.mutate("approved")}>
            제안 승인
          </button>
          <button disabled={reviewMut.isPending} onClick={() => reviewMut.mutate("rejected")}>
            제안 거절
          </button>
        </div>
      ) : (
        <div className="muted" style={{ fontSize: "0.8em" }}>
          검토자: {proposal.reviewed_by ?? "-"}
          {proposal.review_note ? ` · 메모: ${proposal.review_note}` : ""}
        </div>
      )}

      {/* APPROVED 제안만: 준비됐으면 읽기 전용 실험 카드, 아니면 준비 버튼. PENDING/REJECTED는 없음. */}
      {isApproved &&
        (proposal.experiment_id ? (
          <PreparedExperimentView experimentId={proposal.experiment_id} proposal={proposal} />
        ) : (
          <div className="form-row" style={{ marginTop: 4, alignItems: "center", gap: 6 }}>
            <button disabled={prepareMut.isPending} onClick={() => prepareMut.mutate()}>
              {prepareMut.isPending ? "준비 중…" : "Paper 실험 준비"}
            </button>
            {prepareMut.isSuccess && (
              <span className="muted" style={{ fontSize: "0.8em" }}>
                Paper 실험 준비됨 — 실행/자동매매 아님 (DRAFT)
              </span>
            )}
            {prepareMut.isError && (
              <span className="muted" style={{ fontSize: "0.8em", color: "#b91c1c" }}>
                준비 실패 — 다시 시도하세요.
              </span>
            )}
          </div>
        ))}

      {reviewMut.isSuccess && (
        <div className="muted" style={{ fontSize: "0.8em", marginTop: 2 }}>
          상태만 변경됨 — 실행/배정/전략 생성은 하지 않았습니다.
        </div>
      )}
      {reviewMut.isError && (
        <div className="muted" style={{ fontSize: "0.8em", color: "#b91c1c" }}>
          상태 변경 실패 — 다시 시도하세요.
        </div>
      )}
    </li>
  );
}

interface Props {
  candidate: CandidateEvent;
  onClose: () => void;
}

export default function CandidateStrategyProposalPanel({ candidate, onClose }: Props) {
  const queryClient = useQueryClient();
  const previews = buildProposalPreview(candidate);
  const top = previews[0];

  const { data: saved } = useQuery({
    queryKey: ["candidate-proposals", candidate.id],
    queryFn: () => getCandidateStrategyProposals(candidate.id),
  });

  const saveMut = useMutation({
    // 제안(PENDING)만 저장한다 — 어떤 실행/배정/매매도 하지 않는다.
    mutationFn: () =>
      createCandidateStrategyProposal(candidate.id, {
        suggested_strategy_type: top.strategy,
        rationale: top.reason,
        confidence: candidate.score ? Math.round((candidate.score / 100) * 10000) / 10000 : undefined,
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["candidate-proposals", candidate.id] }),
  });

  return (
    <div className="card proposal-preview" style={{ background: "#f1f5f9" }}>
      <div className="proposal-preview-head">
        <strong>전략 제안 (검토용)</strong>
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

      <div className="form-row" style={{ marginTop: 8, alignItems: "center", gap: 8 }}>
        <button disabled={saveMut.isPending} onClick={() => saveMut.mutate()}>
          {saveMut.isPending ? "저장 중…" : "PENDING 제안으로 저장"}
        </button>
        {saveMut.isSuccess && (
          <span className="action-result value" style={{ margin: 0 }}>
            저장됨 — PENDING 제안 #{saveMut.data.id} (실행/배정 아님)
          </span>
        )}
        {saveMut.isError && (
          <span className="muted" style={{ color: "#b91c1c" }}>저장 실패 — 다시 시도하세요.</span>
        )}
      </div>

      {saved && saved.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <strong style={{ fontSize: "0.86em" }}>저장된 제안 (상태만 관리 — 실행 아님)</strong>
          <ul className="proposal-review-list">
            {saved.map((s) => (
              <SavedProposalRow key={s.id} proposal={s} candidateId={candidate.id} />
            ))}
          </ul>
        </div>
      )}

      <p className="muted safety-note" style={{ fontSize: "0.82em", marginTop: 8 }}>
        ⚠️ ‘제안 저장’은 <strong>PENDING 제안</strong>만 만듭니다 — 전략을 적용하거나 배정을 실행하지
        않으며 전략 버전 생성·자동매매·주문·실전 연결을 하지 않습니다. 확정 배정은 ‘전략 배정’(배정 규칙
        기반 기록)으로, 실험·실전 배치는 사람이 별도로 승인합니다.
      </p>
    </div>
  );
}
