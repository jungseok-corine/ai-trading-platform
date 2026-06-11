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

  const warnings: string[] = [];
  if (data.last_error) warnings.push(`Scheduler 오류: ${data.last_error}`);
  if (data.order_sync_last_error) warnings.push(`Order Sync 오류: ${data.order_sync_last_error}`);
  if (data.recent_run_has_failure) warnings.push("최근 scheduler 실행 기록 중 실패한 작업이 있습니다.");
  if (data.active_strategy_count >= 2) {
    warnings.push(`활성 전략이 ${data.active_strategy_count}개 동시에 실행 중입니다.`);
  }
  if (data.auto_trade_enabled_count > 0) {
    warnings.push(`자동매매(auto_trade_enabled)가 활성화된 전략이 ${data.auto_trade_enabled_count}개 있습니다.`);
  }

  return (
    <div className="card">
      <h2>Engine Status</h2>
      {warnings.length > 0 && (
        <div className="card warning-banner">
          <strong>운영 경고</strong>
          <ul>
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
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
          <span className={`value ${data.active_strategy_count >= 2 ? "error" : ""}`}>
            {data.active_strategy_count}
          </span>
        </div>
        <div className="status-item">
          <span className="label">Auto Trade Enabled</span>
          <span className={`value ${data.auto_trade_enabled_count > 0 ? "error" : "ok"}`}>
            {data.auto_trade_enabled_count}
          </span>
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
