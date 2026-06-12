import { useMutation, useQueryClient } from "@tanstack/react-query";
import { runOnce, syncOrders } from "../api/client";
import EngineStatusCard from "../components/EngineStatusCard";
import SchedulerRunsCard from "../components/SchedulerRunsCard";
import PortfolioSummaryCard from "../components/PortfolioSummaryCard";
import PositionsTable from "../components/PositionsTable";
import TradesTable from "../components/TradesTable";
import SignalsTable from "../components/SignalsTable";
import RiskControls from "../components/RiskControls";
import RunOnceResultsTable from "../components/RunOnceResultsTable";
import { useSettings } from "../i18n/SettingsContext";
import type { OrderSyncResult } from "../types";

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

  return (
    <div className="action-result">
      <div className="muted">{entries.map(([label, value]) => `${label}: ${value}`).join(", ")}</div>
      {result.errors.length > 0 && (
        <ul className="scheduler-error-list">
          {result.errors.map((err, i) => (
            <li key={i}>{err}</li>
          ))}
        </ul>
      )}
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
