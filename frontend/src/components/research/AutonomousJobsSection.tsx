import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getAutonomousJobs, runAutonomousJob, toggleAutonomousJob } from "../../api/client";
import { useSettings } from "../../i18n/SettingsContext";

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
                    {job.label}
                    <div className="muted" style={{ fontSize: "0.85em" }}>{job.job_id}</div>
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
