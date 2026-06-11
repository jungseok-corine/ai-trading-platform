import { useQuery } from "@tanstack/react-query";
import { getEngineStatus } from "../api/client";

export default function EngineStatusCard() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["engine-status"],
    queryFn: getEngineStatus,
  });

  if (isLoading) return <div className="card"><h2>Engine Status</h2><p className="muted">불러오는 중...</p></div>;
  if (isError || !data) {
    return (
      <div className="card">
        <h2>Engine Status</h2>
        <p className="value error">{(error as Error)?.message ?? "조회 실패"}</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h2>Engine Status</h2>
      <div className="status-grid">
        <div className="status-item">
          <span className="label">Scheduler Running</span>
          <span className={`value ${data.scheduler_running ? "ok" : "error"}`}>
            {data.scheduler_running ? "Running" : "Stopped"}
          </span>
        </div>
        <div className="status-item">
          <span className="label">Registered Jobs</span>
          <span className="value">{data.registered_jobs.join(", ") || "-"}</span>
        </div>
        <div className="status-item">
          <span className="label">Active Strategies</span>
          <span className="value">{data.active_strategy_count}</span>
        </div>
        <div className="status-item">
          <span className="label">Last Run At</span>
          <span className="value">{data.last_run_at ?? "-"}</span>
        </div>
        <div className="status-item">
          <span className="label">Last Error</span>
          <span className={`value ${data.last_error ? "error" : "ok"}`}>{data.last_error ?? "-"}</span>
        </div>
        <div className="status-item">
          <span className="label">Order Sync Last Run At</span>
          <span className="value">{data.order_sync_last_run_at ?? "-"}</span>
        </div>
        <div className="status-item">
          <span className="label">Order Sync Last Error</span>
          <span className={`value ${data.order_sync_last_error ? "error" : "ok"}`}>
            {data.order_sync_last_error ?? "-"}
          </span>
        </div>
      </div>
    </div>
  );
}
