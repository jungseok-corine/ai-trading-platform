import axios from "axios";
import type {
  EngineStatus,
  OrderSyncResult,
  Position,
  RiskConfig,
  SchedulerRun,
  SignalLog,
  Strategy,
  StrategyRunResult,
  StrategyVersion,
  StrategyVersionCreateRequest,
  StrategyVersionUpdateRequest,
  Trade,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

export const apiClient = axios.create({ baseURL: BASE_URL });

export async function getEngineStatus(): Promise<EngineStatus> {
  const { data } = await apiClient.get<EngineStatus>("/engine/status");
  return data;
}

export async function runOnce(): Promise<StrategyRunResult[]> {
  const { data } = await apiClient.post<StrategyRunResult[]>("/engine/run-once");
  return data;
}

export async function syncOrders(): Promise<OrderSyncResult> {
  const { data } = await apiClient.post<OrderSyncResult>("/engine/sync-orders");
  return data;
}

export async function getSchedulerRuns(limit = 20): Promise<SchedulerRun[]> {
  const { data } = await apiClient.get<SchedulerRun[]>("/engine/runs", { params: { limit } });
  return data;
}

export async function getSignals(): Promise<SignalLog[]> {
  const { data } = await apiClient.get<SignalLog[]>("/signals");
  return data;
}

export async function getTrades(): Promise<Trade[]> {
  const { data } = await apiClient.get<Trade[]>("/trades");
  return data;
}

export async function getPositions(): Promise<Position[]> {
  const { data } = await apiClient.get<Position[]>("/positions");
  return data;
}

export async function getStrategies(): Promise<Strategy[]> {
  const { data } = await apiClient.get<Strategy[]>("/strategies");
  return data;
}

export async function createStrategy(payload: {
  name: string;
  description?: string | null;
}): Promise<Strategy> {
  const { data } = await apiClient.post<Strategy>("/strategies", payload);
  return data;
}

export async function getStrategyVersions(strategyId: number): Promise<StrategyVersion[]> {
  const { data } = await apiClient.get<StrategyVersion[]>(`/strategies/${strategyId}/versions`);
  return data;
}

export async function createStrategyVersion(
  strategyId: number,
  payload: StrategyVersionCreateRequest,
): Promise<StrategyVersion> {
  const { data } = await apiClient.post<StrategyVersion>(`/strategies/${strategyId}/versions`, payload);
  return data;
}

export async function updateStrategyVersion(
  strategyId: number,
  versionId: number,
  payload: StrategyVersionUpdateRequest,
): Promise<StrategyVersion> {
  const { data } = await apiClient.patch<StrategyVersion>(
    `/strategies/${strategyId}/versions/${versionId}`,
    payload,
  );
  return data;
}

export async function getRiskConfig(accountId: number): Promise<RiskConfig> {
  const { data } = await apiClient.get<RiskConfig>(`/risk-config/${accountId}`);
  return data;
}

export async function setEmergencyStop(accountId: number, enabled: boolean): Promise<RiskConfig> {
  const { data } = await apiClient.post<RiskConfig>(`/risk-config/${accountId}/emergency-stop`, {
    enabled,
  });
  return data;
}
