// C-2.30: AI 전략 제안 승인 전 리포트 카드.
// 승인 전에 "무엇이 바뀌고, 무엇이 바뀌지 않는지"를 보여준다.
import { type ReactNode, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  activateChallengerSession,
  activatePaperSignalRecurringRun,
  comparePaperSignalSessions,
  createPaperSignalRecurringRun,
  getPaperSignalRecurringDispatcherReadiness,
  getProposal,
  getStrategyTransitionPlan,
  listPaperSignalRecurringRuns,
  prepareChallengerSession,
  prepareSignalChallenger,
  runPaperSignalPairOnce,
  runPaperSignalSessionOnce,
  stopPaperSignalRecurringRun,
  tickPaperSignalRecurringRunOnce,
} from "../../api/research";
import type {
  ChallengerSessionActivation,
  ChallengerSessionPreparation,
  PaperSignalComparison,
  PaperSignalPairRunOnceResult,
  PaperSignalRecurringRun,
  PaperSignalRecurringTickResult,
  PaperSignalRunOnceResult,
  RecurringDispatcherReadiness,
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

// M2.12 — 안전 경계를 한 줄 배지로 일관 표시(읽기 전용 표식). 어떤 동작도 트리거하지 않음.
const SAFETY_BADGES = [
  "SignalLog만",
  "주문 없음",
  "거래 없음",
  "자동매매 아님",
  "runner 별도",
];

function SafetyBadges() {
  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 2 }}>
      {SAFETY_BADGES.map((b) => (
        <span
          key={b}
          className="muted"
          style={{
            fontSize: "0.7em",
            border: "1px solid #d1d5db",
            borderRadius: 4,
            padding: "0 4px",
          }}
        >
          {b}
        </span>
      ))}
    </div>
  );
}

// M2.12 — 단계 가이드. 현재 상태에 따라 사용자가 다음에 무엇을 눌러야 하는지 알려준다(표시 전용).
const LIFECYCLE_STEPS = [
  "Challenger 세션 준비",
  "Active 전환",
  "페어 신호 1회 기록",
  "신호 성과 비교 보기",
  "반복 runner는 별도 승인 후",
];

function LifecycleGuide({ currentIndex }: { currentIndex: number }) {
  return (
    <ol style={{ margin: "4px 0", paddingLeft: 18, fontSize: "0.78em" }}>
      {LIFECYCLE_STEPS.map((s, i) => {
        const done = i < currentIndex;
        const cur = i === currentIndex;
        return (
          <li
            key={s}
            style={{
              fontWeight: cur ? 600 : 400,
              color: done ? "#16a34a" : cur ? "#111827" : "#9ca3af",
              listStyle: "none",
            }}
          >
            {done ? "✓" : `${i + 1}.`} {s}
            {cur && <span style={{ marginLeft: 4, color: "#2563eb" }}>← 지금</span>}
          </li>
        );
      })}
    </ol>
  );
}

// M2.14G — 운영자 명료성을 위한 섹션 그룹(표시 전용). 제목 + helper로 목적을 분리한다.
function SectionGroup({
  title,
  helper,
  children,
}: {
  title: string;
  helper: string;
  children: ReactNode;
}) {
  return (
    <div style={{ marginTop: 8, borderLeft: "3px solid #e5e7eb", paddingLeft: 8 }}>
      <div style={{ fontSize: "0.82em", fontWeight: 700 }}>{title}</div>
      <div className="muted" style={{ fontSize: "0.75em", marginBottom: 2 }}>
        {helper}
      </div>
      {children}
    </div>
  );
}

// M2.14G — 대략적인 참고용 표본 힌트(기존 카운트만 사용 · 새 백엔드 지표 계산 없음).
// paired = min(baseline, challenger) 신호 수. <10 표본 부족 / 10~29 관찰 중 / >=30 비교 시작 가능.
function sampleSizeHint(paired: number): { label: string; color: string } {
  if (paired < 10) return { label: "표본 부족", color: "#b45309" };
  if (paired < 30) return { label: "관찰 중", color: "#2563eb" };
  return { label: "비교 시작 가능", color: "#16a34a" };
}

// M2.8 — 선택한 단일 active 세션에 신호 1회 기록(SignalLog만). 반복/스케줄러/주문/거래 없음.
// M2.11 — 공정 비교용: baseline + challenger 두 active 세션을 각각 1회 신호 기록(SignalLog만).
// 권장 동작(단일 세션보다 공정). 반복/스케줄러/주문/거래 아님.
function PairRunOnce({
  baselineSessionId,
  challengerSessionId,
  challengerStatus,
  onPairComplete,
}: {
  baselineSessionId: number;
  challengerSessionId: number;
  challengerStatus: string;
  onPairComplete?: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const [result, setResult] = useState<PaperSignalPairRunOnceResult | null>(null);
  const mut = useMutation({
    mutationFn: () =>
      runPaperSignalPairOnce(baselineSessionId, challengerSessionId, {
        confirmed: true,
        confirmed_by: "manual_user",
      }),
    onSuccess: (data) => {
      setResult(data);
      onPairComplete?.();
    },
  });
  if (challengerStatus !== "active") {
    return (
      <div className="muted" style={{ fontSize: "0.8em", marginTop: 4 }}>
        페어 신호 기록은 active 전환 후 가능합니다.
      </div>
    );
  }
  const sideText = (label: string, s: PaperSignalPairRunOnceResult["baseline"]) =>
    s.signal_created
      ? `${label} SignalLog #${s.signal_id} 생성`
      : `${label} skipped: ${s.reason ?? "사유 없음"}`;
  return (
    <div style={{ marginTop: 6 }}>
      <div style={{ fontSize: "0.82em", fontWeight: 600 }}>
        단발 비교용 1회 기록 (권장)
      </div>
      <div className="muted" style={{ fontSize: "0.78em" }}>
        비교를 위해 현재 페어를 한 번 기록합니다. 계획의 completed_runs에는 누적되지 않습니다.
      </div>
      <label className="confirm-check" style={{ fontSize: "0.82em" }}>
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        기준 세션과 challenger 세션을 각각 1회 신호 기록합니다. 주문/거래는 생성하지 않습니다.
      </label>
      <div className="form-row">
        <button
          className="primary"
          disabled={!confirmed || mut.isPending}
          onClick={() => mut.mutate()}
        >
          {mut.isPending ? "기록 중…" : "페어 신호 1회 기록"}
        </button>
        <span className="muted" style={{ fontSize: "0.78em", marginLeft: 6 }}>
          SignalLog만 · 주문 없음 · 거래 없음 · 자동매매 아님 · 반복 실행 아님
        </span>
      </div>
      {mut.isError && (
        <div className="muted" style={{ fontSize: "0.8em", color: "#b91c1c", marginTop: 4 }}>
          페어 기록 실패 — 두 세션 상태/관계(같은 baseline·종목·DRAFT)를 확인하세요.
        </div>
      )}
      {result && (
        <div style={{ fontSize: "0.8em", marginTop: 4 }}>
          <div className="muted">{sideText("기준 세션", result.baseline)}</div>
          <div className="muted">{sideText("Challenger", result.challenger)}</div>
          <div className="muted">
            orders {result.orders_created} · trades {result.trades_created} · runner{" "}
            {String(result.runner_enabled)}
          </div>
          {result.warnings.map((w) => (
            <div key={w} className="muted" style={{ color: "#b45309" }}>
              ℹ {w}
            </div>
          ))}
          <div style={{ fontWeight: 600, color: "#2563eb", marginTop: 2 }}>
            이제 아래 ‘신호 성과 비교 보기’를 다시 눌러 결과를 확인하세요.
          </div>
        </div>
      )}
    </div>
  );
}

// M2.14C — pair-scoped 수동 누적 신호 기록 *계획* 관리(생성/활성화/1회 tick/중지/조회).
// 모든 동작은 사람 클릭으로만 호출 — page-load 자동 호출/백그라운드 폴링/자동 tick 없음.
// dispatcher/scheduler/job 아님 · 선택한 페어만 · tick은 최대 2 SignalLog · 주문/거래 없음.
// M2.14E — "반복"→"수동 누적", active→"수동 기록 가능", next_run_at→"다음 기준 시각" 카피로 오해 축소.
const RECURRING_BADGES = [
  "선택한 페어만",
  "SignalLog만",
  "주문 없음",
  "거래 없음",
  "자동매매 아님",
  "자동 실행 없음",
  "디스패처 없음",
  "스케줄러/잡 없음",
  "버튼 클릭 시에만",
];

// M2.14E — 백엔드 raw status를 사람이 읽는 한글 부제로 매핑(원시 status는 디버그용으로 함께 노출).
// active를 "수동 기록 가능"으로 표시해 "실행 중"으로 오해하지 않게 한다.
function statusLabel(status: string): string {
  switch (status) {
    case "prepared":
      return "준비됨";
    case "active":
      return "수동 기록 가능";
    case "stopped":
      return "중지됨";
    case "completed":
      return "완료됨";
    case "failed":
      return "실패";
    default:
      return status;
  }
}

function planLine(p: PaperSignalRecurringRun): string {
  // next_run_at은 디스패처가 없어 "다음 기준 시각" 메모일 뿐(자동 실행 아님).
  return (
    `#${p.id} · ${statusLabel(p.status)}(${p.status}) · 간격 ${p.interval_seconds}s · ` +
    `${p.completed_runs}/${p.max_runs}회 기록 · ` +
    `마지막 ${p.last_run_at ?? "없음"} · 다음 기준 ${p.next_run_at ?? "없음"}`
  );
}

function RecurringPlanControls({
  baselineSessionId,
  challengerSessionId,
  challengerStatus,
}: {
  baselineSessionId: number;
  challengerSessionId: number;
  challengerStatus: string;
}) {
  const [tickIntervalSec, setTickIntervalSec] = useState(60);
  const [maxRuns, setMaxRuns] = useState(30);
  const [createOk, setCreateOk] = useState(false);
  const [plans, setPlans] = useState<PaperSignalRecurringRun[] | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [tick, setTick] = useState<PaperSignalRecurringTickResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // 활성화/tick/중지 확인 체크(액션별 분리).
  const [activateOk, setActivateOk] = useState(false);
  const [tickOk, setTickOk] = useState(false);
  const [stopOk, setStopOk] = useState(false);

  const reload = useMutation({
    // 현재 페어의 계획만 추려서 보여준다(서버는 전체 목록 — 클라이언트에서 페어 필터).
    mutationFn: () => listPaperSignalRecurringRuns(),
    onSuccess: (all) =>
      setPlans(
        all.filter(
          (p) =>
            p.baseline_session_id === baselineSessionId &&
            p.challenger_session_id === challengerSessionId,
        ),
      ),
    onError: (e: unknown) => setErr(String(e)),
  });
  const createMut = useMutation({
    mutationFn: () =>
      createPaperSignalRecurringRun({
        baseline_session_id: baselineSessionId,
        challenger_session_id: challengerSessionId,
        interval_seconds: tickIntervalSec,
        max_runs: maxRuns,
        confirmed: true,
        confirmed_by: "manual_user",
      }),
    onSuccess: (p) => {
      setErr(null);
      setSelectedId(p.id);
      reload.mutate();
    },
    onError: (e: unknown) => setErr(String(e)),
  });
  const activateMut = useMutation({
    mutationFn: (id: number) =>
      activatePaperSignalRecurringRun(id, { confirmed: true, confirmed_by: "manual_user" }),
    onSuccess: () => {
      setErr(null);
      reload.mutate();
    },
    onError: (e: unknown) => setErr(String(e)),
  });
  const tickMut = useMutation({
    mutationFn: (id: number) =>
      tickPaperSignalRecurringRunOnce(id, { confirmed: true, confirmed_by: "manual_user" }),
    onSuccess: (r) => {
      setErr(null);
      setTick(r);
      reload.mutate();
    },
    onError: (e: unknown) => setErr(String(e)),
  });
  const stopMut = useMutation({
    mutationFn: (id: number) =>
      stopPaperSignalRecurringRun(id, { confirmed: true, confirmed_by: "manual_user" }),
    onSuccess: () => {
      setErr(null);
      reload.mutate();
    },
    onError: (e: unknown) => setErr(String(e)),
  });

  if (challengerStatus !== "active") {
    return (
      <div className="muted" style={{ fontSize: "0.8em", marginTop: 6 }}>
        수동 누적 신호 기록 계획은 challenger 세션을 수동 기록 가능 상태(active)로 전환한 뒤 만들 수 있습니다.
      </div>
    );
  }

  const selected = plans?.find((p) => p.id === selectedId) ?? null;

  return (
    <details style={{ marginTop: 6 }}>
      <summary style={{ fontSize: "0.84em", fontWeight: 600, cursor: "pointer" }}>
        계획 누적용: 수동 누적 신호 기록 계획
      </summary>
      <div className="muted" style={{ fontSize: "0.78em", marginTop: 2 }}>
        선택한 기준/챌린저 페어만, 사람이 버튼을 누를 때만 SignalLog를 추가합니다. 자동 실행/디스패처/스케줄러는
        없습니다.
      </div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 2 }}>
        {RECURRING_BADGES.map((b) => (
          <span
            key={b}
            className="muted"
            style={{ fontSize: "0.7em", border: "1px solid #d1d5db", borderRadius: 4, padding: "0 4px" }}
          >
            {b}
          </span>
        ))}
      </div>

      {/* 계획 생성(prepared) */}
      <div style={{ marginTop: 6 }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <label style={{ fontSize: "0.78em" }}>
            간격(s)
            <select value={tickIntervalSec} onChange={(e) => setTickIntervalSec(Number(e.target.value))}>
              {[60, 120, 300, 600].map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </label>
          <label style={{ fontSize: "0.78em" }}>
            max_runs
            <select value={maxRuns} onChange={(e) => setMaxRuns(Number(e.target.value))}>
              {[1, 5, 10, 30, 60].map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </label>
        </div>
        <label className="confirm-check" style={{ fontSize: "0.8em" }}>
          <input type="checkbox" checked={createOk} onChange={(e) => setCreateOk(e.target.checked)} />
          이 계획은 아직 자동 실행되지 않으며, SignalLog만 기록하는 계획입니다. 주문/거래는 생성하지 않습니다.
        </label>
        <div className="form-row">
          <button
            className="primary"
            disabled={!createOk || createMut.isPending}
            onClick={() => createMut.mutate()}
          >
            {createMut.isPending ? "만드는 중…" : "수동 누적 계획 만들기"}
          </button>
          <button disabled={reload.isPending} onClick={() => reload.mutate()} style={{ marginLeft: 6 }}>
            계획 상태 새로고침
          </button>
        </div>
      </div>

      {err && (
        <div className="muted" style={{ fontSize: "0.8em", color: "#b91c1c", marginTop: 4 }}>
          요청 실패 — 계획 상태/관계(같은 baseline·종목·DRAFT·active)를 확인하세요.
        </div>
      )}

      {/* 현재 페어 계획 목록 + 선택 */}
      {plans && plans.length > 0 && (
        <div style={{ marginTop: 6, fontSize: "0.8em" }}>
          {plans.map((p) => (
            <label key={p.id} style={{ display: "block", cursor: "pointer" }}>
              <input
                type="radio"
                name={`plan-${baselineSessionId}-${challengerSessionId}`}
                checked={selectedId === p.id}
                onChange={() => setSelectedId(p.id)}
              />{" "}
              {planLine(p)}
            </label>
          ))}
        </div>
      )}
      {plans && plans.length === 0 && (
        <div className="muted" style={{ fontSize: "0.78em", marginTop: 4 }}>
          이 페어의 계획이 없습니다. 위에서 준비 상태 계획을 만들어 보세요.
        </div>
      )}

      {/* 선택 계획 액션 */}
      {selected && (
        <div style={{ marginTop: 6, fontSize: "0.8em", borderTop: "1px solid #e5e7eb", paddingTop: 4 }}>
          <div style={{ fontWeight: 600 }}>선택: {planLine(selected)}</div>

          {selected.status === "prepared" && (
            <div style={{ marginTop: 4 }}>
              <label className="confirm-check" style={{ fontSize: "0.8em" }}>
                <input type="checkbox" checked={activateOk} onChange={(e) => setActivateOk(e.target.checked)} />
                수동 기록 가능 상태입니다. 이 상태만으로는 아무 신호도 기록되지 않습니다. 사람이 누르는 tick의
                후보가 될 뿐입니다(자동 실행/디스패처 아님).
              </label>
              <button
                disabled={!activateOk || activateMut.isPending}
                onClick={() => activateMut.mutate(selected.id)}
              >
                {activateMut.isPending ? "전환 중…" : "수동 기록 가능 상태로 전환"}
              </button>
              <div className="muted" style={{ marginTop: 2 }}>
                전환해도 아무 신호도 기록되지 않습니다 — 아래에서 사람이 1회씩 눌러야 쌓입니다.
              </div>
            </div>
          )}

          {selected.status === "active" && (
            <div style={{ marginTop: 4 }}>
              <label className="confirm-check" style={{ fontSize: "0.8em" }}>
                <input type="checkbox" checked={tickOk} onChange={(e) => setTickOk(e.target.checked)} />
                선택한 계획의 completed_runs를 1회 늘리며, 기준/챌린저 각각 최대 1개(총 최대 2개)의 SignalLog를
                추가합니다. 주문/거래는 생성하지 않습니다.
              </label>
              <button
                className="primary"
                disabled={!tickOk || tickMut.isPending}
                onClick={() => tickMut.mutate(selected.id)}
              >
                {tickMut.isPending ? "기록 중…" : "계획 누적용 1회 기록"}
              </button>
            </div>
          )}

          {(selected.status === "prepared" || selected.status === "active") && (
            <div style={{ marginTop: 4 }}>
              <label className="confirm-check" style={{ fontSize: "0.8em" }}>
                <input type="checkbox" checked={stopOk} onChange={(e) => setStopOk(e.target.checked)} />
                이 계획을 stopped 상태로 바꿉니다. 세션/전략/제안 상태는 바꾸지 않습니다.
              </label>
              <button
                className="danger"
                disabled={!stopOk || stopMut.isPending}
                onClick={() => stopMut.mutate(selected.id)}
              >
                {stopMut.isPending ? "중지 중…" : "계획 중지"}
              </button>
            </div>
          )}
        </div>
      )}

      {/* tick 결과 */}
      {tick && (
        <div style={{ marginTop: 6, fontSize: "0.8em" }}>
          <div className="muted">
            기준 세션{" "}
            {tick.baseline.signal_created
              ? `SignalLog #${tick.baseline.signal_id} 생성`
              : `skipped: ${tick.baseline.reason ?? "사유 없음"}`}
          </div>
          <div className="muted">
            Challenger{" "}
            {tick.challenger.signal_created
              ? `SignalLog #${tick.challenger.signal_id} 생성`
              : `skipped: ${tick.challenger.reason ?? "사유 없음"}`}
          </div>
          <div className="muted">
            {tick.completed_runs}/{tick.max_runs}회 기록 · {statusLabel(tick.status)}({tick.status}) · orders{" "}
            {tick.orders_created} · trades {tick.trades_created}
          </div>
          <div className="muted" style={{ fontSize: "0.92em" }}>
            다음 기준 시각 {tick.next_run_at ?? "없음(완료)"} — 디스패처가 없어 자동 실행되지 않습니다(수동 기록
            참고용 메타데이터).
          </div>
          {tick.warnings.map((w) => (
            <div key={w} className="muted" style={{ color: "#b45309" }}>ℹ {w}</div>
          ))}
          <div className="muted">결과 확인을 위해 아래 ‘신호 성과 비교 보기’를 다시 눌러보세요.</div>
        </div>
      )}
    </details>
  );
}

// M2.14B-3e — 디스패처 readiness/status를 읽기 전용으로 보여준다.
// 실행/활성화/스케줄러/설정 토글 컨트롤 없음 · mutation 없음 · 자동 폴링 없음(수동 새로고침만).
const DISPATCHER_STATUS_BADGES = [
  "읽기 전용",
  "실행 버튼 없음",
  "스케줄러 없음",
  "API 실행 엔드포인트 없음",
  "SignalLog 생성 없음",
  "주문 없음",
  "거래 없음",
  "자동매매 아님",
];

function flagText(label: string, value: boolean, safeWhenFalse = true): JSX.Element {
  // safeWhenFalse=true면 false가 안전(초록), true가 경고(주황). 반대면 반대.
  const safe = safeWhenFalse ? !value : value;
  return (
    <div style={{ color: safe ? "#16a34a" : "#b45309" }}>
      {safe ? "✓" : "⚠"} {label}: {String(value)}
    </div>
  );
}

function RecurringDispatcherStatusPanel() {
  const [status, setStatus] = useState<RecurringDispatcherReadiness | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // 읽기 전용 조회만 — POST/PATCH/DELETE 없음. 사람이 누를 때만 호출(자동 폴링/useEffect 없음).
  const load = useMutation({
    mutationFn: () => getPaperSignalRecurringDispatcherReadiness(),
    onSuccess: (d) => {
      setErr(null);
      setStatus(d);
    },
    onError: (e: unknown) => setErr(String(e)),
  });

  return (
    <details style={{ marginTop: 6 }}>
      <summary style={{ fontSize: "0.84em", fontWeight: 600, cursor: "pointer" }}>
        디스패처 상태(읽기 전용)
      </summary>
      <div className="muted" style={{ fontSize: "0.78em", marginTop: 2 }}>
        현재는 상태만 보여줍니다. 이 화면에서는 어떤 계획도 실행하지 않습니다.
      </div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 2 }}>
        {DISPATCHER_STATUS_BADGES.map((b) => (
          <span
            key={b}
            className="muted"
            style={{ fontSize: "0.7em", border: "1px solid #d1d5db", borderRadius: 4, padding: "0 4px" }}
          >
            {b}
          </span>
        ))}
      </div>
      <div className="form-row" style={{ marginTop: 4 }}>
        <button disabled={load.isPending} onClick={() => load.mutate()}>
          {load.isPending ? "불러오는 중…" : "상태 새로고침"}
        </button>
      </div>

      {err && (
        <div className="muted" style={{ fontSize: "0.8em", color: "#b91c1c", marginTop: 4 }}>
          상태 조회 실패 — 잠시 후 다시 시도하세요.
        </div>
      )}

      {status && (
        <div style={{ fontSize: "0.8em", marginTop: 6 }}>
          {/* M2.14G — 정보 과밀 축소: 핵심 요약을 먼저, 원시 상세는 중첩 details로 접는다. */}
          <div style={{ display: "grid", gap: 1 }}>
            <div>실행 가능 여부: <b style={{ color: "#16a34a" }}>불가</b></div>
            <div>스케줄러: 없음</div>
            <div>API 실행 엔드포인트: 없음</div>
            <div>프론트 실행 버튼: 없음</div>
            <div>자동매매: 아님</div>
          </div>
          <div className="muted" style={{ color: "#2563eb", marginTop: 4 }}>
            due 계획이 있어도 자동 실행되지 않습니다.
          </div>

          <details style={{ marginTop: 6 }}>
            <summary className="muted" style={{ fontSize: "0.78em", cursor: "pointer" }}>
              원시 상태 자세히(표시 전용)
            </summary>
            <div style={{ display: "grid", gap: 6, marginTop: 4 }}>
              {/* 실행 가능 여부(원시) */}
              <div>
                <div style={{ fontWeight: 600 }}>실행 가능 여부</div>
                <div style={{ color: status.can_execute ? "#b45309" : "#16a34a" }}>
                  {status.can_execute ? "⚠" : "✓"} can_execute: {String(status.can_execute)} ·{" "}
                  {status.execution_blocked_reason}
                </div>
                <div className="muted">현재 UI/API에서는 디스패처를 실행할 수 없습니다.</div>
              </div>

              {/* 서비스 코어 */}
              <div>
                <div style={{ fontWeight: 600 }}>서비스 코어</div>
                <div className="muted">단계: {status.dispatcher_stage}</div>
                {flagText("service_core_implemented", status.service_core_implemented, false)}
                <div className="muted">
                  내부 코어는 존재하지만, 스케줄러나 API 실행 경로에 연결되어 있지 않습니다.
                </div>
              </div>

              {/* 스케줄러 */}
              <div>
                <div style={{ fontWeight: 600 }}>스케줄러</div>
                {flagText("scheduler_job_registered", status.scheduler_job_registered)}
                {flagText("scheduler_dispatcher_implemented", status.scheduler_dispatcher_implemented)}
                {flagText("api_execution_endpoint_registered", status.api_execution_endpoint_registered)}
                <div className="muted">스케줄러 잡이 등록되어 있지 않아 자동 실행되지 않습니다.</div>
              </div>

              {/* 설정 플래그(토글 없음 — 표시 전용) */}
              <div>
                <div style={{ fontWeight: 600 }}>설정 플래그(표시 전용 · 토글 없음)</div>
                {flagText(
                  "paper_signal_recurring_plan_dispatcher_enabled",
                  status.config.paper_signal_recurring_plan_dispatcher_enabled,
                )}
                {flagText(
                  "paper_signal_session_runner_enabled",
                  status.config.paper_signal_session_runner_enabled,
                )}
                {flagText("kis_real_trading_enabled", status.config.kis_real_trading_enabled)}
              </div>

              {/* 계획 카운트 */}
              <div>
                <div style={{ fontWeight: 600 }}>계획 카운트</div>
                <div className="muted">
                  total {status.plan_counts.total} · active {status.plan_counts.active} · due_active{" "}
                  {status.plan_counts.due_active} · not_due_active {status.plan_counts.not_due_active} ·
                  missing_next {status.plan_counts.active_missing_next_run_at} · exhausted{" "}
                  {status.plan_counts.active_exhausted} · with_last_error{" "}
                  {status.plan_counts.with_last_error}
                </div>
              </div>

              {/* 안전 불변식 */}
              <div>
                <div style={{ fontWeight: 600 }}>안전 불변식</div>
                <div className="muted">
                  recurring만 스캔: {String(status.safety_invariants.scans_recurring_runs_only)} · 전역 런너
                  금지: {String(status.safety_invariants.global_runner_forbidden)} · 주문 금지:{" "}
                  {String(status.safety_invariants.orders_forbidden)} · 거래 금지:{" "}
                  {String(status.safety_invariants.trades_forbidden)} · broker/KIS 금지:{" "}
                  {String(status.safety_invariants.broker_kis_forbidden)}
                </div>
              </div>

              {/* warnings */}
              {status.warnings.length > 0 && (
                <div>
                  <div style={{ fontWeight: 600 }}>안내</div>
                  {status.warnings.map((w) => (
                    <div key={w} className="muted">
                      ℹ {w}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </details>
        </div>
      )}
    </details>
  );
}

function SessionRunOnce({
  sessionId,
  challengerStatus,
}: {
  sessionId: number;
  challengerStatus: string;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const [result, setResult] = useState<PaperSignalRunOnceResult | null>(null);
  const mut = useMutation({
    mutationFn: () =>
      runPaperSignalSessionOnce(sessionId, { confirmed: true, confirmed_by: "manual_user" }),
    onSuccess: (data) => setResult(data),
  });
  if (challengerStatus !== "active") {
    return (
      <div className="muted" style={{ fontSize: "0.8em", marginTop: 4 }}>
        신호 1회 기록은 active 전환 후 가능합니다.
      </div>
    );
  }
  return (
    <div style={{ marginTop: 6 }}>
      <label className="confirm-check" style={{ fontSize: "0.82em" }}>
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        선택한 세션 1개에 대해 신호를 1회 기록합니다. 주문/거래는 생성하지 않습니다.
      </label>
      <div className="form-row">
        <button disabled={!confirmed || mut.isPending} onClick={() => mut.mutate()}>
          {mut.isPending ? "기록 중…" : "신호 1회 기록"}
        </button>
        <span className="muted" style={{ fontSize: "0.78em", marginLeft: 6 }}>
          선택 세션만 · SignalLog만 · 주문 없음 · 거래 없음 · 자동매매 아님 · 반복 실행 아님
        </span>
      </div>
      {mut.isError && (
        <div className="muted" style={{ fontSize: "0.8em", color: "#b91c1c", marginTop: 4 }}>
          기록 실패 — 세션 상태/버전을 확인하세요.
        </div>
      )}
      {result && (
        <div className="muted" style={{ fontSize: "0.8em", marginTop: 4 }}>
          {result.signal_created
            ? `신호 1건 기록됨 (signal #${result.signal_id})`
            : `신호 미기록 — ${result.reason ?? "사유 없음"}`}{" "}
          · orders {result.orders_created} · trades {result.trades_created} · 위에서 다시 비교하세요.
        </div>
      )}
    </div>
  );
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
  const [pairRan, setPairRan] = useState(false);
  const mut = useMutation({
    mutationFn: () =>
      comparePaperSignalSessions(baselineSessionId, challengerSessionId, horizon),
    onSuccess: (data) => setResult(data),
  });

  // M2.12 — 현재 단계 계산(표시 전용). prepared=1(Active 전환), active 미기록=2(페어 기록),
  // active 기록/비교 단계=3(비교 보기). 반복 runner(4)는 별도 승인 후라 강조하지 않는다.
  const currentStep =
    challengerStatus === "active" ? (pairRan || result ? 3 : 2) : 1;

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
  // M2.12 — 빈/저데이터 비교 안내는 신호 수 기준으로 명확화한다.
  const bSig = result?.baseline.signal_count ?? 0;
  const cSig = result?.challenger.signal_count ?? 0;
  const bothZero = result != null && bSig === 0 && cSig === 0;
  const oneZero = result != null && !bothZero && (bSig === 0 || cSig === 0);

  return (
    <div className="signal-compare" style={{ marginTop: 6 }}>
      <LifecycleGuide currentIndex={currentStep} />
      <SafetyBadges />
      <div className="muted" style={{ fontSize: "0.8em", marginTop: 2 }}>
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
      {/* M2.14G — 네 가지 영역을 목적별로 분리: 단발 비교 / 계획 누적 / 디스패처 상태(읽기) / 고급·디버그 */}
      {/* 1. 단발 비교 — 계획 없이 현재 페어를 한 번 기록 */}
      <SectionGroup
        title="단발 비교"
        helper="선택한 baseline/challenger 페어를 지금 한 번만 기록합니다. 반복 계획에는 누적되지 않습니다."
      >
        <PairRunOnce
          baselineSessionId={baselineSessionId}
          challengerSessionId={challengerSessionId}
          challengerStatus={challengerStatus}
          onPairComplete={() => setPairRan(true)}
        />
      </SectionGroup>
      {/* 2. 계획 누적 — 반복 계획에 수동으로 1회씩 누적 */}
      <SectionGroup
        title="계획 누적"
        helper="반복 계획에 기록을 누적합니다. 수동으로 누를 때만 1회 기록됩니다."
      >
        <RecurringPlanControls
          baselineSessionId={baselineSessionId}
          challengerSessionId={challengerSessionId}
          challengerStatus={challengerStatus}
        />
      </SectionGroup>
      {/* 3. 디스패처 상태 — 읽기 전용(실행 컨트롤 없음) */}
      <SectionGroup
        title="디스패처 상태(읽기 전용)"
        helper="상태만 보여줍니다. 이 화면에서는 디스패처를 실행하지 않습니다."
      >
        <RecurringDispatcherStatusPanel />
      </SectionGroup>
      {/* 4. 고급/디버그 — 단일 세션 1회 기록(기본 접힘) */}
      <SectionGroup title="고급/디버그" helper="일반 비교 흐름에서는 보통 사용하지 않습니다.">
        <details style={{ marginTop: 4 }}>
          <summary className="muted" style={{ fontSize: "0.78em", cursor: "pointer" }}>
            단일 세션만 기록
          </summary>
          <SessionRunOnce sessionId={challengerSessionId} challengerStatus={challengerStatus} />
        </details>
      </SectionGroup>
      {pairRan && !result && (
        <div style={{ fontSize: "0.8em", fontWeight: 600, color: "#2563eb", marginTop: 4 }}>
          이제 ‘신호 성과 비교 보기’를 다시 눌러 결과를 확인하세요.
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
          {bothZero && (
            <div className="muted" style={{ fontSize: "0.8em", color: "#b45309" }}>
              아직 비교할 신호가 없습니다. 페어 신호 1회 기록 후 다시 비교하세요.
            </div>
          )}
          {oneZero && (
            <div className="muted" style={{ fontSize: "0.8em", color: "#b45309" }}>
              한쪽 세션에만 신호가 있어 비교가 편향될 수 있습니다. 페어 신호 기록을 권장합니다.
            </div>
          )}
          {result.warnings.map((w) => (
            <div key={w} className="muted" style={{ fontSize: "0.8em", color: "#b45309" }}>
              ℹ 통계 주의: {w}
            </div>
          ))}
          {/* M2.14G — 대략적인 참고용 표본 힌트(paired = 두 세션 중 작은 신호 수). 통계 계산 아님. */}
          {!bothZero &&
            (() => {
              const paired = Math.min(bSig, cSig);
              const h = sampleSizeHint(paired);
              return (
                <div className="muted" style={{ fontSize: "0.78em", marginTop: 2 }}>
                  대략적인 참고용 표본 힌트:{" "}
                  <b style={{ color: h.color }}>{h.label}</b> (paired≈{paired}) — 표본이 적을수록
                  승률/성과 해석은 불안정합니다.
                </div>
              );
            })()}
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
