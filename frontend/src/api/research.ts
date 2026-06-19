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
