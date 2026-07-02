// C-6.12: 전역 안전 스트립 — 어느 탭에 있든 안전 상태가 항상 보인다.
// read-only 표시 전용. 조치(비상정지 등)는 대시보드 RiskControls/안전 점검 섹션에서.
import { useQuery } from "@tanstack/react-query";
import { getSafetyStatus } from "../api/research";

export default function GlobalSafetyStrip() {
  const { data } = useQuery({
    queryKey: ["global-safety-status"],
    queryFn: getSafetyStatus,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  if (!data) return null;

  const ok = data.invariants_ok && !data.real_trading_enabled;
  const paused = data.guards.paused > 0;

  return (
    <div
      className={`safety-strip ${ok ? "safety-ok" : "safety-alert"}`}
      title={data.warnings.join("\n") || "안전 불변식 정상"}
    >
      <span>{ok ? "🟢" : "🔴"}</span>
      <span>
        실거래 {data.real_trading_enabled ? "ON⚠️" : "OFF"} · 자동매매 버전{" "}
        {data.auto_trade_versions} · 매매가드 {paused ? "일시정지" : "가동"}
      </span>
      {data.warnings.length > 0 && (
        <span className="safety-strip-warn">경고 {data.warnings.length}건</span>
      )}
    </div>
  );
}
