import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { getRiskConfig, setEmergencyStop } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";

const ACCOUNT_ID_STORAGE_KEY = "riskControls.accountId";

function loadStoredAccountId(): string {
  try {
    const stored = window.localStorage.getItem(ACCOUNT_ID_STORAGE_KEY);
    if (stored && /^\d+$/.test(stored)) return stored;
  } catch {
    // localStorage 접근 불가(프라이빗 모드 등) 시 기본값 사용
  }
  return "1";
}

export default function RiskControls() {
  const { t } = useSettings();
  const [accountIdInput, setAccountIdInput] = useState<string>(loadStoredAccountId);
  const queryClient = useQueryClient();

  const isValidAccountId = /^\d+$/.test(accountIdInput) && Number(accountIdInput) > 0;
  const accountId = isValidAccountId ? Number(accountIdInput) : null;

  useEffect(() => {
    if (isValidAccountId) {
      try {
        window.localStorage.setItem(ACCOUNT_ID_STORAGE_KEY, accountIdInput);
      } catch {
        // localStorage 접근 불가 시 무시
      }
    }
  }, [accountIdInput, isValidAccountId]);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["risk-config", accountId],
    queryFn: () => getRiskConfig(accountId as number),
    enabled: accountId !== null,
  });

  const isNotFound = axios.isAxiosError(error) && error.response?.status === 404;

  const emergencyStopMutation = useMutation({
    mutationFn: (enabled: boolean) => setEmergencyStop(accountId as number, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["risk-config", accountId] });
    },
  });

  return (
    <div className="card">
      <h2>{t.risk.title}</h2>
      <div className="risk-controls-form">
        <label htmlFor="risk-account-id">{t.risk.accountId}</label>
        <input
          id="risk-account-id"
          type="text"
          inputMode="numeric"
          value={accountIdInput}
          onChange={(e) => {
            const next = e.target.value;
            if (next === "" || /^\d+$/.test(next)) {
              setAccountIdInput(next);
            }
          }}
        />
      </div>

      {!isValidAccountId && <p className="muted">{t.risk.accountIdPlaceholder}</p>}
      {accountId !== null && isLoading && <p className="muted">{t.common.loading}</p>}
      {accountId !== null && isError && isNotFound && (
        <p className="muted">{t.risk.notFound(accountId)}</p>
      )}
      {accountId !== null && isError && !isNotFound && (
        <p className="value error">{(error as Error)?.message ?? t.common.loadError}</p>
      )}

      {data && (
        <div className="status-grid">
          <div className="status-item">
            <span className="label">{t.risk.emergencyStop}</span>
            <span className={`pill ${data.emergency_stop ? "on" : "off"}`}>
              {data.emergency_stop ? "ON" : "OFF"}
            </span>
          </div>
          <div className="status-item">
            <span className="label">{t.risk.maxDailyLossAmount}</span>
            <span className="value">{data.max_daily_loss_amount}</span>
          </div>
          <div className="status-item">
            <span className="label">{t.risk.maxPositionSize}</span>
            <span className="value">{data.max_position_size}</span>
          </div>
          <div className="status-item">
            <span className="label">{t.risk.maxOpenPositions}</span>
            <span className="value">{data.max_open_positions}</span>
          </div>
          <div className="status-item">
            <span className="label">{t.risk.maxTradesPerDay}</span>
            <span className="value">{data.max_trades_per_day}</span>
          </div>
          <div className="status-item">
            <span className="label">{t.risk.consecutiveLossLimit}</span>
            <span className="value">{data.consecutive_loss_limit}</span>
          </div>
        </div>
      )}

      <div className="actions" style={{ marginTop: 16 }}>
        <button
          className="danger"
          disabled={!data || emergencyStopMutation.isPending || data?.emergency_stop === true}
          onClick={() => emergencyStopMutation.mutate(true)}
        >
          {t.risk.emergencyStopOn}
        </button>
        <button
          className="primary"
          disabled={!data || emergencyStopMutation.isPending || data?.emergency_stop === false}
          onClick={() => emergencyStopMutation.mutate(false)}
        >
          {t.risk.emergencyStopOff}
        </button>
      </div>
      {emergencyStopMutation.isError && (
        <p className="action-result value error">
          {(emergencyStopMutation.error as Error)?.message ?? t.risk.changeFailed}
        </p>
      )}
    </div>
  );
}
