// C-2.30: AI 전략 제안 승인 전 리포트 카드.
// 승인 전에 "무엇이 바뀌고, 무엇이 바뀌지 않는지"를 보여준다.
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  activateChallengerSession,
  comparePaperSignalSessions,
  getProposal,
  getStrategyTransitionPlan,
  prepareChallengerSession,
  prepareSignalChallenger,
} from "../../api/research";
import type {
  ChallengerSessionActivation,
  ChallengerSessionPreparation,
  PaperSignalComparison,
  ProposalStatus,
  SignalChallengerPreparation,
} from "../../types/research";
import TransitionPlanView from "./TransitionPlanView";
import { RawJsonDetails, WillHappenBlock, WillNotHappenBlock } from "./approvalBlocks";
import { STRATEGY_WILL_HAPPEN, STRATEGY_WILL_NOT_HAPPEN } from "./safetyCopy";

// M2.6 — Baseline ↔ Challenger 신호 성과 비교(읽기 전용). 기존 M2.1 compare API 재사용.
// 세션/버전/제안 무변경 · runner 미실행 · 주문/거래 없음.
function cmpFmt(v: number | null): string {
  return v == null ? "-" : String(v);
}

function cmpDelta(v: number | null): string {
  if (v == null) return "-";
  return v > 0 ? `+${v}` : String(v);
}

function ChallengerComparison({
  baselineSessionId,
  challengerSessionId,
  challengerStatus,
  runnerEnabled,
}: {
  baselineSessionId: number;
  challengerSessionId: number;
  challengerStatus: string;
  runnerEnabled?: boolean;
}) {
  const [horizon, setHorizon] = useState(30);
  const [result, setResult] = useState<PaperSignalComparison | null>(null);
  const mut = useMutation({
    mutationFn: () =>
      comparePaperSignalSessions(baselineSessionId, challengerSessionId, horizon),
    onSuccess: (data) => setResult(data),
  });

  const rows: { label: string; b: number | null; c: number | null; d: number | null }[] = result
    ? [
        { label: "신호 수", b: result.baseline.signal_count, c: result.challenger.signal_count, d: result.deltas.signal_count_delta },
        { label: "분석", b: result.baseline.analyzed_count, c: result.challenger.analyzed_count, d: result.deltas.analyzed_count_delta },
        { label: "승률 %", b: result.baseline.win_rate, c: result.challenger.win_rate, d: result.deltas.win_rate_delta },
        { label: "평균 %", b: result.baseline.avg_return_pct, c: result.challenger.avg_return_pct, d: result.deltas.avg_return_pct_delta },
        { label: "최고 %", b: result.baseline.best_return_pct, c: result.challenger.best_return_pct, d: result.deltas.best_return_pct_delta },
        { label: "최저 %", b: result.baseline.worst_return_pct, c: result.challenger.worst_return_pct, d: result.deltas.worst_return_pct_delta },
      ]
    : [];
  const noSignals =
    result != null &&
    (result.baseline.analyzed_count ?? 0) === 0 &&
    (result.challenger.analyzed_count ?? 0) === 0;

  return (
    <div className="signal-compare" style={{ marginTop: 6 }}>
      <div className="muted" style={{ fontSize: "0.8em" }}>
        Baseline ↔ Challenger 비교 (읽기 전용 · 주문 없음 · 거래 없음 · 자동매매 아님 · runner 별도)
      </div>
      <div className="muted" style={{ fontSize: "0.8em" }}>
        기준 세션 #{baselineSessionId} ↔ challenger 세션 #{challengerSessionId} · challenger status:{" "}
        {challengerStatus}
      </div>
      {challengerStatus === "prepared" && (
        <div className="muted" style={{ fontSize: "0.8em", color: "#b45309" }}>
          아직 active가 아니므로 신호 기록 대상이 아닙니다.
        </div>
      )}
      {challengerStatus === "active" && runnerEnabled === false && (
        <div className="muted" style={{ fontSize: "0.8em", color: "#b45309" }}>
          active 상태지만 runner가 꺼져 있으면 새 신호는 생성되지 않습니다.
        </div>
      )}
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", marginTop: 4 }}>
        <select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
          {[5, 15, 30, 60].map((h) => (
            <option key={h} value={h}>
              {h}분
            </option>
          ))}
        </select>
        <button disabled={mut.isPending} onClick={() => mut.mutate()}>
          {mut.isPending ? "비교 중…" : "신호 성과 비교 보기"}
        </button>
      </div>
      {mut.isError && (
        <div className="muted" style={{ fontSize: "0.8em", color: "#b91c1c", marginTop: 4 }}>
          비교 실패 — 세션 id/horizon을 확인하세요.
        </div>
      )}
      {result && (
        <div style={{ marginTop: 6 }}>
          {noSignals && (
            <div className="muted" style={{ fontSize: "0.8em", color: "#b45309" }}>
              아직 비교할 신호 결과가 부족합니다. runner 실행 후 결과가 쌓이면 비교가 의미 있어집니다.
            </div>
          )}
          {result.warnings.map((w) => (
            <div key={w} className="muted" style={{ fontSize: "0.8em", color: "#b45309" }}>
              ⚠ {w}
            </div>
          ))}
          <table className="signal-compare-table" style={{ fontSize: "0.8em", marginTop: 4 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left" }}>지표</th>
                <th>기준 #{result.baseline_session_id}</th>
                <th>challenger #{result.challenger_session_id}</th>
                <th>Δ</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.label}>
                  <td style={{ textAlign: "left" }}>{r.label}</td>
                  <td style={{ textAlign: "right" }}>{cmpFmt(r.b)}</td>
                  <td style={{ textAlign: "right" }}>{cmpFmt(r.c)}</td>
                  <td style={{ textAlign: "right" }}>{cmpDelta(r.d)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="muted" style={{ fontSize: "0.78em", marginTop: 2 }}>
            {result.horizon_minutes}분 forward · 종목 {result.symbol_match ? "동일" : "상이"} · Δ =
            challenger − 기준. 추천/유의성 판단 아님.
          </div>
        </div>
      )}
    </div>
  );
}

// M2.5 Phase 3 — prepared 세션을 active로 전환(런너 대상 자격만). 신호 즉시 생성·주문·거래 없음.
function ChallengerSessionActivate({
  sessionId,
  onActivated,
}: {
  sessionId: number;
  onActivated?: (a: ChallengerSessionActivation) => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const [result, setResult] = useState<ChallengerSessionActivation | null>(null);
  const mut = useMutation({
    mutationFn: () =>
      activateChallengerSession(sessionId, { confirmed: true, confirmed_by: "manual_user" }),
    onSuccess: (data) => {
      setResult(data);
      onActivated?.(data);
    },
  });
  if (result) {
    return (
      <div className="approval-block" style={{ marginTop: 6 }}>
        <strong>신호 세션 active 전환됨</strong>
        <ul className="approval-list">
          <li>active 세션 #{result.session_id} · runner 대상 자격 있음</li>
          <li>
            runner 현재 상태:{" "}
            {result.runner_currently_enabled ? "활성(다음 실행 시 신호 기록)" : "비활성"}
          </li>
          <li>신호 생성은 별도 runner 실행 시에만 · 주문 없음 · 거래 없음 · 자동매매 아님</li>
        </ul>
        {result.warnings.length > 0 && (
          <ul className="approval-list">
            {result.warnings.map((w) => (
              <li key={w} className="muted">ℹ {w}</li>
            ))}
          </ul>
        )}
      </div>
    );
  }
  return (
    <div style={{ marginTop: 6 }}>
      <label className="confirm-check">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        신호 세션을 active로 전환합니다. 신호 생성은 별도 runner 실행 시에만 발생하며 주문/거래는
        생성하지 않습니다.
      </label>
      <div className="form-row">
        <button
          className="primary"
          disabled={!confirmed || mut.isPending}
          onClick={() => mut.mutate()}
        >
          {mut.isPending ? "전환 중…" : "신호 세션 활성화"}
        </button>
      </div>
      {mut.isError && (
        <p className="value error">⚠️ active 전환 실패 — 세션/버전/제안 상태를 확인하세요.</p>
      )}
    </div>
  );
}

// M2.5 Phase 2 — DRAFT challenger 준비 후, 비실행(prepared) PaperSignalSession 준비.
// 세션 시작 컨트롤 없음(시작은 별도 단계). 라벨에 실행/시작/자동매매/주문 사용 금지.
function ChallengerSessionPrepare({ proposalId }: { proposalId: number }) {
  const [confirmed, setConfirmed] = useState(false);
  const [result, setResult] = useState<ChallengerSessionPreparation | null>(null);
  const [activation, setActivation] = useState<ChallengerSessionActivation | null>(null);
  const mut = useMutation({
    mutationFn: () =>
      prepareChallengerSession(proposalId, { confirmed: true, confirmed_by: "manual_user" }),
    onSuccess: (data) => setResult(data),
  });
  if (result) {
    const challengerStatus = activation ? activation.status : result.status;
    return (
      <div className="approval-block" style={{ marginTop: 6 }}>
        <strong>Paper Signal Session 준비됨 (prepared)</strong>
        <ul className="approval-list">
          <li>prepared 세션 #{result.session_id}</li>
          <li>status: {result.status} · runner 미대상</li>
          <li>기준 세션 #{result.baseline_session_id} · challenger 버전 #{result.challenger_version_id}</li>
          <li>주문 없음 · 자동매매 아님</li>
          <li className="muted">비교는 신호 기록 후 가능 · 시작은 별도 단계</li>
        </ul>
        {result.warnings.length > 0 && (
          <ul className="approval-list">
            {result.warnings.map((w) => (
              <li key={w} className="muted">⚠ {w}</li>
            ))}
          </ul>
        )}
        {/* M2.5 Phase 3 — prepared 세션을 active로 전환(런너 대상 자격만) */}
        <ChallengerSessionActivate
          sessionId={result.session_id}
          onActivated={(a) => setActivation(a)}
        />
        {/* M2.6 — Baseline ↔ Challenger 읽기 전용 비교(M2.1 API 재사용) */}
        <ChallengerComparison
          baselineSessionId={result.baseline_session_id}
          challengerSessionId={result.session_id}
          challengerStatus={challengerStatus}
          runnerEnabled={activation?.runner_currently_enabled}
        />
      </div>
    );
  }
  return (
    <div style={{ marginTop: 6 }}>
      <label className="confirm-check">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        prepared 세션만 생성하며 신호 기록 시작/주문/자동매매는 하지 않습니다
      </label>
      <div className="form-row">
        <button
          className="primary"
          disabled={!confirmed || mut.isPending}
          onClick={() => mut.mutate()}
        >
          {mut.isPending ? "준비 중…" : "Paper Signal Session 준비"}
        </button>
      </div>
      {mut.isError && (
        <p className="value error">⚠️ 세션 준비 실패 — challenger 준비 상태를 확인하세요.</p>
      )}
    </div>
  );
}

interface Props {
  proposalId: number;
  status: ProposalStatus;
  onApprove: () => void;
  onReject: () => void;
  approving?: boolean;
  rejecting?: boolean;
}

export default function StrategyProposalReportCard({
  proposalId,
  status,
  onApprove,
  onReject,
  approving,
  rejecting,
}: Props) {
  const [confirmed, setConfirmed] = useState(false);

  const detailQ = useQuery({
    queryKey: ["proposal", proposalId],
    queryFn: () => getProposal(proposalId),
  });
  const planQ = useQuery({
    queryKey: ["strategy-transition-plan", proposalId],
    queryFn: () => getStrategyTransitionPlan(proposalId),
  });

  const detail = detailQ.data;
  const plan = planQ.data;
  const isPending = status === "pending";
  const planOk = !!plan && plan.plan_valid;
  // 승인 가능 조건: pending + 확인 체크 + 전환계획 로드 성공 + plan_valid + 진행중 아님.
  const canApprove = isPending && confirmed && planOk && !approving;

  // M2.2 — paper_signal 트랙 제안은 공유 approve(TESTING) 경로를 쓰지 않는다.
  // 대신 DRAFT-only challenger 준비만 노출한다(승인/머티리얼라이즈 아님).
  const isSignalTrack = detail?.source === "paper_signal_analysis";
  const [challengerConfirmed, setChallengerConfirmed] = useState(false);
  const [challengerResult, setChallengerResult] =
    useState<SignalChallengerPreparation | null>(null);
  const challengerMut = useMutation({
    mutationFn: () =>
      prepareSignalChallenger(proposalId, {
        confirmed: true,
        confirmed_by: "manual_user",
      }),
    onSuccess: (data) => setChallengerResult(data),
  });

  return (
    <div className="card approval-report-card">
      <h4>전략 제안 #{proposalId} 승인 리포트</h4>

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
            <strong>변경점 (before → after)</strong>
            {detail.diff.length === 0 ? (
              <p className="muted">변경 없음</p>
            ) : (
              <ul className="approval-list">
                {detail.diff.map((d) => (
                  <li key={d.key}>
                    {d.key}: <span className="muted">{JSON.stringify(d.before)}</span> →{" "}
                    <strong>{JSON.stringify(d.after)}</strong>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* 전환 계획 — signal 트랙은 공유 approve(TESTING) 경로를 쓰지 않으므로 숨긴다. */}
      {!isSignalTrack && (
        <>
          {planQ.isLoading && <p className="muted">전환 계획 불러오는 중…</p>}
          {planQ.isError && (
            <p className="value error">
              ⚠️ 전환 계획을 불러오지 못했습니다. 안전을 위해 승인할 수 없습니다.
            </p>
          )}
          {plan && <TransitionPlanView plan={plan} />}

          <WillHappenBlock items={STRATEGY_WILL_HAPPEN} />
          <WillNotHappenBlock items={STRATEGY_WILL_NOT_HAPPEN} />

          {plan && <RawJsonDetails label="transition_plan" data={plan} />}
        </>
      )}

      {/* M2.2 — paper_signal 트랙: DRAFT-only challenger 준비 (승인 아님). */}
      {isSignalTrack && isPending && (
        <div className="approval-actions">
          <p className="muted">
            Paper signal 트랙 제안 — 공유 승인(TESTING) 경로 미사용. DRAFT challenger만 준비합니다
            (DRAFT-only · runner 미대상 · 주문 없음 · 세션 시작 없음 · 자동매매 아님).
          </p>
          {!challengerResult ? (
            <>
              <label className="confirm-check">
                <input
                  type="checkbox"
                  checked={challengerConfirmed}
                  onChange={(e) => setChallengerConfirmed(e.target.checked)}
                />
                DRAFT challenger만 생성하며 자동매매/주문/세션 시작은 하지 않습니다
              </label>
              <div className="form-row">
                <button
                  className="primary"
                  disabled={!challengerConfirmed || challengerMut.isPending}
                  onClick={() => challengerMut.mutate()}
                >
                  {challengerMut.isPending ? "준비 중…" : "Signal Challenger 준비"}
                </button>
              </div>
              {challengerMut.isError && (
                <p className="value error">
                  ⚠️ challenger 준비 실패 — 제안 상태/연결을 확인하세요.
                </p>
              )}
            </>
          ) : (
            <div className="approval-block">
              <strong>DRAFT challenger 준비됨</strong>
              <ul className="approval-list">
                <li>challenger 버전 #{challengerResult.challenger_version_id}</li>
                <li>status: {challengerResult.challenger_status} (DRAFT-only)</li>
                <li>auto_trade_enabled: {String(challengerResult.auto_trade_enabled)} · runner 미대상</li>
                <li>주문 없음 · 세션 시작 없음 · 자동매매 아님</li>
                <li className="muted">세션은 별도 승인 후 시작 · 제안 상태는 {challengerResult.proposal_status} 유지</li>
              </ul>
              {challengerResult.warnings.length > 0 && (
                <ul className="approval-list">
                  {challengerResult.warnings.map((w) => (
                    <li key={w} className="muted">⚠ {w}</li>
                  ))}
                </ul>
              )}
              {/* M2.5 Phase 2 — DRAFT challenger 준비 후 비실행 prepared 세션 준비 */}
              <ChallengerSessionPrepare proposalId={proposalId} />
            </div>
          )}
        </div>
      )}

      {/* 승인 UX: one-click 금지. 확인 체크 필수. (signal 트랙은 위에서 처리) */}
      {isPending && !isSignalTrack ? (
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
      ) : !isPending ? (
        <p className="muted">검토 완료 ({detail?.reviewed_by ?? "-"})</p>
      ) : null}
    </div>
  );
}
