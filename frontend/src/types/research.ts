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

export interface CandidateStrategyProposal {
  id: number;
  candidate_event_id: number;
  symbol_code: string;
  suggested_strategy_type: string;
  rationale: string | null;
  confidence: number | null;
  suggested_parameters: Record<string, unknown> | null;
  status: string; // pending | approved | rejected
  source: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
  review_note: string | null;
  experiment_id: number | null; // 준비된 paper 실험(DRAFT) 연결. null이면 미준비.
  prepared_at: string | null;
  created_at: string;
}

export interface PaperReadinessApproval {
  proposal_id: number;
  experiment_id: number;
  experiment_status: string; // 항상 draft (변경 안 함)
  strategy_version_ids: number[];
  strategy_version_statuses: string[]; // 모두 draft (변경 안 함)
  auto_trade_enabled_values: boolean[]; // 모두 false
  ready: boolean;
  already_ready: boolean;
  ready_at: string | null;
  ready_by: string | null;
  message: string;
}

export interface PaperSignalSession {
  id: number;
  candidate_strategy_proposal_id: number;
  experiment_id: number | null;
  strategy_version_id: number | null;
  candidate_event_id: number | null;
  symbol_code: string;
  status: string; // active | stopped
  started_by: string;
  started_at: string;
  stopped_at: string | null;
  stopped_by: string | null;
  last_run_at: string | null;
  last_error: string | null;
  run_count: number;
  signal_count: number;
  note: string | null;
  created_at: string;
}

export interface PaperSignalAnalysisRunResponse {
  id: number;
  provider: string;
  model: string;
  role: string;
  content: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  latency_ms: number | null;
  finish_reason: string | null;
  error_message: string | null;
}

export interface PaperSignalAnalysisRun {
  id: number;
  analysis_type: string;
  target_type: string;
  target_id: number;
  strategy_version_id: number | null;
  provider: string;
  model: string;
  status: string; // pending | running | succeeded | failed
  prompt_length: number | null;
  truncated: boolean;
  warnings: string[] | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  responses: PaperSignalAnalysisRunResponse[];
}

export interface PaperSignalOutcomeRow {
  signal_id: number;
  created_at: string | null;
  action: string;
  entry_price: number | null;
  return_pct: number | null;
  is_win: boolean | null;
  outcome_status: string; // analyzed | pending
}

export interface PaperSignalOutcomeBoard {
  session_id: number;
  status: string;
  symbol_code: string;
  horizon_minutes: number;
  signal_count: number;
  analyzed_count: number;
  pending_count: number;
  win_rate: number | null;
  avg_return_pct: number | null;
  best_return_pct: number | null;
  worst_return_pct: number | null;
  by_action: {
    action: string;
    count: number;
    analyzed_count: number;
    win_rate: number | null;
    avg_return_pct: number | null;
  }[];
  recent_signals: PaperSignalOutcomeRow[];
}

// M2.1 읽기 전용 비교 — 두 PaperSignalSession의 신호 outcome. 주문/생성/상태변경 없음.
export interface PaperSignalComparisonSide {
  session_id: number;
  status: string;
  symbol_code: string;
  strategy_version_id: number | null;
  signal_count: number;
  analyzed_count: number;
  pending_count: number;
  win_rate: number | null;
  avg_return_pct: number | null;
  best_return_pct: number | null;
  worst_return_pct: number | null;
  by_action: {
    action: string;
    count: number;
    analyzed_count: number;
    win_rate: number | null;
    avg_return_pct: number | null;
  }[];
}

export interface PaperSignalComparison {
  baseline_session_id: number;
  challenger_session_id: number;
  horizon_minutes: number;
  generated_at: string;
  symbol_match: boolean;
  baseline: PaperSignalComparisonSide;
  challenger: PaperSignalComparisonSide;
  deltas: {
    signal_count_delta: number | null;
    analyzed_count_delta: number | null;
    pending_count_delta: number | null;
    win_rate_delta: number | null;
    avg_return_pct_delta: number | null;
    best_return_pct_delta: number | null;
    worst_return_pct_delta: number | null;
    by_action: {
      action: string;
      count_delta: number | null;
      analyzed_count_delta: number | null;
      win_rate_delta: number | null;
      avg_return_pct_delta: number | null;
    }[];
  };
  warnings: string[];
}

// M2.5 Phase 2 — 비실행(prepared) challenger PaperSignalSession 준비 결과.
export interface ChallengerSessionPreparation {
  session_id: number;
  status: string; // 항상 "prepared"
  source_type: string; // 항상 "signal_challenger"
  source_strategy_proposal_id: number;
  baseline_session_id: number;
  challenger_version_id: number;
  symbol_code: string;
  runner_eligible: boolean; // 항상 false
  warnings: string[];
}

// M2.5 Phase 3 — prepared challenger 세션을 active로 전환한 결과(런너 대상 자격만).
export interface ChallengerSessionActivation {
  session_id: number;
  status: string; // 항상 "active"
  source_type: string; // 항상 "signal_challenger"
  source_strategy_proposal_id: number;
  baseline_session_id: number;
  strategy_version_id: number;
  runner_eligible: boolean; // 항상 true
  runner_currently_enabled: boolean;
  warnings: string[];
}

// M2.8 — 세션 1회 실행 결과(SignalLog만 · 주문/거래 없음 · 반복 아님).
export interface PaperSignalRunOnceResult {
  session_id: number;
  status: string; // 'active' (불변)
  signal_created: boolean;
  signal_id: number | null;
  reason: string | null;
  orders_created: number; // 항상 0
  trades_created: number; // 항상 0
  runner_enabled: boolean; // 항상 false
  warnings: string[];
}

// M2.10/M2.11 — baseline+challenger 페어 1회 실행 결과(SignalLog만 · 최대 2 · 주문/거래 없음 · 반복 아님).
export interface PaperSignalPairRunOnceSide {
  session_id: number;
  signal_created: boolean;
  signal_id: number | null;
  reason: string | null;
}

export interface PaperSignalPairRunOnceResult {
  baseline: PaperSignalPairRunOnceSide;
  challenger: PaperSignalPairRunOnceSide;
  orders_created: number; // 항상 0
  trades_created: number; // 항상 0
  runner_enabled: boolean; // 항상 false
  comparison_ready_hint: string;
  warnings: string[];
}

export interface PreparedExperiment {
  proposal_id: number;
  candidate_event_id: number;
  symbol_code: string;
  suggested_strategy_type: string;
  strategy_id: number | null;
  strategy_version_id: number | null;
  strategy_version_status: string; // 항상 draft
  experiment_id: number;
  experiment_status: string; // 항상 draft
  auto_trade_enabled: boolean; // 항상 false
  prepared_at: string | null;
  already_prepared: boolean;
}

export interface ScanResponse {
  scanner_rule_version_id: number;
  scanned: number;
  matched: number;
  candidates: CandidateEvent[];
}

export interface BucketStat {
  count: number;
  win_rate: number | null;
  avg_return_pct: number | null;
}

export interface CandidateAnalysis {
  horizon_minutes: number;
  total: number;
  analyzed: number;
  overall: BucketStat;
  by_time_bucket: Record<string, BucketStat>;
  by_condition: Record<string, BucketStat>;
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

// M2.2 — DRAFT-only challenger 준비 결과(승인 아님 · runner 미대상 · 주문/세션 없음).
export interface SignalChallengerPreparation {
  proposal_id: number;
  source_analysis_run_id: number | null;
  source_session_id: number | null;
  base_version_id: number;
  challenger_version_id: number;
  challenger_status: string;
  auto_trade_enabled: boolean;
  proposal_status: string;
  no_change: boolean;
  warnings: string[];
}

// --- Scanner proposal (C-2.39) ---------------------------------------------
export interface ScannerProposal {
  id: number;
  scanner_rule_id: number;
  base_version_id: number | null;
  title: string;
  summary: string | null;
  rationale: string | null;
  expected_effect: string | null;
  risk_notes: string | null;
  suggested_conditions: ScannerCondition[];
  source: string;
  status: ProposalStatus;
  created_version_id: number | null;
  reviewed_by: string | null;
  review_note: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface ConditionDiff {
  type: string;
  before: unknown;
  after: unknown;
}

export interface ScannerProposalDetail extends ScannerProposal {
  diff: ConditionDiff[];
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

// --- Status transition plan (C-2.29.1) -------------------------------------
export interface TransitionPlanNewVersion {
  status: string;
  reason: string;
  // strategy 제안에만 존재. scanner 제안에는 없을 수 있다.
  auto_trade_enabled?: boolean;
}

export interface TransitionPlanPreviousVersion {
  version_id: number;
  current_status: string;
  proposed_action: string; // "KEEP" | "ARCHIVE"
  reason: string;
  running_experiment_ids: number[];
  roles: string[];
}

export interface TransitionPlanBlockedAction {
  action: string; // e.g. "ARCHIVE_VERSION"
  version_id: number;
  reason: string;
}

export interface TransitionPlan {
  proposal_id: number;
  proposal_type: "strategy" | "scanner";
  new_version: TransitionPlanNewVersion;
  previous_versions: TransitionPlanPreviousVersion[];
  blocked_actions: TransitionPlanBlockedAction[];
  safety_warnings: string[];
  plan_valid: boolean;
}

// --- Live promotion review (C-2.29) ----------------------------------------
export interface LiveReadinessReport {
  strategy_version_id: number;
  criteria_id: number | null;
  passed: boolean;
  trades_count: number;
  days: number;
  expectancy: number;
  max_drawdown: number;
  checks: PromotionCheck[];
  intel_context: Record<string, unknown> | null;
  evaluation_id: number | null;
}

export interface LivePromotionRecord {
  id: number;
  strategy_version_id: number;
  promotion_evaluation_id: number | null;
  status: string;
  criteria_passed: boolean;
  readiness_snapshot: Record<string, unknown> | null;
  risk_snapshot: Record<string, unknown> | null;
  approved_at: string;
  approved_by: string;
  note: string | null;
  created_at: string;
}

export interface LivePromoteResponse {
  record: LivePromotionRecord;
  readiness_snapshot: Record<string, unknown> | null;
  message: string;
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

// M2.14A/B-1/B-2 — pair-scoped 반복 신호 기록 *계획*. 사람이 누를 때만 동작(디스패처/스케줄러 아님).
export interface PaperSignalRecurringRun {
  id: number;
  status: string; // prepared | active | stopped | completed | failed
  scope_type: string;
  baseline_session_id: number;
  challenger_session_id: number;
  interval_seconds: number;
  max_runs: number;
  completed_runs: number;
  last_run_at: string | null;
  next_run_at: string | null;
  created_by: string;
  stopped_by: string | null;
  stopped_at: string | null;
  note: string | null;
  last_error: string | null;
  orders_created: number; // 항상 0
  trades_created: number; // 항상 0
  warnings: string[];
}

// M2.14B-2 — tick-once 결과(계획 메타데이터 + baseline/challenger 각 1회 평가 결과).
export interface PaperSignalRecurringTickSide {
  session_id: number;
  signal_created: boolean;
  signal_id: number | null;
  reason: string | null;
}

export interface PaperSignalRecurringTickResult extends PaperSignalRecurringRun {
  baseline: PaperSignalRecurringTickSide;
  challenger: PaperSignalRecurringTickSide;
}

// M2.14B-3b/3c/3e — 디스패처 readiness/status(읽기 전용). 이 응답은 아무것도 실행하지 않는다.
export interface RecurringDispatcherConfig {
  paper_signal_recurring_plan_dispatcher_enabled: boolean;
  paper_signal_session_runner_enabled: boolean;
  kis_real_trading_enabled: boolean;
}

export interface RecurringDispatcherPlanCounts {
  total: number;
  prepared: number;
  active: number;
  stopped: number;
  completed: number;
  failed: number;
  due_active: number;
  not_due_active: number;
  active_missing_next_run_at: number;
  active_exhausted: number;
  with_last_error: number;
}

export interface RecurringDispatcherSafetyInvariants {
  scans_recurring_runs_only: boolean;
  global_runner_forbidden: boolean;
  signal_log_only_future_requirement: boolean;
  orders_forbidden: boolean;
  trades_forbidden: boolean;
  broker_kis_forbidden: boolean;
}

export interface RecurringDispatcherReadiness {
  dispatcher_stage: string;
  dispatcher_implemented: boolean;
  service_core_implemented: boolean;
  scheduler_dispatcher_implemented: boolean;
  api_execution_endpoint_registered: boolean;
  scheduler_job_registered: boolean;
  can_execute: boolean;
  execution_blocked_reason: string;
  config: RecurringDispatcherConfig;
  plan_counts: RecurringDispatcherPlanCounts;
  readiness_blockers: string[];
  safety_invariants: RecurringDispatcherSafetyInvariants;
  warnings: string[];
}
