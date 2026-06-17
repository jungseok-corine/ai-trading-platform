import axios from "axios";
import type {
  AIProviderStatusRead,
  AnalysisRun,
  AnalysisRunCreateRequest,
  BrokerSyncResult,
  EngineStatus,
  OrderSyncResult,
  PortfolioSummary,
  Position,
  RefreshPricesResult,
  RiskConfig,
  SchedulerRun,
  SchedulerSettings,
  SchedulerSettingsUpdateRequest,
  SignalLog,
  SignalOutcomeRead,
  SignalOutcomeSummary,
  Strategy,
  StrategyRunResult,
  StrategyVersion,
  StrategyVersionCreateRequest,
  StrategyVersionPerformanceRead,
  StrategyVersionUpdateRequest,
  Trade,
  Watchlist,
  WatchlistBulkStrategyCreateRequest,
  WatchlistBulkStrategyCreateResponse,
  WatchlistCreateRequest,
  WatchlistSymbol,
  WatchlistSymbolCreateRequest,
  WatchlistSymbolUpdateRequest,
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

export async function getSchedulerSettings(): Promise<SchedulerSettings> {
  const { data } = await apiClient.get<SchedulerSettings>("/engine/scheduler-settings");
  return data;
}

export async function updateSchedulerSettings(
  payload: SchedulerSettingsUpdateRequest,
): Promise<SchedulerSettings> {
  const { data } = await apiClient.patch<SchedulerSettings>("/engine/scheduler-settings", payload);
  return data;
}

export async function getSignals(): Promise<SignalLog[]> {
  const { data } = await apiClient.get<SignalLog[]>("/signals");
  return data;
}

export async function getSignalOutcome(signalId: number): Promise<SignalOutcomeRead> {
  const { data } = await apiClient.get<SignalOutcomeRead>(`/signals/${signalId}/outcome`);
  return data;
}

export async function getOutcomesSummary(limit = 100): Promise<SignalOutcomeSummary> {
  const { data } = await apiClient.get<SignalOutcomeSummary>("/signals/outcomes/summary", {
    params: { limit },
  });
  return data;
}

export async function getTrades(): Promise<Trade[]> {
  const { data } = await apiClient.get<Trade[]>("/trades");
  return data;
}

export async function getPositions(accountId?: number): Promise<Position[]> {
  const { data } = await apiClient.get<Position[]>("/positions", {
    params: accountId !== undefined ? { account_id: accountId } : undefined,
  });
  return data;
}

export async function getPortfolioSummary(accountId: number): Promise<PortfolioSummary> {
  const { data } = await apiClient.get<PortfolioSummary>("/portfolio/summary", {
    params: { account_id: accountId },
  });
  return data;
}

export async function refreshAllPrices(accountId: number): Promise<RefreshPricesResult> {
  const { data } = await apiClient.post<RefreshPricesResult>("/positions/refresh-prices", null, {
    params: { account_id: accountId },
  });
  return data;
}

export async function syncPositionsFromBroker(accountId: number): Promise<BrokerSyncResult> {
  const { data } = await apiClient.post<BrokerSyncResult>("/positions/sync-from-broker", null, {
    params: { account_id: accountId },
  });
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

export async function getVersionPerformance(
  strategyId: number,
  versionId: number,
): Promise<StrategyVersionPerformanceRead> {
  const { data } = await apiClient.get<StrategyVersionPerformanceRead>(
    `/strategies/${strategyId}/versions/${versionId}/performance`,
  );
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

export async function getWatchlists(): Promise<Watchlist[]> {
  const { data } = await apiClient.get<Watchlist[]>("/watchlists");
  return data;
}

export async function createWatchlist(payload: WatchlistCreateRequest): Promise<Watchlist> {
  const { data } = await apiClient.post<Watchlist>("/watchlists", payload);
  return data;
}

export async function getWatchlistSymbols(watchlistId: number): Promise<WatchlistSymbol[]> {
  const { data } = await apiClient.get<WatchlistSymbol[]>(`/watchlists/${watchlistId}/symbols`);
  return data;
}

export async function addWatchlistSymbol(
  watchlistId: number,
  payload: WatchlistSymbolCreateRequest,
): Promise<WatchlistSymbol> {
  const { data } = await apiClient.post<WatchlistSymbol>(`/watchlists/${watchlistId}/symbols`, payload);
  return data;
}

export async function updateWatchlistSymbol(
  watchlistId: number,
  symbolId: number,
  payload: WatchlistSymbolUpdateRequest,
): Promise<WatchlistSymbol> {
  const { data } = await apiClient.patch<WatchlistSymbol>(
    `/watchlists/${watchlistId}/symbols/${symbolId}`,
    payload,
  );
  return data;
}

export async function deleteWatchlistSymbol(watchlistId: number, symbolId: number): Promise<void> {
  await apiClient.delete(`/watchlists/${watchlistId}/symbols/${symbolId}`);
}

export async function createStrategyVersionsFromWatchlist(
  watchlistId: number,
  payload: WatchlistBulkStrategyCreateRequest,
): Promise<WatchlistBulkStrategyCreateResponse> {
  const { data } = await apiClient.post<WatchlistBulkStrategyCreateResponse>(
    `/watchlists/${watchlistId}/create-strategy-versions`,
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

// ---------------------------------------------------------------------------
// AI Analysis (C-2.8)
// ---------------------------------------------------------------------------

export async function getAIProviderStatuses(): Promise<AIProviderStatusRead[]> {
  const { data } = await apiClient.get<AIProviderStatusRead[]>("/ai-analysis/providers");
  return data;
}

export async function createStrategyAnalysisRun(
  strategyId: number,
  versionId: number,
  request: AnalysisRunCreateRequest,
): Promise<AnalysisRun> {
  const { data } = await apiClient.post<AnalysisRun>(
    `/strategies/${strategyId}/versions/${versionId}/analysis-runs`,
    request,
  );
  return data;
}

export async function getStrategyAnalysisRuns(
  strategyId: number,
  versionId: number,
): Promise<AnalysisRun[]> {
  const { data } = await apiClient.get<AnalysisRun[]>(
    `/strategies/${strategyId}/versions/${versionId}/analysis-runs`,
  );
  return data;
}

export async function getAnalysisRun(runId: number): Promise<AnalysisRun> {
  const { data } = await apiClient.get<AnalysisRun>(`/analysis-runs/${runId}`);
  return data;
}
