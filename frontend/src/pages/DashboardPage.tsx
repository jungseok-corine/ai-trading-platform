import { useMutation, useQueryClient } from "@tanstack/react-query";
import { runOnce, syncOrders } from "../api/client";
import EngineStatusCard from "../components/EngineStatusCard";
import SchedulerSettingsCard from "../components/SchedulerSettingsCard";
import SchedulerRunsCard from "../components/SchedulerRunsCard";
import PortfolioSummaryCard from "../components/PortfolioSummaryCard";
import PositionsTable from "../components/PositionsTable";
import TradesTable from "../components/TradesTable";
import SignalsTable from "../components/SignalsTable";
import RiskControls from "../components/RiskControls";
import RunOnceResultsTable from "../components/RunOnceResultsTable";
import { useSettings } from "../i18n/SettingsContext";
import type { Translations } from "../i18n/translations";
import type { OrderSyncResult } from "../types";
import { formatPrice, formatQuantity } from "../utils/format";

function UnmatchedExecutions({ result, t }: { result: OrderSyncResult; t: Translations }) {
  if (result.unmatched_order_ids.length === 0 || result.executions.length === 0) return null;
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
          {result.executions.map((e, i) => (
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

function SyncOrdersResult({ result }: { result: OrderSyncResult }) {
  const { t } = useSettings();
  const entries: [string, string][] = [
    [t.scheduler.summaryKeyLabels.checked, String(result.checked)],
    [t.scheduler.summaryKeyLabels.updated, String(result.updated)],
    [t.scheduler.summaryKeyLabels.matched, String(result.matched)],
    [t.scheduler.summaryKeyLabels.unmatched, String(result.unmatched)],
  ];
  if (result.unmatched_order_ids.length > 0) {
    entries.push([t.scheduler.summaryKeyLabels.unmatched_order_ids, result.unmatched_order_ids.join(", ")]);
  }

  const skippedLabel = result.skipped_reason
    ? t.scheduler.skippedReasonLabels[result.skipped_reason] ?? result.skipped_reason
    : null;
  const category = result.error_category ? t.scheduler.errorCategoryLabels[result.error_category] : null;

  return (
    <div className="action-result">
      {skippedLabel && <div className="muted">{skippedLabel}</div>}
      <div className="muted">{entries.map(([label, value]) => `${label}: ${value}`).join(", ")}</div>
      {category && (
        <div>
          <div className="value error">{category.title}</div>
          <div className="muted">{category.description}</div>
        </div>
      )}
      {result.errors.length > 0 && (
        <ul className="scheduler-error-list">
          {result.errors.map((err, i) => (
            <li key={i}>
              {category ? (
                <details>
                  <summary>{t.scheduler.showDetails}</summary>
                  <div className="muted scheduler-error-raw">{err}</div>
                </details>
              ) : (
                err
              )}
            </li>
          ))}
        </ul>
      )}
      <UnmatchedExecutions result={result} t={t} />
    </div>
  );
}

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const { t } = useSettings();

  const refreshAll = () => {
    queryClient.invalidateQueries();
  };

  const runOnceMutation = useMutation({
    mutationFn: runOnce,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["engine-status"] });
      queryClient.invalidateQueries({ queryKey: ["scheduler-runs"] });
      queryClient.invalidateQueries({ queryKey: ["signals"] });
      queryClient.invalidateQueries({ queryKey: ["trades"] });
      queryClient.invalidateQueries({ queryKey: ["positions"] });
    },
  });

  const syncOrdersMutation = useMutation({
    mutationFn: syncOrders,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["engine-status"] });
      queryClient.invalidateQueries({ queryKey: ["scheduler-runs"] });
      queryClient.invalidateQueries({ queryKey: ["trades"] });
      queryClient.invalidateQueries({ queryKey: ["positions"] });
    },
  });

  return (
    <div className="app">
      <h1>{t.dashboard.title}</h1>

      <EngineStatusCard />
      <SchedulerSettingsCard />
      <SchedulerRunsCard />

      <div className="card">
        <h2>{t.dashboard.actions}</h2>
        <div className="actions">
          <button
            className="primary"
            disabled={runOnceMutation.isPending}
            onClick={() => runOnceMutation.mutate()}
          >
            {t.dashboard.runOnce}
          </button>
          <button
            className="primary"
            disabled={syncOrdersMutation.isPending}
            onClick={() => syncOrdersMutation.mutate()}
          >
            {t.dashboard.syncOrders}
          </button>
          <button onClick={refreshAll}>{t.common.refresh}</button>
        </div>

        {runOnceMutation.isSuccess && (
          <div className="action-result">
            <RunOnceResultsTable results={runOnceMutation.data} />
          </div>
        )}
        {runOnceMutation.isError && (
          <p className="action-result value error">{(runOnceMutation.error as Error)?.message}</p>
        )}

        {syncOrdersMutation.isSuccess && <SyncOrdersResult result={syncOrdersMutation.data} />}
        {syncOrdersMutation.isError && (
          <p className="action-result value error">{(syncOrdersMutation.error as Error)?.message}</p>
        )}
      </div>

      <PortfolioSummaryCard />
      <PositionsTable />
      <TradesTable />
      <SignalsTable />
      <RiskControls />
    </div>
  );
}
