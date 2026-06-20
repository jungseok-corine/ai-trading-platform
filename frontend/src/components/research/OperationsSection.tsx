import { useQuery } from "@tanstack/react-query";
import { getOperationsOverview } from "../../api/research";

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="stat-card">
      <div className="muted">{label}</div>
      <div className={accent ? "action-result value" : "value"}>{value}</div>
    </div>
  );
}

function rate(r: number | null): string {
  return r === null ? "-" : `${(r * 100).toFixed(0)}%`;
}

export default function OperationsSection() {
  const { data, isLoading } = useQuery({
    queryKey: ["operations-overview"],
    queryFn: () => getOperationsOverview(30),
  });

  return (
    <div className="card">
      <h3>운영 종합 관제</h3>
      <p className="muted">
        안전·연구 루프·제안 퍼널·AI 비용의 핵심만 한눈에. 세부는 각 전용 탭에서 봅니다.
        (최근 30일 기준, read-only)
      </p>

      {isLoading && <p className="muted">불러오는 중…</p>}
      {data && (
        <>
          <p className="action-result value">
            {data.safety.invariants_ok ? "✅ 안전 불변식 정상" : "⚠️ 안전 점검 필요"}
            {data.safety.warnings.length > 0 && ` — ${data.safety.warnings.join("; ")}`}
          </p>
          <div className="stat-grid">
            <Stat label="검토 대기 제안" value={`${data.research.pending_total}`} accent />
            <Stat label="활성 전략/스캐너 버전"
              value={`${data.research.active_strategy_versions} / ${data.research.active_scanner_versions}`} />
            <Stat label="공시 알림" value={`${data.research.disclosure_alerts}`} />
            <Stat label="매크로 레짐" value={data.research.macro_regime ?? "-"} />
            <Stat label="제안 생성→승인→버전"
              value={`${data.funnel.generated} → ${data.funnel.approved} → ${data.funnel.versions_created}`} />
            <Stat label="승인률" value={rate(data.funnel.approval_rate)} />
            <Stat label="회고 (개선/악화)"
              value={`${data.retrospective.improved} / ${data.retrospective.worse}`} />
            <Stat label="AI 비용 (30일)"
              value={`$${data.cost.est_cost_usd.toFixed(2)}`} accent />
          </div>
        </>
      )}
    </div>
  );
}
