import { useMutation, useQueryClient } from "@tanstack/react-query";
import { runOnce, syncOrders } from "../api/client";
import EngineStatusCard from "../components/EngineStatusCard";
import SchedulerRunsCard from "../components/SchedulerRunsCard";
import PositionsTable from "../components/PositionsTable";
import TradesTable from "../components/TradesTable";
import SignalsTable from "../components/SignalsTable";
import RiskControls from "../components/RiskControls";

export default function DashboardPage() {
  const queryClient = useQueryClient();

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
      <h1>AI Trading Platform Dashboard</h1>

      <EngineStatusCard />
      <SchedulerRunsCard />

      <div className="card">
        <h2>Actions</h2>
        <div className="actions">
          <button
            className="primary"
            disabled={runOnceMutation.isPending}
            onClick={() => runOnceMutation.mutate()}
          >
            Run Once
          </button>
          <button
            className="primary"
            disabled={syncOrdersMutation.isPending}
            onClick={() => syncOrdersMutation.mutate()}
          >
            Sync Orders
          </button>
          <button onClick={refreshAll}>새로고침</button>
        </div>

        {runOnceMutation.isSuccess && (
          <pre className="action-result">{JSON.stringify(runOnceMutation.data, null, 2)}</pre>
        )}
        {runOnceMutation.isError && (
          <p className="action-result value error">{(runOnceMutation.error as Error)?.message}</p>
        )}

        {syncOrdersMutation.isSuccess && (
          <pre className="action-result">{JSON.stringify(syncOrdersMutation.data, null, 2)}</pre>
        )}
        {syncOrdersMutation.isError && (
          <p className="action-result value error">{(syncOrdersMutation.error as Error)?.message}</p>
        )}
      </div>

      <PositionsTable />
      <TradesTable />
      <SignalsTable />
      <RiskControls />
    </div>
  );
}
