import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { getSchedulerSettings, updateSchedulerSettings } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";

const MIN_INTERVAL_SECONDS = 60;

export default function SchedulerSettingsCard() {
  const { t, formatDateTime } = useSettings();
  const queryClient = useQueryClient();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["scheduler-settings"],
    queryFn: getSchedulerSettings,
  });

  const [strategyInterval, setStrategyInterval] = useState("");
  const [orderSyncInterval, setOrderSyncInterval] = useState("");

  useEffect(() => {
    if (data) {
      setStrategyInterval(String(data.strategy_scheduler_interval_seconds));
      setOrderSyncInterval(String(data.order_sync_scheduler_interval_seconds));
    }
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: updateSchedulerSettings,
    onSuccess: (updated) => {
      queryClient.setQueryData(["scheduler-settings"], updated);
    },
  });

  const strategyValue = Number(strategyInterval);
  const orderSyncValue = Number(orderSyncInterval);
  const isStrategyValid = Number.isInteger(strategyValue) && strategyValue >= MIN_INTERVAL_SECONDS;
  const isOrderSyncValid = Number.isInteger(orderSyncValue) && orderSyncValue >= MIN_INTERVAL_SECONDS;
  const canSave = isStrategyValid && isOrderSyncValid && !saveMutation.isPending;

  const saveErrorMessage = (() => {
    if (!saveMutation.isError) return null;
    if (axios.isAxiosError(saveMutation.error) && saveMutation.error.response?.status === 400) {
      return t.schedulerSettings.invalidInterval(MIN_INTERVAL_SECONDS);
    }
    return (saveMutation.error as Error)?.message ?? t.schedulerSettings.saveFailed;
  })();

  return (
    <div className="card">
      <h2>{t.schedulerSettings.title}</h2>
      <p className="section-description">{t.schedulerSettings.description}</p>

      {isLoading && <p className="muted">{t.common.loading}</p>}
      {isError && <p className="value error">{(error as Error)?.message ?? t.common.loadError}</p>}

      {data && (
        <>
          <div className="risk-controls-form">
            <label htmlFor="strategy-scheduler-interval">{t.schedulerSettings.strategyInterval}</label>
            <input
              id="strategy-scheduler-interval"
              type="number"
              min={MIN_INTERVAL_SECONDS}
              step={1}
              inputMode="numeric"
              value={strategyInterval}
              onChange={(e) => setStrategyInterval(e.target.value)}
            />
            <span className="muted">{t.schedulerSettings.unitSeconds}</span>
          </div>
          {!isStrategyValid && (
            <p className="value error">{t.schedulerSettings.invalidInterval(MIN_INTERVAL_SECONDS)}</p>
          )}

          <div className="risk-controls-form">
            <label htmlFor="order-sync-scheduler-interval">{t.schedulerSettings.orderSyncInterval}</label>
            <input
              id="order-sync-scheduler-interval"
              type="number"
              min={MIN_INTERVAL_SECONDS}
              step={1}
              inputMode="numeric"
              value={orderSyncInterval}
              onChange={(e) => setOrderSyncInterval(e.target.value)}
            />
            <span className="muted">{t.schedulerSettings.unitSeconds}</span>
          </div>
          {!isOrderSyncValid && (
            <p className="value error">{t.schedulerSettings.invalidInterval(MIN_INTERVAL_SECONDS)}</p>
          )}

          <p className="muted">{t.schedulerSettings.minIntervalHint}</p>

          <div className="status-item">
            <span className="label">{t.schedulerSettings.updatedAt}</span>
            <span className="value">{formatDateTime(data.updated_at)}</span>
          </div>

          <div className="actions" style={{ marginTop: 16 }}>
            <button
              className="primary"
              disabled={!canSave}
              onClick={() =>
                saveMutation.mutate({
                  strategy_scheduler_interval_seconds: strategyValue,
                  order_sync_scheduler_interval_seconds: orderSyncValue,
                })
              }
            >
              {saveMutation.isPending ? t.schedulerSettings.saving : t.schedulerSettings.save}
            </button>
          </div>

          {saveMutation.isSuccess && <p className="action-result value ok">{t.schedulerSettings.saveSuccess}</p>}
          {saveErrorMessage && <p className="action-result value error">{saveErrorMessage}</p>}
        </>
      )}
    </div>
  );
}
