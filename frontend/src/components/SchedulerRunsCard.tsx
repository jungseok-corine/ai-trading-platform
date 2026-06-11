import { useQuery } from "@tanstack/react-query";
import { getSchedulerRuns } from "../api/client";

export default function SchedulerRunsCard() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["scheduler-runs"],
    queryFn: () => getSchedulerRuns(20),
  });

  return (
    <div className="card">
      <h2>Scheduler Logs</h2>
      {isLoading && <p className="muted">불러오는 중...</p>}
      {isError && <p className="value error">{(error as Error)?.message ?? "조회 실패"}</p>}
      {data && data.length === 0 && <p className="muted">실행 기록이 없습니다.</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Job</th>
                <th>Status</th>
                <th>Started At</th>
                <th>Duration (ms)</th>
                <th>Error</th>
                <th>Summary</th>
              </tr>
            </thead>
            <tbody>
              {data.map((run) => (
                <tr key={run.id}>
                  <td>{run.job_id}</td>
                  <td>
                    <span className={`value ${run.status === "failed" ? "error" : "ok"}`}>{run.status}</span>
                  </td>
                  <td>{run.started_at}</td>
                  <td>{run.duration_ms ?? "-"}</td>
                  <td>{run.error_message ?? "-"}</td>
                  <td>
                    <pre className="parameters-cell">{run.summary ? JSON.stringify(run.summary) : "-"}</pre>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
