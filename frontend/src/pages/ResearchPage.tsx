import { useState } from "react";
import ScannersSection from "../components/research/ScannersSection";
import CandidatesSection from "../components/research/CandidatesSection";
import AssignmentsSection from "../components/research/AssignmentsSection";
import ExperimentsSection from "../components/research/ExperimentsSection";
import ProposalsSection from "../components/research/ProposalsSection";
import ReportsSection from "../components/research/ReportsSection";
import PromotionsSection from "../components/research/PromotionsSection";
import MarketContextSection from "../components/research/MarketContextSection";

type Section =
  | "proposals"
  | "scanners"
  | "candidates"
  | "assignments"
  | "experiments"
  | "reports"
  | "promotions"
  | "context";

const SECTIONS: { key: Section; label: string }[] = [
  { key: "proposals", label: "AI 제안" },
  { key: "scanners", label: "스캐너" },
  { key: "candidates", label: "후보 종목" },
  { key: "assignments", label: "전략 배정" },
  { key: "experiments", label: "실험 비교" },
  { key: "reports", label: "일일 리포트" },
  { key: "promotions", label: "실전 승격" },
  { key: "context", label: "시장 맥락" },
];

export default function ResearchPage() {
  const [section, setSection] = useState<Section>("proposals");

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

      {section === "proposals" && <ProposalsSection />}
      {section === "scanners" && <ScannersSection />}
      {section === "candidates" && <CandidatesSection />}
      {section === "assignments" && <AssignmentsSection />}
      {section === "experiments" && <ExperimentsSection />}
      {section === "reports" && <ReportsSection />}
      {section === "promotions" && <PromotionsSection />}
      {section === "context" && <MarketContextSection />}
    </div>
  );
}
