import { useState } from "react";
import ActionInboxSection from "../components/research/ActionInboxSection";
import ScannersSection from "../components/research/ScannersSection";
import CandidatesSection from "../components/research/CandidatesSection";
import AssignmentsSection from "../components/research/AssignmentsSection";
import ExperimentsSection from "../components/research/ExperimentsSection";
import ProposalsSection from "../components/research/ProposalsSection";
import ScannerProposalsSection from "../components/research/ScannerProposalsSection";
import ReportsSection from "../components/research/ReportsSection";
import PromotionsSection from "../components/research/PromotionsSection";
import MarketContextSection from "../components/research/MarketContextSection";
import PipelineSection from "../components/research/PipelineSection";
import ChartSection from "../components/research/ChartSection";
import RetrospectiveSection from "../components/research/RetrospectiveSection";
import AiCostSection from "../components/research/AiCostSection";
import FunnelSection from "../components/research/FunnelSection";
import SafetySection from "../components/research/SafetySection";
import AnalysisAuditSection from "../components/research/AnalysisAuditSection";
import OperationsSection from "../components/research/OperationsSection";
import OperationsTrendSection from "../components/research/OperationsTrendSection";
import PortfolioSection from "../components/research/PortfolioSection";
import DataFreshnessSection from "../components/research/DataFreshnessSection";
import TradeActivitySection from "../components/research/TradeActivitySection";
import RiskEventsSection from "../components/research/RiskEventsSection";
import PromotionReadinessSection from "../components/research/PromotionReadinessSection";
import AutonomousJobsSection from "../components/research/AutonomousJobsSection";
import LeaderTrendSection from "../components/research/LeaderTrendSection";

type Section =
  | "ops"
  | "inbox"
  | "ops-trend"
  | "autonomous-jobs"
  | "pipeline"
  | "proposals"
  | "scanner-proposals"
  | "scanners"
  | "candidates"
  | "leader-trend"
  | "assignments"
  | "experiments"
  | "reports"
  | "promotions"
  | "context"
  | "chart"
  | "retro"
  | "funnel"
  | "ai-cost"
  | "safety"
  | "analysis-audit"
  | "portfolio"
  | "freshness"
  | "trade-activity"
  | "risk-events"
  | "promotion-readiness";

const SECTIONS: { key: Section; label: string }[] = [
  { key: "ops", label: "운영 종합" },
  { key: "inbox", label: "액션 인박스" },
  { key: "ops-trend", label: "운영 추세" },
  { key: "autonomous-jobs", label: "자율 잡 제어" },
  { key: "pipeline", label: "파이프라인" },
  { key: "proposals", label: "AI 전략 제안" },
  { key: "scanner-proposals", label: "AI 스캐너 제안" },
  { key: "scanners", label: "스캐너" },
  { key: "candidates", label: "후보 종목" },
  { key: "leader-trend", label: "주도주 리서치" },
  { key: "assignments", label: "전략 배정" },
  { key: "experiments", label: "실험 비교" },
  { key: "reports", label: "일일 리포트" },
  { key: "promotions", label: "실전 승격" },
  { key: "context", label: "시장 맥락" },
  { key: "chart", label: "매매 차트" },
  { key: "retro", label: "제안 회고" },
  { key: "funnel", label: "제안 퍼널" },
  { key: "ai-cost", label: "AI 비용" },
  { key: "safety", label: "안전 점검" },
  { key: "analysis-audit", label: "분석 감사" },
  { key: "portfolio", label: "포트폴리오" },
  { key: "freshness", label: "데이터 신선도" },
  { key: "trade-activity", label: "거래 활동" },
  { key: "risk-events", label: "리스크 이벤트" },
  { key: "promotion-readiness", label: "승격 준비" },
];

export default function ResearchPage() {
  const [section, setSection] = useState<Section>("ops");

  return (
    <div className="app">
      <h1>AI 전략 연구소</h1>
      <p className="muted">
        시장 감시 → 후보 발견 → 전략 배정 → 실험 비교 → AI 제안 → 승인 → 실전 승격까지의 연구 루프.
      </p>
      <div className="sub-nav">
        {SECTIONS.map((s) => (
          <button key={s.key} className={section === s.key ? "primary" : undefined}
            onClick={() => setSection(s.key)}>
            {s.label}
          </button>
        ))}
      </div>

      {section === "ops" && <OperationsSection />}
      {section === "inbox" && (
        <ActionInboxSection onNavigate={(s) => setSection(s as Section)} />
      )}
      {section === "ops-trend" && <OperationsTrendSection />}
      {section === "autonomous-jobs" && <AutonomousJobsSection />}
      {section === "pipeline" && <PipelineSection />}
      {section === "proposals" && <ProposalsSection />}
      {section === "scanner-proposals" && <ScannerProposalsSection />}
      {section === "scanners" && <ScannersSection />}
      {section === "candidates" && <CandidatesSection />}
      {section === "leader-trend" && <LeaderTrendSection />}
      {section === "assignments" && <AssignmentsSection />}
      {section === "experiments" && <ExperimentsSection />}
      {section === "reports" && <ReportsSection />}
      {section === "promotions" && <PromotionsSection />}
      {section === "context" && <MarketContextSection />}
      {section === "chart" && <ChartSection />}
      {section === "retro" && <RetrospectiveSection />}
      {section === "funnel" && <FunnelSection />}
      {section === "ai-cost" && <AiCostSection />}
      {section === "safety" && <SafetySection />}
      {section === "analysis-audit" && <AnalysisAuditSection />}
      {section === "portfolio" && <PortfolioSection />}
      {section === "freshness" && <DataFreshnessSection />}
      {section === "trade-activity" && <TradeActivitySection />}
      {section === "risk-events" && <RiskEventsSection />}
      {section === "promotion-readiness" && <PromotionReadinessSection />}
    </div>
  );
}
