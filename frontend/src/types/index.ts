export type TradeSide = "buy" | "sell";

export type OrderStatus = "pending" | "filled" | "partial" | "cancelled" | "rejected";

export interface EngineStatus {
  scheduler_running: boolean;
  registered_jobs: string[];
  last_run_at: string | null;
  last_error: string | null;
  active_strategy_count: number;
  order_sync_last_run_at: string | null;
  order_sync_last_error: string | null;
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

export interface OrderSyncResult {
  checked: number;
  updated: number;
  matched: number;
  unmatched: number;
  unmatched_order_ids: string[];
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
