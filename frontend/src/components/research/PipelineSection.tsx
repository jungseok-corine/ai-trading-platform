import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getPipelineRuns, getResearchStatus, runPipeline } from "../../api/research";
import type { PipelineSummary } from "../../types/research";

const JOB_LABELS: Record<string, string> = {
  research_pipeline: "스캔·후보·배정",
  scanner_review: "스캐너 점검",
  strategy_review: "전략 점검",
  daily_report: "일일 리포트",
};

function ControlTower() {
  const { data } = useQuery({ queryKey: ["research-status"], queryFn: getResearchStatus });
  if (!data) return null;
  return (
    <div className="card" style={{ background: "#f8f9fa" }}>
      <strong>자율 운영 현황 (관제탑)</strong>
      <p className="muted">
        검토 대기 제안 {data.pending.total}건 (전략 {data.pending.strategy} / 스캐너 {data.pending.scanner}) ·
        활성 스캐너 버전 {data.active.scanner_versions}개 · 활성 전략 버전 {data.active.strategy_versions}개
      </p>
      <p className="muted">
        제안 회고 {data.retrospective.total}건 — 개선 {data.retrospective.improved} ·
        악화 {data.retrospective.worse} · 판단보류 {data.retrospective.inconclusive}
      </p>
      <p className="muted">
        매크로 레짐: <strong>{data.macro.regime}</strong>
        {data.macro.session_date ? ` (전일 ${data.macro.session_date})` : ""}
        {data.macro.vix != null ? ` · VIX ${data.macro.vix} (${data.macro.vix_level})` : ""}
        {data.macro.us_trend ? ` · 미국장 ${data.macro.us_trend}` : ""}
        {data.macro.semis_strength ? ` · 반도체 ${data.macro.semis_strength}` : ""}
      </p>
      <div className="table-wrapper">
        <table>
          <thead><tr><th>잡</th><th>최근 실행</th><th>상태</th><th>소요(ms)</th></tr></thead>
          <tbody>
            {data.jobs.map((j) => (
              <tr key={j.job_id}>
                <td>{JOB_LABELS[j.job_id] ?? j.job_id}</td>
                <td>{j.last_run_at ? new Date(j.last_run_at).toLocaleString() : "—"}</td>
                <td>{j.status ?? "미실행"}</td>
                <td>{j.duration_ms ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function PipelineSection() {
  const queryClient = useQueryClient();

  const { data: runs, isLoading } = useQuery({
    queryKey: ["pipeline-runs"],
    queryFn: () => getPipelineRuns(20),
  });

  const runMut = useMutation({
    mutationFn: () => runPipeline({ auto_assign: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pipeline-runs"] }),
  });

  const last = runMut.data as PipelineSummary | undefined;

  return (
    <div className="card">
      <h3>자율 파이프라인</h3>
      <p className="muted">
        스캔 → 후보 발견 → 전략 배정을 한 번에 실행합니다. (watchlist 종목 대상, 주문은 발생하지 않음)
      </p>

      <ControlTower />

      <div className="form-row">
        <button className="primary" disabled={runMut.isPending} onClick={() => runMut.mutate()}>
          {runMut.isPending ? "실행 중..." : "지금 실행"}
        </button>
        {runMut.isError && <span className="value error">실행 실패</span>}
      </div>

      {last && (
        <p className="action-result value">
          버전 {last.versions}개 · 종목 {last.symbols}개 스캔 → 후보 {last.candidates}건 · 배정 {last.assignments}건
        </p>
      )}

      <h4>실행 이력</h4>
      {isLoading && <p className="muted">불러오는 중...</p>}
      {runs && runs.length === 0 && <p className="muted">아직 실행 이력이 없습니다.</p>}
      {runs && runs.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr><th>시각</th><th>상태</th><th>버전</th><th>종목</th><th>후보</th><th>배정</th><th>소요(ms)</th></tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>{new Date(r.started_at).toLocaleString()}</td>
                  <td><span className={r.status === "success" ? "param-chip-val ok" : "param-chip-val danger"}>{r.status}</span></td>
                  <td>{r.summary?.versions ?? "-"}</td>
                  <td>{r.summary?.symbols ?? "-"}</td>
                  <td>{r.summary?.candidates ?? "-"}</td>
                  <td>{r.summary?.assignments ?? "-"}</td>
                  <td>{r.duration_ms ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
