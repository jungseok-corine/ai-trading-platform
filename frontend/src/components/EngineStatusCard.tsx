import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { getEngineStatus } from "../api/client";
import { getSafetyStatus } from "../api/research";
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
  // 실거래 활성 여부는 engine status API에 없으므로 safety-status에서 읽는다(read-only).
  // 알 수 없으면(로딩/실패) 보수적으로 '실거래 ON'으로 간주해 강한 경고를 유지한다(과소경고 방지).
  const { data: safety } = useQuery({
    queryKey: ["safety-status"],
    queryFn: getSafetyStatus,
  });
  const realTradingOn = safety?.real_trading_enabled ?? true;

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
  if (data.auto_trade_enabled_count > 0) {
    if (realTradingOn) {
      // 실거래 ON(또는 상태 미확인) → 강한 빨간 경고 유지.
      strongWarnings.push(t.engineStatus.autoTradeStrongWarning(data.auto_trade_enabled_count));
    } else {
      // 실거래 OFF → paper/test 기록 수집용. 강한 경고 대신 운영 안내로 표시.
      warnings.push(t.engineStatus.autoTradePaperNotice(data.auto_trade_enabled_count));
    }
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
        <div className="status-item status-item-jobs">
          <span className="label">
            {t.engineStatus.registeredJobs} ({data.registered_jobs.length})
          </span>
          {data.registered_jobs.length > 0 ? (
            <div className="engine-job-chips">
              {data.registered_jobs.map((id) => (
                <span key={id} className="engine-job-chip" title={id}>
                  {t.scheduler.jobLabels[id] ?? id}
                </span>
              ))}
            </div>
          ) : (
            <span className="value">-</span>
          )}
        </div>
        <div className="status-item">
          <span className="label">{t.engineStatus.activeStrategies}</span>
          <span className={`value ${data.active_strategy_count >= 2 ? "error" : ""}`}>
            {data.active_strategy_count}
          </span>
        </div>
        <div className="status-item">
          <span className="label">{t.engineStatus.autoTradeEnabled}</span>
          <span
            className={`value ${
              data.auto_trade_enabled_count === 0
                ? "ok"
                : realTradingOn
                  ? "error"
                  : ""
            }`}
          >
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
