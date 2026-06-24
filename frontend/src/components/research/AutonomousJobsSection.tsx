import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AutonomousJob,
  getAutonomousJobs,
  runAutonomousJob,
  toggleAutonomousJob,
} from "../../api/client";
import { useSettings } from "../../i18n/SettingsContext";
import JobEnableConfirm from "./JobEnableConfirm";
import { CapabilityBadges, RECOMMENDED_LABEL, RISK_LABEL } from "./jobRiskLabels";

export default function AutonomousJobsSection() {
  const { t, formatDateTime } = useSettings();
  const j = t.autonomousJobs;
  const qc = useQueryClient();
  // C-OPS-3.2: ON 확인 게이트 대상 잡 (recommended_state !== "ON_OK"일 때만 채워짐).
  const [pendingEnableJob, setPendingEnableJob] = useState<AutonomousJob | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["autonomous-jobs"],
    queryFn: getAutonomousJobs,
    refetchInterval: 20000,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["autonomous-jobs"] });

  const toggle = useMutation({
    mutationFn: ({ jobId, enabled }: { jobId: string; enabled: boolean }) =>
      toggleAutonomousJob(jobId, enabled),
    onSuccess: () => {
      setPendingEnableJob(null);
      invalidate();
    },
    onError: () => setPendingEnableJob(null),
  });
  const run = useMutation({
    mutationFn: (jobId: string) => runAutonomousJob(jobId),
    onSuccess: invalidate,
  });

  // ON/OFF 클릭 처리: OFF는 즉시, ON은 SAFE_ON(ON_OK)만 즉시 — 그 외엔 확인 게이트.
  const handleToggleClick = (job: AutonomousJob) => {
    if (job.enabled) {
      toggle.mutate({ jobId: job.job_id, enabled: false });
      return;
    }
    if (job.recommended_state === "ON_OK") {
      toggle.mutate({ jobId: job.job_id, enabled: true });
    } else {
      setPendingEnableJob(job);
    }
  };

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
                      onClick={() => handleToggleClick(job)}
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

      {pendingEnableJob && (
        <JobEnableConfirm
          key={pendingEnableJob.job_id}
          job={pendingEnableJob}
          isPending={toggle.isPending}
          onConfirm={() => toggle.mutate({ jobId: pendingEnableJob.job_id, enabled: true })}
          onCancel={() => setPendingEnableJob(null)}
        />
      )}
    </div>
  );
}
