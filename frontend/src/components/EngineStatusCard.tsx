import { useQuery } from "@tanstack/react-query";
import { getEngineStatus } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";

export default function EngineStatusCard() {
  const { t, formatDateTime } = useSettings();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["engine-status"],
    queryFn: getEngineStatus,
  });

  if (isLoading) {
    return (
      <div className="card">
        <h2>{t.engineStatus.title}</h2>
        <p className="muted">{t.common.loading}</p>
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className="card">
        <h2>{t.engineStatus.title}</h2>
        <p className="value error">{(error as Error)?.message ?? t.common.loadError}</p>
      </div>
    );
  }

  const warnings: string[] = [];
  if (data.last_error) warnings.push(`${t.engineStatus.schedulerErrorPrefix}: ${data.last_error}`);
  if (data.order_sync_last_error) {
    warnings.push(`${t.engineStatus.orderSyncErrorPrefix}: ${data.order_sync_last_error}`);
  }
  if (data.recent_run_has_failure) warnings.push(t.engineStatus.recentFailureWarning);
  if (data.active_strategy_count >= 2) {
    warnings.push(t.engineStatus.multipleActiveWarning(data.active_strategy_count));
  }
  if (data.auto_trade_enabled_count > 0) {
    warnings.push(t.engineStatus.autoTradeWarning(data.auto_trade_enabled_count));
  }

  return (
    <div className="card">
      <h2>{t.engineStatus.title}</h2>
      {warnings.length > 0 && (
        <div className="card warning-banner">
          <strong>{t.engineStatus.warningTitle}</strong>
          <ul>
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="status-grid">
        <div className="status-item">
          <span className="label">{t.engineStatus.schedulerRunning}</span>
          <span className={`value ${data.scheduler_running ? "ok" : "error"}`}>
            {data.scheduler_running ? t.engineStatus.running : t.engineStatus.stopped}
          </span>
        </div>
        <div className="status-item">
          <span className="label">{t.engineStatus.registeredJobs}</span>
          <span className="value">{data.registered_jobs.join(", ") || "-"}</span>
        </div>
        <div className="status-item">
          <span className="label">{t.engineStatus.activeStrategies}</span>
          <span className={`value ${data.active_strategy_count >= 2 ? "error" : ""}`}>
            {data.active_strategy_count}
          </span>
        </div>
        <div className="status-item">
          <span className="label">{t.engineStatus.autoTradeEnabled}</span>
          <span className={`value ${data.auto_trade_enabled_count > 0 ? "error" : "ok"}`}>
            {data.auto_trade_enabled_count}
          </span>
        </div>
        <div className="status-item">
          <span className="label">{t.engineStatus.lastRunAt}</span>
          <span className="value">{formatDateTime(data.last_run_at)}</span>
        </div>
        <div className="status-item">
          <span className="label">{t.engineStatus.lastError}</span>
          <span className={`value ${data.last_error ? "error" : "ok"}`}>{data.last_error ?? "-"}</span>
        </div>
        <div className="status-item">
          <span className="label">{t.engineStatus.orderSyncLastRunAt}</span>
          <span className="value">{formatDateTime(data.order_sync_last_run_at)}</span>
        </div>
        <div className="status-item">
          <span className="label">{t.engineStatus.orderSyncLastError}</span>
          <span className={`value ${data.order_sync_last_error ? "error" : "ok"}`}>
            {data.order_sync_last_error ?? "-"}
          </span>
        </div>
      </div>
    </div>
  );
}
