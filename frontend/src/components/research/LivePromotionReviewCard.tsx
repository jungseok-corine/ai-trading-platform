// C-2.30: 실전 승격 '검토 승인' 카드 (C-2.29 live-readiness / live-promote).
//
// ⚠️ 이 카드는 실거래를 시작하지 않는다. '사람이 검토를 승인했다'는 감사 기록만 남긴다.
// 실계좌 선택 / 자동매매 토글 / ACTIVE 전환 / 실주문 UI는 의도적으로 존재하지 않는다.
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { approveLivePromotion, getLiveReadiness } from "../../api/research";
import type { LivePromoteResponse } from "../../types/research";
import { RawJsonDetails, WillNotHappenBlock } from "./approvalBlocks";
import { LIVE_PROMOTION_BANNER, LIVE_PROMOTION_WILL_NOT_HAPPEN } from "./safetyCopy";

interface Props {
  strategyVersionId: number;
  criteriaId?: number;
  approvedBy?: string;
}

export default function LivePromotionReviewCard({
  strategyVersionId,
  criteriaId,
  approvedBy = "user",
}: Props) {
  const [confirmed, setConfirmed] = useState(false);
  const [note, setNote] = useState("");
  const [result, setResult] = useState<LivePromoteResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const readinessQ = useQuery({
    queryKey: ["live-readiness", strategyVersionId, criteriaId ?? null],
    queryFn: () => getLiveReadiness(strategyVersionId, criteriaId),
  });
  const readiness = readinessQ.data;
  const readinessPassed = !!readiness && readiness.passed;

  const approveMut = useMutation({
    mutationFn: () =>
      approveLivePromotion(
        strategyVersionId,
        { confirmed: true, confirmed_by: approvedBy, note: note || null },
        criteriaId,
      ),
    onSuccess: (r) => {
      setResult(r);
      setError(null);
    },
    onError: (e) => setError((e as Error)?.message ?? "승격 검토 승인 실패"),
  });

  // 승인 가능: readiness 통과 + 확인 체크 + 미진행 + 아직 승인 안 함.
  const canApprove =
    readinessPassed && confirmed && !approveMut.isPending && result === null;

  return (
    <div className="card approval-report-card">
      <h4>실전 승격 검토 — 전략 버전 #{strategyVersionId}</h4>

      {/* 가장 눈에 띄는 안전 배너 */}
      <div className="live-banner">⚠️ {LIVE_PROMOTION_BANNER}</div>

      {readinessQ.isLoading && <p className="muted">준비도 평가 불러오는 중…</p>}
      {readinessQ.isError && (
        <p className="value error">준비도 평가를 불러오지 못했습니다 (version/criteria 확인).</p>
      )}

      {readiness && (
        <>
          <p className="action-result value">
            판정: {readiness.passed ? "✅ 통과" : "❌ 미달"} · 거래 {readiness.trades_count}건 ·{" "}
            {readiness.days}일 · 기댓값 {readiness.expectancy.toLocaleString()} · MDD{" "}
            {readiness.max_drawdown.toLocaleString()}
          </p>

          <div className="approval-block">
            <strong>준비도 체크</strong>
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>항목</th>
                    <th>실제</th>
                    <th>기준</th>
                    <th>통과</th>
                  </tr>
                </thead>
                <tbody>
                  {readiness.checks.map((c) => (
                    <tr key={c.name}>
                      <td>{c.name}</td>
                      <td>{c.actual}</td>
                      <td>{c.threshold}</td>
                      <td>{c.passed ? "✓" : "✗"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {readiness.intel_context && (
            <RawJsonDetails label="intel_context" data={readiness.intel_context} />
          )}
        </>
      )}

      <WillNotHappenBlock items={LIVE_PROMOTION_WILL_NOT_HAPPEN} />

      {/* 승인 결과 표시 (백엔드 message 그대로 노출) */}
      {result && (
        <div className="approval-block safe">
          <strong>검토 승인 기록 생성됨 (#{result.record.id})</strong>
          <p className="value">{result.message}</p>
          <p className="muted">
            상태: {result.record.status} · 승인자: {result.record.approved_by}
          </p>
        </div>
      )}
      {error && <p className="value error">{error}</p>}

      {/* 승인 UX: 확인 체크 필수. readiness 미달이면 비활성화. */}
      {result === null && (
        <div className="approval-actions">
          <input
            className="full-width"
            placeholder="검토 메모 (선택)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <label className="confirm-check">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            이것이 실거래 시작이 아니라 '검토 승인 기록'임을 이해했습니다.
          </label>
          <button className="primary" disabled={!canApprove} onClick={() => approveMut.mutate()}>
            실전 승격 검토 승인
          </button>
          {!readinessPassed && !readinessQ.isLoading && (
            <p className="muted">준비도 기준 미달 — 승인이 비활성화됩니다.</p>
          )}
        </div>
      )}
    </div>
  );
}
