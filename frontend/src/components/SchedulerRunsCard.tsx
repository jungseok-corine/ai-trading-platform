import { useQuery } from "@tanstack/react-query";
import { getSchedulerRuns } from "../api/client";
import type { OrderSyncExecutionSummary, SchedulerRunErrorEntry, SchedulerRunSummary } from "../types";
import { useSettings } from "../i18n/SettingsContext";
import type { Translations } from "../i18n/translations";
import { formatPrice, formatQuantity } from "../utils/format";

function describeCategory(category: string | null, t: Translations): { title: string; description: string } | null {
  if (!category) return null;
  return t.scheduler.errorCategoryLabels[category] ?? { title: category, description: "" };
}

function describeJob(jobId: string, t: Translations): string {
  return t.scheduler.jobLabels[jobId] ?? jobId;
}

function describeSummaryKey(key: string, t: Translations): string {
  return t.scheduler.summaryKeyLabels[key] ?? key;
}

function formatSummaryValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.length === 0 ? "-" : value.join(", ");
  }
  return String(value);
}

const HIDDEN_SUMMARY_KEYS = new Set(["errors", "error_category", "skipped_reason", "executions", "error_categories"]);

function ExecutionsList({ executions, t }: { executions: OrderSyncExecutionSummary[]; t: Translations }) {
  if (executions.length === 0) return null;
  return (
    <details>
      <summary>{t.scheduler.executionsTitle}</summary>
      <table className="executions-table">
        <thead>
          <tr>
            <th>{t.scheduler.executionOrderId}</th>
            <th>{t.scheduler.executionFilledQuantity}</th>
            <th>{t.scheduler.executionFilledPrice}</th>
          </tr>
        </thead>
        <tbody>
          {executions.map((e, i) => (
            <tr key={i}>
              <td>{e.order_id}</td>
              <td>{formatQuantity(e.filled_quantity)}</td>
              <td>{formatPrice(e.filled_price)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function SummaryCounts({ summary, t }: { summary: SchedulerRunSummary; t: Translations }) {
  const counts = Object.entries(summary).filter(
    ([key, value]) => !HIDDEN_SUMMARY_KEYS.has(key) && value !== null && value !== undefined,
  );
  const skippedLabel = summary.skipped_reason
    ? t.scheduler.skippedReasonLabels[summary.skipped_reason] ?? summary.skipped_reason
    : null;
  if (counts.length === 0 && !skippedLabel) return null;
  return (
    <div className="muted">
      {skippedLabel && <div>{skippedLabel}</div>}
      {counts.length > 0 &&
        counts.map(([key, value]) => `${describeSummaryKey(key, t)}: ${formatSummaryValue(value)}`).join(", ")}
    </div>
  );
}

function ErrorList({ errors, t }: { errors: SchedulerRunErrorEntry[]; t: Translations }) {
  if (errors.length === 0) return null;
  // 종목마다 한 줄씩 나열하면 감시 종목이 많을 때 너무 길어진다.
  // 같은 오류(카테고리/메시지)끼리 묶어 "오류명 (N) + 상세 접기"로 압축한다.
  const groups = new Map<string, SchedulerRunErrorEntry[]>();
  for (const err of errors) {
    const key = err.category ?? err.message ?? "unknown";
    const arr = groups.get(key);
    if (arr) arr.push(err);
    else groups.set(key, [err]);
  }
  return (
    <ul className="scheduler-error-list">
      {Array.from(groups.entries()).map(([key, errs]) => {
        const category = describeCategory(errs[0].category, t);
        const title = category ? category.title : errs[0].message || "-";
        const symbols = errs.map((e) => e.symbol_code).filter(Boolean) as string[];
        const rawMessage = errs[0].message;
        return (
          <li key={key}>
            <span className="value error">{title}</span>
            {errs.length > 1 && <span className="muted"> ({errs.length})</span>}
            <details>
              <summary>{t.scheduler.showDetails}</summary>
              {category?.description && <div className="muted">{category.description}</div>}
              {rawMessage && <div className="muted scheduler-error-raw">{rawMessage}</div>}
              {symbols.length > 0 && (
                <div className="muted scheduler-error-raw">{symbols.join(", ")}</div>
              )}
            </details>
          </li>
        );
      })}
    </ul>
  );
}

export default function SchedulerRunsCard() {
  const { t, formatDateTime } = useSettings();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["scheduler-runs"],
    queryFn: () => getSchedulerRuns(20),
    // 새 실행 로그가 생기면 수동 새로고침 없이 주기적으로 갱신한다(탭이 보일 때만).
    refetchInterval: 20000,
  });

  const statusLabel = (status: string) =>
    (t.schedulerStatus as Record<string, string>)[status] ?? status;

  return (
    <div className="card">
      <h2>{t.scheduler.title}</h2>
      <p className="section-description">{t.scheduler.description}</p>
      {isLoading && <p className="muted">{t.scheduler.loading}</p>}
      {isError && <p className="value error">{(error as Error)?.message ?? t.common.loadError}</p>}
      {data && data.length === 0 && <p className="muted">{t.scheduler.empty}</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t.scheduler.colJob}</th>
                <th>{t.scheduler.colStatus}</th>
                <th>{t.scheduler.colStartedAt}</th>
                <th>{t.scheduler.colDuration}</th>
                <th>{t.scheduler.colErrors}</th>
                <th>{t.scheduler.colSummary}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((run) => (
                <tr key={run.id}>
                  <td>{describeJob(run.job_id, t)}</td>
                  <td>
                    <span className={`value ${run.status === "failed" ? "error" : "ok"}`}>
                      {statusLabel(run.status)}
                    </span>
                  </td>
                  <td>{formatDateTime(run.started_at)}</td>
                  <td>{run.duration_ms ?? "-"}</td>
                  <td>
                    {run.summary?.errors && run.summary.errors.length > 0 ? (
                      <ErrorList errors={run.summary.errors} t={t} />
                    ) : (
                      "-"
                    )}
                  </td>
                  <td>
                    {run.summary ? <SummaryCounts summary={run.summary} t={t} /> : "-"}
                    {run.summary?.unmatched_order_ids && run.summary.unmatched_order_ids.length > 0 && (
                      <ExecutionsList executions={run.summary.executions ?? []} t={t} />
                    )}
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
