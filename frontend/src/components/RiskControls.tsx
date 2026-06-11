import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRiskConfig, setEmergencyStop } from "../api/client";

export default function RiskControls() {
  const [accountId, setAccountId] = useState(1);
  const queryClient = useQueryClient();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["risk-config", accountId],
    queryFn: () => getRiskConfig(accountId),
  });

  const emergencyStopMutation = useMutation({
    mutationFn: (enabled: boolean) => setEmergencyStop(accountId, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["risk-config", accountId] });
    },
  });

  return (
    <div className="card">
      <h2>Risk Controls</h2>
      <div className="risk-controls-form">
        <label htmlFor="risk-account-id">Account ID</label>
        <input
          id="risk-account-id"
          type="number"
          value={accountId}
          onChange={(e) => setAccountId(Number(e.target.value) || 1)}
        />
      </div>

      {isLoading && <p className="muted">불러오는 중...</p>}
      {isError && <p className="value error">{(error as Error)?.message ?? "조회 실패"}</p>}

      {data && (
        <div className="status-grid">
          <div className="status-item">
            <span className="label">Emergency Stop</span>
            <span className={`pill ${data.emergency_stop ? "on" : "off"}`}>
              {data.emergency_stop ? "ON" : "OFF"}
            </span>
          </div>
          <div className="status-item">
            <span className="label">Max Daily Loss Amount</span>
            <span className="value">{data.max_daily_loss_amount}</span>
          </div>
          <div className="status-item">
            <span className="label">Max Position Size</span>
            <span className="value">{data.max_position_size}</span>
          </div>
          <div className="status-item">
            <span className="label">Max Open Positions</span>
            <span className="value">{data.max_open_positions}</span>
          </div>
          <div className="status-item">
            <span className="label">Max Trades Per Day</span>
            <span className="value">{data.max_trades_per_day}</span>
          </div>
          <div className="status-item">
            <span className="label">Consecutive Loss Limit</span>
            <span className="value">{data.consecutive_loss_limit}</span>
          </div>
        </div>
      )}

      <div className="actions" style={{ marginTop: 16 }}>
        <button
          className="danger"
          disabled={emergencyStopMutation.isPending || data?.emergency_stop === true}
          onClick={() => emergencyStopMutation.mutate(true)}
        >
          Emergency Stop ON
        </button>
        <button
          className="primary"
          disabled={emergencyStopMutation.isPending || data?.emergency_stop === false}
          onClick={() => emergencyStopMutation.mutate(false)}
        >
          Emergency Stop OFF
        </button>
      </div>
      {emergencyStopMutation.isError && (
        <p className="action-result value error">
          {(emergencyStopMutation.error as Error)?.message ?? "변경 실패"}
        </p>
      )}
    </div>
  );
}
