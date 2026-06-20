import { useQuery } from "@tanstack/react-query";
import { getSafetyStatus, getSchedulerHealth } from "../../api/research";

function Flag({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li>
      {ok ? "✅" : "⚠️"} {label}
    </li>
  );
}

export default function SafetySection() {
  const { data, isLoading } = useQuery({
    queryKey: ["safety-status"],
    queryFn: getSafetyStatus,
  });
  const { data: sched } = useQuery({
    queryKey: ["scheduler-health"],
    queryFn: getSchedulerHealth,
  });

  return (
    <div className="card">
      <h3>안전 점검 (불변식)</h3>
      <p className="muted">
        실거래 비활성·자동매매 off 등 핵심 안전 불변식이 그대로인지 확인합니다.
        read-only 점검이며, 드리프트는 경고로만 표시합니다(해제·변경은 사람이 직접).
      </p>

      {isLoading && <p className="muted">불러오는 중…</p>}
      {data && (
        <>
          <p className="action-result value">
            {data.invariants_ok ? "✅ 핵심 불변식 정상" : "⚠️ 점검 필요 — 아래 경고 확인"}
          </p>
          <ul>
            <Flag ok={!data.real_trading_enabled}
              label={`실거래(KIS_REAL_TRADING_ENABLED): ${data.real_trading_enabled ? "ON ⚠️" : "OFF"}`} />
            <Flag ok={data.auto_trade_versions === 0}
              label={`자동매매 전략 버전(활성/테스트): ${data.auto_trade_versions}개`} />
            <li>
              가드 pause: {data.guards.paused}/{data.guards.total} · 비상정지:{" "}
              {data.risk.emergency_stops}/{data.risk.configs}
            </li>
          </ul>

          {data.warnings.length > 0 && (
            <div className="table-wrapper">
              <table>
                <thead><tr><th>경고</th></tr></thead>
                <tbody>
                  {data.warnings.map((w, i) => (
                    <tr key={i}><td>{w}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h4>거래 스케줄러</h4>
          <ul>
            {Object.entries(data.schedulers).map(([k, v]) => (
              <li key={k}>{v ? "🟢 ON" : "⚪ OFF"} — {k}</li>
            ))}
          </ul>
        </>
      )}

      {sched && (
        <>
          <h4>자율 잡 건강</h4>
          <p className="muted">
            활성 잡이 제때 돌고 있는지 점검합니다. 비활성 잡은 점검 대상이 아닙니다.
            {sched.unhealthy_count > 0 ? ` ⚠️ 이상 ${sched.unhealthy_count}개` : " ✅ 이상 없음"}
          </p>
          <ul>
            {sched.jobs.filter((j) => j.enabled).length === 0 ? (
              <li className="muted">활성화된 자율 잡이 없습니다.</li>
            ) : (
              sched.jobs.filter((j) => j.enabled).map((j) => (
                <li key={j.job_id}>
                  {j.healthy ? "🟢" : "⚠️"} {j.job_id}
                  {j.reason ? ` — ${j.reason}` : ` — ${j.last_status ?? "?"}`}
                </li>
              ))
            )}
          </ul>
        </>
      )}
    </div>
  );
}
