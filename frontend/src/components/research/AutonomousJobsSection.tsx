import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AutonomousJob,
  getAutonomousJobs,
  runAutonomousJob,
  toggleAutonomousJob,
} from "../../api/client";
import { useSettings } from "../../i18n/SettingsContext";

// C-3.1: 위험도/추천 상태/특성 라벨 (정적 상수, 표시 전용).
const RISK_LABEL: Record<AutonomousJob["risk_level"], string> = {
  SAFE_ON: "상시 ON 가능",
  MANUAL_FIRST: "수동 실행 먼저 권장",
  KEEP_OFF: "기본 OFF 유지 권장",
  DO_NOT_ENABLE: "활성화 금지",
};

const RECOMMENDED_LABEL: Record<AutonomousJob["recommended_state"], string> = {
  ON_OK: "추천: ON 가능",
  MANUAL_FIRST: "추천: 수동 우선",
  KEEP_OFF: "추천: OFF 유지",
};

function CapabilityBadges({ job }: { job: AutonomousJob }) {
  return (
    <div className="badge-row">
      {job.writes_db && <span className="cap-badge">DB 기록 있음</span>}
      {(job.uses_llm || job.cost_risk) && (
        <span className="cap-badge cap-warn">LLM/비용 가능성</span>
      )}
      {job.external_network && <span className="cap-badge">외부 API 호출</span>}
      {job.creates_proposals && (
        <span className="cap-badge cap-warn">제안 생성 가능</span>
      )}
      {job.paper_action && <span className="cap-badge">Paper 상태 변경 가능</span>}
      {job.data_volume_risk && <span className="cap-badge">레코드 다량 생성</span>}
      {/* 안전 고지: 어떤 잡도 실전 거래에 영향 없음 */}
      <span className="cap-badge cap-safe">실전 주문 영향 없음</span>
    </div>
  );
}

export default function AutonomousJobsSection() {
  const { t, formatDateTime } = useSettings();
  const j = t.autonomousJobs;
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["autonomous-jobs"],
    queryFn: getAutonomousJobs,
    refetchInterval: 20000,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["autonomous-jobs"] });

  const toggle = useMutation({
    mutationFn: ({ jobId, enabled }: { jobId: string; enabled: boolean }) =>
      toggleAutonomousJob(jobId, enabled),
    onSuccess: invalidate,
  });
  const run = useMutation({
    mutationFn: (jobId: string) => runAutonomousJob(jobId),
    onSuccess: invalidate,
  });

  return (
    <div className="card">
      <h2>{j.title}</h2>
      <p className="section-description">{j.description}</p>
      {isLoading && <p className="muted">{t.common.loading}</p>}
      {isError && <p className="value error">{t.common.loadError}</p>}
      {data && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{j.colJob}</th>
                <th>{j.colSchedule}</th>
                <th>{j.colStatus}</th>
                <th>{j.colActions}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((job) => (
                <tr key={job.job_id}>
                  <td>
                    <strong>{job.label}</strong>
                    <div className="muted" style={{ fontSize: "0.85em" }}>{job.job_id}</div>
                    {job.description && (
                      <div style={{ fontSize: "0.88em", margin: "4px 0" }}>{job.description}</div>
                    )}
                    <div className="badge-row">
                      <span className={`risk-badge risk-${job.risk_level}`}>
                        {RISK_LABEL[job.risk_level]}
                      </span>
                      <span className="risk-badge risk-rec">
                        {RECOMMENDED_LABEL[job.recommended_state]}
                      </span>
                    </div>
                    <CapabilityBadges job={job} />
                    {job.safety_notes.length > 0 && (
                      <ul className="job-safety-notes">
                        {job.safety_notes.map((n) => (
                          <li key={n}>{n}</li>
                        ))}
                      </ul>
                    )}
                  </td>
                  <td className="muted">{job.schedule}</td>
                  <td>
                    <span className={`value ${job.enabled ? "ok" : ""}`}>
                      {job.enabled ? j.on : j.off}
                    </span>
                    {job.enabled && job.running && (
                      <span className="muted"> · {j.runningNow}</span>
                    )}
                    {job.last_run_at && (
                      <div className="muted" style={{ fontSize: "0.85em" }}>
                        {j.lastRun}: {formatDateTime(job.last_run_at)}
                      </div>
                    )}
                    {job.last_error && (
                      <div className="value error" style={{ fontSize: "0.85em" }}>{job.last_error}</div>
                    )}
                  </td>
                  <td>
                    <button
                      onClick={() => toggle.mutate({ jobId: job.job_id, enabled: !job.enabled })}
                      disabled={toggle.isPending}
                    >
                      {job.enabled ? j.turnOff : j.turnOn}
                    </button>{" "}
                    <button onClick={() => run.mutate(job.job_id)} disabled={run.isPending}>
                      {j.runNow}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {run.isSuccess && <p className="muted">{j.runTriggered}</p>}
    </div>
  );
}
