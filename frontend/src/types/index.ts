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
}

export interface OrderSyncResult {
  checked: number;
  updated: number;
  errors: string[];
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
