export type TradeSide = "buy" | "sell";

export type OrderStatus = "pending" | "filled" | "partial" | "cancelled" | "rejected";

export interface EngineStatus {
  scheduler_running: boolean;
  registered_jobs: string[];
  last_run_at: string | null;
  last_error: string | null;
  last_error_category: string | null;
  active_strategy_count: number;
  order_sync_last_run_at: string | null;
  order_sync_last_error: string | null;
  order_sync_last_error_category: string | null;
  recent_run_has_failure: boolean;
  auto_trade_enabled_count: number;
}

export type SchedulerRunStatus = "success" | "failed" | "skipped";

export interface SchedulerRunErrorEntry {
  strategy_version_id: number | null;
  symbol_code: string | null;
  message: string;
  category: string | null;
}

export interface SchedulerRunSummary {
  versions_run?: number;
  signals_created?: number;
  trades_attempted?: number;
  checked?: number;
  updated?: number;
  matched?: number;
  unmatched?: number;
  unmatched_order_ids?: string[];
  executions?: OrderSyncExecutionSummary[];
  errors?: SchedulerRunErrorEntry[];
  error_category?: string | null;
  skipped_reason?: string | null;
}

export interface SchedulerRun {
  id: number;
  job_id: string;
  status: SchedulerRunStatus;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  error_message: string | null;
  summary: SchedulerRunSummary | null;
  created_at: string;
}

export interface SchedulerSettings {
  strategy_scheduler_interval_seconds: number;
  order_sync_scheduler_interval_seconds: number;
  updated_at: string;
}

export interface SchedulerSettingsUpdateRequest {
  strategy_scheduler_interval_seconds?: number;
  order_sync_scheduler_interval_seconds?: number;
}

export interface OrderSyncExecutionSummary {
  order_id: string;
  filled_quantity: number;
  filled_price: number | null;
}

export interface OrderSyncResult {
  checked: number;
  updated: number;
  matched: number;
  unmatched: number;
  unmatched_order_ids: string[];
  executions: OrderSyncExecutionSummary[];
  errors: string[];
  error_category?: string | null;
  skipped_reason?: string | null;
}

export interface StrategyRunResult {
  strategy_version_id: number | null;
  symbol_code: string;
  signal_created: boolean;
  signal_id: number | null;
  auto_trade_enabled: boolean;
  trade_attempted: boolean;
  trade_approved: boolean | null;
  trade_id: number | null;
  rejection_reason: string | null;
  error: string | null;
  error_category: string | null;
}

export interface Position {
  id: number;
  account_id: number;
  symbol_code: string;
  symbol_name: string | null;
  quantity: number;
  avg_entry_price: string;
  realized_pnl: string;
  unrealized_pnl: string;
  last_price: string | null;
  updated_at: string;
}

export interface PortfolioSummary {
  account_id: number;
  position_count: number;
  total_quantity: number;
  total_cost_amount: string;
  total_eval_amount: string;
  total_unrealized_pnl: string;
  total_unrealized_pnl_pct: string;
  total_realized_pnl: string;
  total_pnl: string;
}

export interface RefreshPricesResult {
  updated: number;
  positions: Position[];
}

export interface BrokerSyncResult {
  created: number;
  updated: number;
  zeroed: number;
  positions: Position[];
}

export interface Trade {
  id: number;
  account_id: number;
  strategy_version_id: number | null;
  symbol_code: string;
  symbol_name: string | null;
  side: TradeSide;
  entry_time: string | null;
  exit_time: string | null;
  entry_price: string | null;
  exit_price: string | null;
  quantity: number;
  pnl_amount: string | null;
  pnl_pct: string | null;
  entry_reason: string | null;
  exit_reason: string | null;
  market_condition: Record<string, unknown> | null;
  ai_analysis_id: number | null;
  order_status: OrderStatus;
  broker_order_id: string | null;
  partial_fill: Record<string, unknown> | null;
  position_applied_quantity: number;
  commission: string | null;
  tax: string | null;
  slippage: string | null;
  created_at: string;
}

export interface SignalLog {
  id: number;
  symbol_code: string;
  symbol_name?: string | null;
  symbol_display?: string | null;
  strategy_version_id: number | null;
  signal_type: TradeSide;
  generated_at: string;
  candle_ts: string | null;
  reason: string | null;
  short_ma: string | null;
  long_ma: string | null;
  price: string | null;
  quantity: number | null;
  created_at: string;
}

export interface RiskConfig {
  id: number;
  account_id: number;
  max_daily_loss_amount: string;
  max_position_size: string;
  max_open_positions: number;
  max_trades_per_day: number;
  consecutive_loss_limit: number;
  emergency_stop: boolean;
  updated_at: string;
}

export type StrategyVersionStatus = "draft" | "testing" | "active" | "retired";

export interface Strategy {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  version_count: number;
}

export interface StrategyVersionParameters {
  strategy_type: string;
  symbol_code: string;
  short_window: number;
  long_window: number;
  quantity: number;
  timeframe: string;
  account_id: number | null;
  enabled: boolean;
  auto_trade_enabled: boolean;
}

export interface StrategyVersion {
  id: number;
  strategy_id: number;
  version_no: number;
  parameters: StrategyVersionParameters;
  change_description: string | null;
  status: StrategyVersionStatus;
  win_rate: string | null;
  avg_profit: string | null;
  avg_loss: string | null;
  mdd: string | null;
  created_at: string;
  updated_at: string;
}

export interface StrategyVersionCreateRequest {
  parameters: StrategyVersionParameters;
  change_description?: string | null;
  status?: StrategyVersionStatus;
}

export interface StrategyVersionUpdateRequest {
  parameters?: StrategyVersionParameters;
  change_description?: string | null;
  status?: StrategyVersionStatus;
}

export interface Watchlist {
  id: number;
  name: string;
  description: string | null;
  enabled: boolean;
  symbol_count: number;
  created_at: string;
  updated_at: string;
}

export interface WatchlistCreateRequest {
  name: string;
  description?: string | null;
  enabled?: boolean;
}

export interface WatchlistSymbol {
  id: number;
  watchlist_id: number;
  symbol_code: string;
  symbol_name: string | null;
  enabled: boolean;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface WatchlistSymbolCreateRequest {
  symbol_code: string;
  symbol_name?: string | null;
  enabled?: boolean;
  note?: string | null;
}

export interface WatchlistSymbolUpdateRequest {
  symbol_name?: string | null;
  enabled?: boolean;
  note?: string | null;
}

export interface WatchlistBulkStrategyCreateRequest {
  strategy_id: number;
  short_window?: number;
  long_window?: number;
  timeframe?: string;
  quantity?: number;
  account_id?: number | null;
  status?: StrategyVersionStatus;
  auto_trade_enabled?: boolean;
}

export interface WatchlistBulkStrategyCreateItem {
  symbol_code: string;
  symbol_name: string | null;
  created: boolean;
  strategy_version_id: number | null;
  reason: string | null;
}

export interface WatchlistBulkStrategyCreateResponse {
  strategy_id: number;
  items: WatchlistBulkStrategyCreateItem[];
}

export interface StrategyVersionPerformanceByHorizon {
  horizon_minutes: number;
  count: number;
  win_rate: string;
  avg_return_pct: string;
  avg_directional_return_pct: string;
  avg_mfe_pct: string | null;
  avg_mae_pct: string | null;
}

export interface StrategyVersionPerformanceBySignalType {
  signal_type: TradeSide;
  signal_count: number;
  analyzed_count: number;
  win_rate_5m: string | null;
  avg_directional_return_pct_5m: string | null;
}

export interface StrategyVersionPerformanceBySymbol {
  symbol_code: string;
  signal_count: number;
  analyzed_count: number;
  win_rate_5m: string | null;
  avg_directional_return_pct_5m: string | null;
}

export interface StrategyVersionActualTradingPerformance {
  trade_count: number;
  filled_count: number;
  total_pnl_amount: string | null;
  win_trade_count: number | null;
  loss_trade_count: number | null;
  note: string;
}

export interface StrategyVersionPerformanceRead {
  strategy_id: number;
  strategy_version_id: number;
  total_signals: number;
  analyzed_signals: number;
  skipped_signals: number;
  by_horizon: StrategyVersionPerformanceByHorizon[];
  by_signal_type: StrategyVersionPerformanceBySignalType[];
  by_symbol: StrategyVersionPerformanceBySymbol[];
  actual_trading: StrategyVersionActualTradingPerformance | null;
}

export interface SignalOutcomeHorizonResult {
  horizon_minutes: number;
  close_price: string | null;
  return_pct: string | null;
  directional_return_pct: string | null;
  is_win: boolean | null;
  available: boolean;
}

export interface SignalOutcomeRead {
  signal_id: number;
  symbol_code: string;
  signal_type: TradeSide;
  signal_ts: string;
  timeframe: string;
  entry_price: string | null;
  horizons: SignalOutcomeHorizonResult[];
  mfe_pct: string | null;
  mae_pct: string | null;
  available: boolean;
  note: string | null;
}

export interface SignalOutcomeByHorizon {
  horizon_minutes: number;
  count: number;
  avg_return_pct: string;
  win_rate: string;
}

export interface SignalOutcomeBySymbol {
  symbol_code: string;
  signal_count: number;
  analyzed_count: number;
  win_rate_5m: string | null;
}

export interface SignalOutcomeBySignalType {
  signal_type: TradeSide;
  signal_count: number;
  analyzed_count: number;
  win_rate_5m: string | null;
}

export interface SignalOutcomeSummary {
  total_signals: number;
  analyzed_count: number;
  skipped_count: number;
  by_horizon: SignalOutcomeByHorizon[];
  by_symbol: SignalOutcomeBySymbol[];
  by_signal_type: SignalOutcomeBySignalType[];
}

// ---------------------------------------------------------------------------
// AI Analysis (C-2.8)
// ---------------------------------------------------------------------------

export type AIProviderStatus = "available" | "missing_config" | "not_implemented";

export interface AIProviderStatusRead {
  provider: string;
  implemented: boolean;
  configured: boolean;
  default_model: string | null;
  missing_settings: string[];
  status: AIProviderStatus;
  note: string | null;
}

export type AnalysisRunMode = "single" | "dual";
export type AnalysisRunStatus = "running" | "succeeded" | "failed";
export type PromptType = "overview" | "risk" | "improvement";

export interface AIModelResponse {
  id: number;
  run_id: number;
  role: string;
  provider: string;
  model: string;
  content: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  latency_ms: number | null;
  finish_reason: string | null;
  error_message: string | null;
  created_at: string;
}

export interface AnalysisRun {
  id: number;
  strategy_id: number;
  strategy_version_id: number;
  mode: AnalysisRunMode;
  prompt_type: string;
  provider: string;
  model: string;
  secondary_provider?: string | null;
  secondary_model?: string | null;
  status: AnalysisRunStatus;
  input_hash: string | null;
  prompt_hash: string | null;
  prompt_length: number | null;
  truncated: boolean;
  warnings: string[] | null;
  error_message: string | null;
  responses: AIModelResponse[];
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface AnalysisRunCreateRequest {
  prompt_type: PromptType;
  provider: string;
  model?: string | null;
  mode?: AnalysisRunMode;
  secondary_provider?: string | null;
  secondary_model?: string | null;
  enable_critique?: boolean;
  enable_synthesis?: boolean;
}

export const DEFAULT_STRATEGY_VERSION_PARAMETERS: StrategyVersionParameters = {
  strategy_type: "moving_average_cross",
  symbol_code: "",
  short_window: 5,
  long_window: 20,
  quantity: 1,
  timeframe: "1m",
  account_id: null,
  enabled: true,
  auto_trade_enabled: false,
};
