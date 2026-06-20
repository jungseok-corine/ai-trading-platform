// C-2.33: 연구 루프 API 클라이언트.
import { apiClient } from "./client";
import type {
  AssignmentLog,
  AssignmentRule,
  CandidateAnalysis,
  CandidateEvent,
  ComparisonResult,
  DailyReport,
  Experiment,
  ExperimentDetail,
  ExperimentVariant,
  MarketCode,
  NewsEvent,
  PipelineRun,
  PipelineSummary,
  PromotionCriteria,
  PromotionEvaluation,
  ProposalDetail,
  ProposalStatus,
  ScanResponse,
  ScannerCondition,
  ScannerProposal,
  ScannerProposalDetail,
  ScannerRule,
  ScannerRuleStatus,
  ScannerRuleVersion,
  StrategyProposal,
  UsMarketSnapshot,
  VariantRole,
} from "../types/research";

// --- Scanner ---------------------------------------------------------------
export async function getScannerRules(): Promise<ScannerRule[]> {
  const { data } = await apiClient.get<ScannerRule[]>("/scanner-rules");
  return data;
}

export async function createScannerRule(payload: {
  name: string;
  market?: MarketCode;
  description?: string | null;
}): Promise<ScannerRule> {
  const { data } = await apiClient.post<ScannerRule>("/scanner-rules", payload);
  return data;
}

export async function getScannerVersions(
  ruleId: number,
  includeArchived = false,
): Promise<ScannerRuleVersion[]> {
  const { data } = await apiClient.get<ScannerRuleVersion[]>(
    `/scanner-rules/${ruleId}/versions`,
    { params: { include_archived: includeArchived } },
  );
  return data;
}

export async function createScannerVersion(
  ruleId: number,
  payload: { conditions: ScannerCondition[]; change_description?: string | null; status?: ScannerRuleStatus },
): Promise<ScannerRuleVersion> {
  const { data } = await apiClient.post<ScannerRuleVersion>(
    `/scanner-rules/${ruleId}/versions`,
    payload,
  );
  return data;
}

export async function updateScannerVersionStatus(
  ruleId: number,
  versionId: number,
  status: ScannerRuleStatus,
): Promise<ScannerRuleVersion> {
  const { data } = await apiClient.patch<ScannerRuleVersion>(
    `/scanner-rules/${ruleId}/versions/${versionId}`,
    { status },
  );
  return data;
}

export async function scanMarket(
  ruleId: number,
  versionId: number,
  payload: { symbol_codes: string[]; timeframe?: string; volume_window?: number; lookback?: number },
): Promise<ScanResponse> {
  const { data } = await apiClient.post<ScanResponse>(
    `/scanner-rules/${ruleId}/versions/${versionId}/scan-market`,
    payload,
  );
  return data;
}

// --- Candidates ------------------------------------------------------------
export async function getCandidates(params?: {
  scanner_rule_version_id?: number;
  symbol_code?: string;
  market?: MarketCode;
  limit?: number;
}): Promise<CandidateEvent[]> {
  const { data } = await apiClient.get<CandidateEvent[]>("/candidates", { params });
  return data;
}

export async function assignCandidate(candidateId: number): Promise<AssignmentLog | null> {
  const res = await apiClient.post(`/candidates/${candidateId}/assign`);
  return res.status === 204 ? null : (res.data as AssignmentLog);
}

export async function getCandidateAnalysis(horizonMinutes = 30): Promise<CandidateAnalysis> {
  const { data } = await apiClient.get<CandidateAnalysis>("/candidates/analysis", {
    params: { horizon_minutes: horizonMinutes },
  });
  return data;
}

// --- Assignment rules ------------------------------------------------------
export async function getAssignmentRules(): Promise<AssignmentRule[]> {
  const { data } = await apiClient.get<AssignmentRule[]>("/assignment-rules");
  return data;
}

export async function createAssignmentRule(payload: {
  name: string;
  strategy_type: string;
  market?: MarketCode;
  scanner_rule_id?: number | null;
  default_parameters?: Record<string, unknown> | null;
  priority?: number;
  description?: string | null;
}): Promise<AssignmentRule> {
  const { data } = await apiClient.post<AssignmentRule>("/assignment-rules", payload);
  return data;
}

export async function getAssignmentLogs(params?: {
  candidate_event_id?: number;
  symbol_code?: string;
}): Promise<AssignmentLog[]> {
  const { data } = await apiClient.get<AssignmentLog[]>("/assignment-logs", { params });
  return data;
}

// --- Experiments -----------------------------------------------------------
export async function getExperiments(): Promise<Experiment[]> {
  const { data } = await apiClient.get<Experiment[]>("/experiments");
  return data;
}

export async function createExperiment(payload: {
  name: string;
  market?: MarketCode;
  description?: string | null;
}): Promise<Experiment> {
  const { data } = await apiClient.post<Experiment>("/experiments", payload);
  return data;
}

export async function getExperiment(id: number): Promise<ExperimentDetail> {
  const { data } = await apiClient.get<ExperimentDetail>(`/experiments/${id}`);
  return data;
}

export async function addExperimentVariant(
  experimentId: number,
  payload: { strategy_version_id: number; role?: VariantRole; label?: string | null },
): Promise<ExperimentVariant> {
  const { data } = await apiClient.post<ExperimentVariant>(
    `/experiments/${experimentId}/variants`,
    payload,
  );
  return data;
}

export async function compareExperiment(
  experimentId: number,
  persist = false,
): Promise<ComparisonResult> {
  const { data } = await apiClient.post<ComparisonResult>(
    `/experiments/${experimentId}/compare`,
    null,
    { params: { persist } },
  );
  return data;
}

// --- Proposals -------------------------------------------------------------
export async function getProposals(params?: {
  strategy_id?: number;
  status?: ProposalStatus;
}): Promise<StrategyProposal[]> {
  const { data } = await apiClient.get<StrategyProposal[]>("/strategy-proposals", { params });
  return data;
}

export async function getProposal(id: number): Promise<ProposalDetail> {
  const { data } = await apiClient.get<ProposalDetail>(`/strategy-proposals/${id}`);
  return data;
}

export async function generateProposal(payload: {
  strategy_id: number;
  version_id: number;
  ai_analysis_run_id?: number | null;
}): Promise<StrategyProposal | null> {
  const res = await apiClient.post("/strategy-proposals/generate", payload);
  return res.status === 204 ? null : (res.data as StrategyProposal);
}

export async function approveProposal(
  id: number,
  payload: { reviewed_by?: string | null; review_note?: string | null },
): Promise<{ proposal: StrategyProposal; created_version_id: number }> {
  const { data } = await apiClient.post(`/strategy-proposals/${id}/approve`, payload);
  return data;
}

export async function rejectProposal(
  id: number,
  payload: { reviewed_by?: string | null; review_note?: string | null },
): Promise<StrategyProposal> {
  const { data } = await apiClient.post<StrategyProposal>(
    `/strategy-proposals/${id}/reject`,
    payload,
  );
  return data;
}

// --- Scanner proposals (C-2.39) --------------------------------------------
export async function getScannerProposals(params?: {
  scanner_rule_id?: number;
  status?: ProposalStatus;
}): Promise<ScannerProposal[]> {
  const { data } = await apiClient.get<ScannerProposal[]>("/scanner-proposals", { params });
  return data;
}

export async function getScannerProposal(id: number): Promise<ScannerProposalDetail> {
  const { data } = await apiClient.get<ScannerProposalDetail>(`/scanner-proposals/${id}`);
  return data;
}

export async function generateScannerProposal(payload: {
  version_id: number;
  horizon_minutes?: number;
}): Promise<ScannerProposal | null> {
  const res = await apiClient.post("/scanner-proposals/generate", payload);
  return res.status === 204 ? null : (res.data as ScannerProposal);
}

export async function approveScannerProposal(
  id: number,
  payload: { reviewed_by?: string | null; review_note?: string | null },
): Promise<{ proposal: ScannerProposal; created_version_id: number }> {
  const { data } = await apiClient.post(`/scanner-proposals/${id}/approve`, payload);
  return data;
}

export async function rejectScannerProposal(
  id: number,
  payload: { reviewed_by?: string | null; review_note?: string | null },
): Promise<ScannerProposal> {
  const { data } = await apiClient.post<ScannerProposal>(
    `/scanner-proposals/${id}/reject`,
    payload,
  );
  return data;
}

// --- Trade chart (C-2.60) --------------------------------------------------
export interface ChartCandle {
  ts: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}
export interface ChartMarker {
  ts: string;
  side: string;
  price: number;
  kind: "entry" | "exit";
}
export interface ChartData {
  symbol_code: string;
  trading_day: string;
  timeframe: string;
  candles: ChartCandle[];
  markers: ChartMarker[];
}

export async function getChartData(
  strategyVersionId: number,
  tradingDay: string,
): Promise<ChartData> {
  const { data } = await apiClient.get<ChartData>("/analysis-bundle/chart-data", {
    params: { strategy_version_id: strategyVersionId, trading_day: tradingDay },
  });
  return data;
}

// --- Proposal retrospective (C-2.64) ---------------------------------------
export interface RetroEntry {
  proposal_id: number;
  kind: string;
  base_version_id: number | null;
  created_version_id: number | null;
  metric: string;
  base_metric: number | null;
  new_metric: number | null;
  base_samples: number;
  new_samples: number;
  verdict: string;
}

export async function getStrategyRetros(): Promise<RetroEntry[]> {
  const { data } = await apiClient.get<RetroEntry[]>("/proposal-retrospective/strategy");
  return data;
}
export async function getScannerRetros(): Promise<RetroEntry[]> {
  const { data } = await apiClient.get<RetroEntry[]>("/proposal-retrospective/scanner");
  return data;
}
export async function getRetroSummary(): Promise<{
  total: number; improved: number; worse: number; inconclusive: number;
}> {
  const { data } = await apiClient.get("/proposal-retrospective/summary");
  return data;
}

// --- Research status (C-2.43) ----------------------------------------------
export interface ResearchJobStatus {
  job_id: string;
  last_run_at: string | null;
  status: string | null;
  duration_ms: number | null;
  error_message: string | null;
}

export interface MacroRegime {
  regime: string;
  session_date: string | null;
  vix: number | null;
  vix_level: string | null;
  us_trend: string | null;
  us_avg_change_pct: number | null;
  semis_strength: string | null;
}

export interface ResearchStatus {
  jobs: ResearchJobStatus[];
  pending: { strategy: number; scanner: number; total: number };
  active: { scanner_versions: number; strategy_versions: number };
  retrospective: { total: number; improved: number; worse: number; inconclusive: number };
  macro: MacroRegime;
  disclosure_alerts: number;
}

export interface DisclosureAlert {
  symbol_code: string;
  headline: string;
  category: string | null;
  materiality: number | null;
  corp_name: string | null;
  published_at: string | null;
  url: string | null;
}

export async function getDisclosureAlerts(hours = 48): Promise<DisclosureAlert[]> {
  const { data } = await apiClient.get<DisclosureAlert[]>("/dart/alerts", {
    params: { hours },
  });
  return data;
}

export async function getResearchStatus(): Promise<ResearchStatus> {
  const { data } = await apiClient.get<ResearchStatus>("/research-status");
  return data;
}

// --- AI cost (C-3.1) -------------------------------------------------------
export interface AiCostModelRow {
  provider: string;
  model: string;
  responses: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  est_cost_usd: number;
  priced: boolean;
}

export interface AiCostDayRow {
  date: string;
  responses: number;
  total_tokens: number;
  est_cost_usd: number;
}

export interface AiCostBudget {
  budget_usd: number;
  used_usd: number;
  used_pct: number | null;
  threshold_pct: number;
  status: "ok" | "warn" | "over" | "disabled";
}

export interface AiCostSummary {
  days: number;
  total: {
    responses: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    est_cost_usd: number;
  };
  by_model: AiCostModelRow[];
  by_day: AiCostDayRow[];
  unpriced_models: string[];
  budget: AiCostBudget;
}

export async function getAiCostSummary(days = 30): Promise<AiCostSummary> {
  const { data } = await apiClient.get<AiCostSummary>("/ai-cost/summary", {
    params: { days },
  });
  return data;
}

// --- Promotion readiness (C-3.13) ------------------------------------------
export interface PromotionCheck {
  name: string;
  passed: boolean;
  actual: string;
  threshold: string;
}

export interface PromotionReadinessRow {
  strategy_version_id: number;
  label: string;
  status: string;
  passed: boolean;
  checks_passed: number;
  checks_total: number;
  trades_count: number;
  days: number;
  expectancy: number;
  max_drawdown: number;
  checks: PromotionCheck[];
}

export interface PromotionReadiness {
  criteria: {
    id: number;
    name: string;
    market: string;
    min_trade_count: number;
    min_days: number;
    min_expectancy: number;
    max_drawdown: number | null;
  } | null;
  rows: PromotionReadinessRow[];
  note: string;
}

export async function getPromotionReadiness(criteriaId?: number): Promise<PromotionReadiness> {
  const { data } = await apiClient.get<PromotionReadiness>("/promotion-readiness", {
    params: criteriaId ? { criteria_id: criteriaId } : undefined,
  });
  return data;
}

// --- Risk events (C-3.12) --------------------------------------------------
export interface RiskRuleRow {
  rule_name: string;
  approved: number;
  rejected: number;
}

export interface RiskRejection {
  rule_name: string | null;
  reason: string | null;
  strategy_version_id: number | null;
  created_at: string | null;
}

export interface RiskEventSummary {
  days: number;
  total: number;
  approved: number;
  rejected: number;
  rejection_rate: number | null;
  by_rule: RiskRuleRow[];
  recent_rejections: RiskRejection[];
}

export async function getRiskEventSummary(days = 30): Promise<RiskEventSummary> {
  const { data } = await apiClient.get<RiskEventSummary>("/risk-events/summary", {
    params: { days },
  });
  return data;
}

// --- Trade activity (C-3.11) -----------------------------------------------
export interface TradeBucket {
  trades: number;
  closed: number;
  wins: number;
  losses: number;
  total_pnl: number;
  win_rate: number | null;
  avg_pnl: number | null;
}

export interface TradeStrategyRow extends TradeBucket {
  strategy_version_id: number | null;
  label: string;
}

export interface TradeActivity {
  days: number;
  overall: TradeBucket;
  by_strategy: TradeStrategyRow[];
}

export async function getTradeActivity(days = 30): Promise<TradeActivity> {
  const { data } = await apiClient.get<TradeActivity>("/trade-activity", {
    params: { days },
  });
  return data;
}

// --- Data freshness (C-3.10) -----------------------------------------------
export interface FreshnessSource {
  source: string;
  present: boolean;
  last_at: string | null;
  age_hours: number | null;
  threshold_hours: number;
  stale: boolean;
}

export interface DataFreshness {
  checked_at: string;
  sources: FreshnessSource[];
  stale_count: number;
  stale_sources: string[];
}

export async function getDataFreshness(): Promise<DataFreshness> {
  const { data } = await apiClient.get<DataFreshness>("/data-freshness");
  return data;
}

// --- Operations snapshot trend (C-3.17) ------------------------------------
export interface OperationsSnapshot {
  snapshot_date: string;
  invariants_ok: boolean;
  pending_total: number;
  promotion_ready: number;
  est_cost_usd: number;
  total_pnl: number;
  win_rate: number | null;
}

export async function getOperationsTrend(days = 30): Promise<OperationsSnapshot[]> {
  const { data } = await apiClient.get<OperationsSnapshot[]>("/operations-snapshot/trend", {
    params: { days },
  });
  return data;
}

export async function recordOperationsSnapshot(): Promise<OperationsSnapshot> {
  const { data } = await apiClient.post<OperationsSnapshot>("/operations-snapshot/record");
  return data;
}

// --- Operations digest (C-3.8) ---------------------------------------------
export interface DigestAlert {
  level: "alert" | "attention";
  text: string;
}

export interface OperationsDigest {
  generated_at: string;
  severity: "ok" | "attention" | "alert";
  has_alerts: boolean;
  alerts: DigestAlert[];
  summary_line: string;
}

export async function getOperationsDigest(days = 30): Promise<OperationsDigest> {
  const { data } = await apiClient.get<OperationsDigest>("/operations-digest", {
    params: { days },
  });
  return data;
}

// --- Portfolio summary (C-3.6) ---------------------------------------------
export interface PortfolioPosition {
  account_id: number;
  symbol_code: string;
  symbol_name: string | null;
  quantity: number;
  avg_entry_price: number;
  last_price: number;
  cost_basis: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pct: number | null;
  exposure_pct: number | null;
  has_price: boolean;
}

export interface PortfolioSummary {
  open_positions: number;
  total_market_value: number;
  total_cost_basis: number;
  total_unrealized_pnl: number;
  total_realized_pnl: number;
  positions: PortfolioPosition[];
}

export async function getPortfolioSummary(): Promise<PortfolioSummary> {
  const { data } = await apiClient.get<PortfolioSummary>("/portfolio-summary");
  return data;
}

// --- Operations overview (C-3.5) -------------------------------------------
export interface OperationsOverview {
  days: number;
  safety: { invariants_ok: boolean; warnings: string[] };
  research: {
    pending_total: number;
    active_strategy_versions: number;
    active_scanner_versions: number;
    disclosure_alerts: number;
    macro_regime: string | null;
    promotion_ready: number;
  };
  funnel: {
    generated: number;
    approved: number;
    versions_created: number;
    approval_rate: number | null;
  };
  retrospective: { total: number; improved: number; worse: number; inconclusive: number };
  cost: {
    responses: number;
    total_tokens: number;
    est_cost_usd: number;
    budget_status: "ok" | "warn" | "over" | "disabled";
    budget_used_pct: number | null;
  };
  trading: {
    closed_trades: number;
    win_rate: number | null;
    total_pnl: number;
    risk_rejected: number;
    risk_rejection_rate: number | null;
  };
}

export async function getOperationsOverview(days = 30): Promise<OperationsOverview> {
  const { data } = await apiClient.get<OperationsOverview>("/operations-overview", {
    params: { days },
  });
  return data;
}

// --- Analysis audit (C-3.4) ------------------------------------------------
export interface AnalysisRunAudit {
  id: number;
  created_at: string | null;
  analysis_type: string;
  mode: string;
  provider: string;
  model: string;
  prompt_type: string;
  status: string;
  strategy_version_id: number | null;
  truncated: boolean;
  warnings: number;
  error_message: string | null;
  total_tokens: number;
  est_cost_usd: number;
  proposals_created: number;
}

export async function getAnalysisAudit(limit = 20): Promise<AnalysisRunAudit[]> {
  const { data } = await apiClient.get<AnalysisRunAudit[]>("/analysis-audit", {
    params: { limit },
  });
  return data;
}

// --- Safety status (C-3.3) -------------------------------------------------
export interface SafetyStatus {
  invariants_ok: boolean;
  real_trading_enabled: boolean;
  auto_trade_versions: number;
  guards: { total: number; paused: number };
  risk: { configs: number; emergency_stops: number };
  schedulers: Record<string, boolean>;
  warnings: string[];
}

export async function getSafetyStatus(): Promise<SafetyStatus> {
  const { data } = await apiClient.get<SafetyStatus>("/safety-status");
  return data;
}

// --- Proposal funnel (C-3.2) -----------------------------------------------
export interface FunnelStage {
  generated: number;
  pending: number;
  approved: number;
  rejected: number;
  versions_created: number;
  approval_rate: number | null;
}

export interface ProposalFunnel {
  days: number;
  strategy: FunnelStage;
  scanner: FunnelStage;
  combined: FunnelStage;
  retrospective: { total: number; improved: number; worse: number; inconclusive: number };
}

export async function getProposalFunnel(days = 30): Promise<ProposalFunnel> {
  const { data } = await apiClient.get<ProposalFunnel>("/proposal-funnel", {
    params: { days },
  });
  return data;
}

// --- Strategy review (C-2.42) ----------------------------------------------
export interface StrategyReviewSummary {
  versions_reviewed: number;
  proposals_created: number;
  skipped_existing: number;
  created_proposal_ids: number[];
}

export async function runStrategyReview(): Promise<StrategyReviewSummary> {
  const { data } = await apiClient.post<StrategyReviewSummary>("/strategy-review/run");
  return data;
}

// --- Scanner review (C-2.40) -----------------------------------------------
export interface ScannerReviewSummary {
  versions_reviewed: number;
  proposals_created: number;
  skipped_existing: number;
  created_proposal_ids: number[];
}

export async function runScannerReview(horizonMinutes = 30): Promise<ScannerReviewSummary> {
  const { data } = await apiClient.post<ScannerReviewSummary>("/scanner-review/run", {
    horizon_minutes: horizonMinutes,
  });
  return data;
}

// --- Bulk review (C-2.45) --------------------------------------------------
export interface BulkReviewResult {
  action: string;
  succeeded: number[];
  failed: { id: number; reason: string }[];
}

export async function bulkReviewScannerProposals(
  proposalIds: number[],
  action: "approve" | "reject",
  reviewedBy = "user",
): Promise<BulkReviewResult> {
  const { data } = await apiClient.post<BulkReviewResult>("/scanner-proposals/bulk-review", {
    proposal_ids: proposalIds,
    action,
    reviewed_by: reviewedBy,
  });
  return data;
}

export async function bulkReviewStrategyProposals(
  proposalIds: number[],
  action: "approve" | "reject",
  reviewedBy = "user",
): Promise<BulkReviewResult> {
  const { data } = await apiClient.post<BulkReviewResult>("/strategy-proposals/bulk-review", {
    proposal_ids: proposalIds,
    action,
    reviewed_by: reviewedBy,
  });
  return data;
}

// --- News / US market ------------------------------------------------------
export async function getNews(params?: {
  market?: MarketCode;
  symbol_code?: string;
}): Promise<NewsEvent[]> {
  const { data } = await apiClient.get<NewsEvent[]>("/news-events", { params });
  return data;
}

export async function createNews(payload: {
  headline: string;
  published_at: string;
  market?: MarketCode;
  symbol_code?: string | null;
  sentiment?: "positive" | "neutral" | "negative" | null;
  themes?: string[] | null;
}): Promise<NewsEvent> {
  const { data } = await apiClient.post<NewsEvent>("/news-events", payload);
  return data;
}

export async function getUsSnapshots(): Promise<UsMarketSnapshot[]> {
  const { data } = await apiClient.get<UsMarketSnapshot[]>("/us-market-snapshots");
  return data;
}

export async function upsertUsSnapshot(payload: {
  session_date: string;
  nasdaq_change_pct?: string | null;
  sp500_change_pct?: string | null;
  sox_change_pct?: string | null;
}): Promise<UsMarketSnapshot> {
  const { data } = await apiClient.put<UsMarketSnapshot>("/us-market-snapshots", payload);
  return data;
}

export interface UsRefreshResult {
  provider: string;
  updated: boolean;
  session_date: string | null;
  reason: string | null;
}

export async function refreshUsSnapshot(): Promise<UsRefreshResult> {
  const { data } = await apiClient.post<UsRefreshResult>("/us-market-snapshots/refresh");
  return data;
}

// --- Daily reports ---------------------------------------------------------
export async function getDailyReports(): Promise<DailyReport[]> {
  const { data } = await apiClient.get<DailyReport[]>("/daily-reports");
  return data;
}

export async function generateDailyReport(reportDate?: string): Promise<DailyReport> {
  const { data } = await apiClient.post<DailyReport>("/daily-reports/generate", null, {
    params: reportDate ? { report_date: reportDate } : undefined,
  });
  return data;
}

// --- Promotion -------------------------------------------------------------
export async function getPromotionCriteria(): Promise<PromotionCriteria[]> {
  const { data } = await apiClient.get<PromotionCriteria[]>("/promotion-criteria");
  return data;
}

export async function createPromotionCriteria(payload: {
  name: string;
  market?: MarketCode;
  min_trade_count?: number;
  min_days?: number;
  min_expectancy?: string;
  max_drawdown?: string | null;
}): Promise<PromotionCriteria> {
  const { data } = await apiClient.post<PromotionCriteria>("/promotion-criteria", payload);
  return data;
}

export async function evaluatePromotion(
  versionId: number,
  criteriaId: number,
  persist = false,
): Promise<PromotionEvaluation> {
  const { data } = await apiClient.post<PromotionEvaluation>(
    `/strategy-versions/${versionId}/promotion-evaluation`,
    null,
    { params: { criteria_id: criteriaId, persist } },
  );
  return data;
}

// --- Research pipeline ------------------------------------------------------
export async function runPipeline(payload?: {
  symbol_codes?: string[] | null;
  auto_assign?: boolean;
}): Promise<PipelineSummary> {
  const { data } = await apiClient.post<PipelineSummary>("/research-pipeline/run", payload ?? {});
  return data;
}

export async function getPipelineRuns(limit = 20): Promise<PipelineRun[]> {
  const { data } = await apiClient.get<PipelineRun[]>("/research-pipeline/runs", {
    params: { limit },
  });
  return data;
}
