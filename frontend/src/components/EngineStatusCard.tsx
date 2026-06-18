import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { getEngineStatus } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";
import type { Translations } from "../i18n/translations";

function describeCategory(category: string | null, t: Translations): { title: string; description: string } {
  if (!category) return t.scheduler.errorCategoryLabels.unknown;
  return t.scheduler.errorCategoryLabels[category] ?? { title: category, description: "" };
}

function ErrorValue({ error, category, t }: { error: string | null; category: string | null; t: Translations }) {
  if (!error) return <span className="value ok">-</span>;
  const { title, description } = describeCategory(category, t);
  return (
    <div>
      <span className="value error">{title}</span>
      <details>
        <summary>{t.scheduler.showDetails}</summary>
        {description && <div className="muted">{description}</div>}
        <div className="muted scheduler-error-raw">{error}</div>
      </details>
    </div>
  );
}

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

  const warnings: ReactNode[] = [];
  const strongWarnings: ReactNode[] = [];
  if (data.last_error) {
    warnings.push(
      `${t.engineStatus.schedulerErrorPrefix}: ${describeCategory(data.last_error_category, t).title}`,
    );
  }
  if (data.order_sync_last_error) {
    warnings.push(
      `${t.engineStatus.orderSyncErrorPrefix}: ${describeCategory(data.order_sync_last_error_category, t).title}`,
    );
  }
  if (data.recent_run_has_failure) warnings.push(t.engineStatus.recentFailureWarning);
  if (data.active_strategy_count >= 2) {
    warnings.push(t.engineStatus.multipleActiveWarning(data.active_strategy_count));
  }
  if (data.active_strategy_count >= 5) {
    warnings.push(t.engineStatus.manyActiveStrategiesWarning(data.active_strategy_count));
  }
  if (data.auto_trade_enabled_count >= 2) {
    strongWarnings.push(t.engineStatus.autoTradeStrongWarning(data.auto_trade_enabled_count));
  } else if (data.auto_trade_enabled_count > 0) {
    warnings.push(t.engineStatus.autoTradeWarning(data.auto_trade_enabled_count));
  }

  return (
    <div className="card">
      <h2>{t.engineStatus.title}</h2>
      {strongWarnings.length > 0 && (
        <div className="card warning-banner warning-banner-strong">
          <strong>{t.engineStatus.warningTitle}</strong>
          <ul>
            {strongWarnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
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
          <span className="value">
            {data.registered_jobs.length > 0
              ? data.registered_jobs.map((id) => t.scheduler.jobLabels[id] ?? id).join(", ")
              : "-"}
          </span>
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
          <ErrorValue error={data.last_error} category={data.last_error_category} t={t} />
        </div>
        <div className="status-item">
          <span className="label">{t.engineStatus.orderSyncLastRunAt}</span>
          <span className="value">{formatDateTime(data.order_sync_last_run_at)}</span>
        </div>
        <div className="status-item">
          <span className="label">{t.engineStatus.orderSyncLastError}</span>
          <ErrorValue error={data.order_sync_last_error} category={data.order_sync_last_error_category} t={t} />
        </div>
      </div>
    </div>
  );
}
