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
import AiActivityFeedSection from "../components/research/AiActivityFeedSection";
import BacktestSection from "../components/research/BacktestSection";
import ExecutionQualitySection from "../components/research/ExecutionQualitySection";

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
  | "promotion-readiness"
  | "ai-feed"
  | "backtest"
  | "execution-quality";

// C-6.6: 사용자 동선 4뷰 — "매일 내려야 하는 결정과 그 근거만 전면에".
// 기존 섹션은 전부 유지하고 그룹으로 재배치만 했다 (삭제 없음).
type Group = "home" | "approvals" | "scoreboard" | "operations";

const GROUPS: { key: Group; label: string; sections: { key: Section; label: string }[] }[] = [
  {
    key: "home",
    label: "홈",
    sections: [
      { key: "ops", label: "오늘 요약" },
      { key: "ai-feed", label: "AI 피드" },
      { key: "safety", label: "안전 점검" },
      { key: "portfolio", label: "포트폴리오" },
    ],
  },
  {
    key: "approvals",
    label: "승인함",
    sections: [
      { key: "inbox", label: "액션 인박스" },
      { key: "proposals", label: "AI 전략 제안" },
      { key: "scanner-proposals", label: "AI 스캐너 제안" },
      { key: "promotions", label: "실전 승격" },
    ],
  },
  {
    key: "scoreboard",
    label: "전략 성적표",
    sections: [
      { key: "experiments", label: "실험 비교" },
      { key: "backtest", label: "백테스트" },
      { key: "retro", label: "제안 회고" },
      { key: "promotion-readiness", label: "승격 준비" },
      { key: "trade-activity", label: "거래 활동" },
      { key: "execution-quality", label: "체결 품질" },
      { key: "reports", label: "일일 리포트" },
      { key: "chart", label: "매매 차트" },
    ],
  },
  {
    key: "operations",
    label: "운영 (고급)",
    sections: [
      { key: "ops-trend", label: "운영 추세" },
      { key: "autonomous-jobs", label: "자율 잡 제어" },
      { key: "pipeline", label: "파이프라인" },
      { key: "scanners", label: "스캐너" },
      { key: "candidates", label: "후보 종목" },
      { key: "leader-trend", label: "주도주 리서치" },
      { key: "assignments", label: "전략 배정" },
      { key: "context", label: "시장 맥락" },
      { key: "funnel", label: "제안 퍼널" },
      { key: "ai-cost", label: "AI 비용" },
      { key: "analysis-audit", label: "분석 감사" },
      { key: "freshness", label: "데이터 신선도" },
      { key: "risk-events", label: "리스크 이벤트" },
    ],
  },
];

// inbox의 onNavigate가 임의 섹션 키를 넘겨도 해당 그룹으로 함께 이동하도록 역매핑.
const SECTION_TO_GROUP: Record<string, Group> = Object.fromEntries(
  GROUPS.flatMap((g) => g.sections.map((s) => [s.key, g.key]))
) as Record<string, Group>;

export default function ResearchPage() {
  const [group, setGroup] = useState<Group>("home");
  const [section, setSection] = useState<Section>("ops");

  const navigate = (target: Section) => {
    setSection(target);
    const targetGroup = SECTION_TO_GROUP[target];
    if (targetGroup) setGroup(targetGroup);
  };

  const activeGroup = GROUPS.find((g) => g.key === group) ?? GROUPS[0];

  return (
    <div className="app">
      <h1>AI 전략 연구소</h1>
      <p className="muted">
        시장 감시 → 후보 발견 → 전략 배정 → 실험 비교 → AI 제안 → 승인 → 실전 승격까지의 연구 루프.
      </p>
      <div className="sub-nav">
        {GROUPS.map((g) => (
          <button
            key={g.key}
            className={group === g.key ? "primary" : undefined}
            onClick={() => {
              setGroup(g.key);
              setSection(g.sections[0].key);
            }}
          >
            {g.label}
          </button>
        ))}
      </div>
      {activeGroup.sections.length > 1 && (
        <div className="sub-nav sub-nav-secondary">
          {activeGroup.sections.map((s) => (
            <button
              key={s.key}
              className={section === s.key ? "primary" : undefined}
              onClick={() => setSection(s.key)}
            >
              {s.label}
            </button>
          ))}
        </div>
      )}

      {section === "ops" && <OperationsSection />}
      {section === "inbox" && <ActionInboxSection onNavigate={(s) => navigate(s as Section)} />}
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
      {section === "ai-feed" && <AiActivityFeedSection />}
      {section === "backtest" && <BacktestSection />}
      {section === "execution-quality" && <ExecutionQualitySection />}
    </div>
  );
}
