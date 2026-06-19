// C-2.33: 연구 루프(스캐너/후보/배정/실험/제안/리포트/승격/맥락) 타입.

export type MarketCode = "KR" | "US";
export type ScannerRuleStatus = "draft" | "testing" | "active" | "archived";
export type ProposalStatus = "pending" | "approved" | "rejected";
export type ExperimentStatus = "draft" | "running" | "completed" | "archived";
export type VariantRole = "champion" | "challenger";

// --- Scanner ---------------------------------------------------------------
export interface ScannerRule {
  id: number;
  market: MarketCode;
  name: string;
  description: string | null;
  enabled: boolean;
  created_at: string;
  version_count: number;
}

export interface ScannerCondition {
  type: string;
  params: Record<string, unknown>;
}

export interface ScannerRuleVersion {
  id: number;
  scanner_rule_id: number;
  version_no: number;
  conditions: ScannerCondition[];
  status: ScannerRuleStatus;
  change_description: string | null;
  created_at: string;
  updated_at: string;
}

export interface CandidateEvent {
  id: number;
  scanner_rule_version_id: number;
  market: MarketCode;
  symbol_code: string;
  triggered_at: string;
  score: number;
  matched_conditions: string[] | null;
  facts: Record<string, unknown> | null;
  context_snapshot_id: number | null;
  created_at: string;
}

export interface ScanResponse {
  scanner_rule_version_id: number;
  scanned: number;
  matched: number;
  candidates: CandidateEvent[];
}

// --- Assignment ------------------------------------------------------------
export interface AssignmentRule {
  id: number;
  market: MarketCode;
  name: string;
  description: string | null;
  scanner_rule_id: number | null;
  strategy_type: string;
  default_parameters: Record<string, unknown> | null;
  priority: number;
  enabled: boolean;
  created_at: string;
}

export interface AssignmentLog {
  id: number;
  candidate_event_id: number;
  strategy_assignment_rule_id: number | null;
  market: MarketCode;
  symbol_code: string;
  strategy_type: string;
  assigned_parameters: Record<string, unknown> | null;
  created_at: string;
}

// --- Experiment ------------------------------------------------------------
export interface Experiment {
  id: number;
  market: MarketCode;
  name: string;
  description: string | null;
  status: ExperimentStatus;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
}

export interface ExperimentVariant {
  id: number;
  experiment_id: number;
  strategy_version_id: number;
  role: VariantRole;
  label: string | null;
  created_at: string;
}

export interface ExperimentDetail extends Experiment {
  variants: ExperimentVariant[];
}

export interface VariantMetrics {
  trades_count: number;
  win_count: number;
  loss_count: number;
  win_rate: string;
  avg_profit: string;
  avg_loss: string;
  profit_factor: string | null;
  expectancy: string;
  max_drawdown: string;
}

export interface VariantComparison {
  variant_id: number;
  strategy_version_id: number;
  role: VariantRole;
  label: string | null;
  metrics: VariantMetrics;
}

export interface ComparisonResult {
  experiment_id: number;
  variants: VariantComparison[];
  winner_variant_id: number | null;
}

// --- Proposal --------------------------------------------------------------
export interface StrategyProposal {
  id: number;
  strategy_id: number;
  base_version_id: number | null;
  ai_analysis_run_id: number | null;
  title: string;
  summary: string | null;
  rationale: string | null;
  expected_effect: string | null;
  risk_notes: string | null;
  suggested_parameters: Record<string, unknown>;
  source: string;
  status: ProposalStatus;
  created_version_id: number | null;
  reviewed_by: string | null;
  review_note: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface ParamDiff {
  key: string;
  before: unknown;
  after: unknown;
}

export interface ProposalDetail extends StrategyProposal {
  diff: ParamDiff[];
}

// --- News / US market ------------------------------------------------------
export interface NewsEvent {
  id: number;
  market: MarketCode;
  symbol_code: string | null;
  source: string;
  headline: string;
  url: string | null;
  sentiment: string | null;
  published_at: string;
  themes: string[] | null;
  created_at: string;
}

export interface UsMarketSnapshot {
  id: number;
  session_date: string;
  nasdaq_change_pct: string | null;
  sp500_change_pct: string | null;
  sox_change_pct: string | null;
  treasury_10y: string | null;
  vix: string | null;
  major_news: string[] | null;
  data: Record<string, unknown> | null;
  created_at: string;
}

// --- Daily report ----------------------------------------------------------
export interface DailyReport {
  id: number;
  market: MarketCode;
  report_date: string;
  summary: string | null;
  sections: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

// --- Promotion -------------------------------------------------------------
export interface PromotionCriteria {
  id: number;
  market: MarketCode;
  name: string;
  min_trade_count: number;
  min_days: number;
  min_expectancy: string;
  max_drawdown: string | null;
  enabled: boolean;
  created_at: string;
}

export interface PromotionCheck {
  name: string;
  passed: boolean;
  actual: string;
  threshold: string;
}

export interface PromotionEvaluation {
  strategy_version_id: number;
  criteria_id: number;
  passed: boolean;
  trades_count: number;
  days: number;
  expectancy: string;
  max_drawdown: string;
  checks: PromotionCheck[];
}

// --- Research pipeline ------------------------------------------------------
export interface PipelineVersionRun {
  scanner_rule_version_id: number;
  scanned: number;
  matched: number;
  assigned: number;
}

export interface PipelineSummary {
  versions: number;
  symbols: number;
  candidates: number;
  assignments: number;
  per_version: PipelineVersionRun[];
}

export interface PipelineRun {
  id: number;
  job_id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  error_message: string | null;
  summary: PipelineSummary | null;
  created_at: string;
}
