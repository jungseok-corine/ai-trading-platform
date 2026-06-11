import axios from "axios";
import type {
  EngineStatus,
  OrderSyncResult,
  Position,
  RiskConfig,
  SignalLog,
  StrategyRunResult,
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
