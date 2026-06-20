import { useQuery } from "@tanstack/react-query";
import { getAnalysisAudit } from "../../api/research";

const STATUS_LABEL: Record<string, string> = {
  succeeded: "✅", failed: "❌", running: "⏳", pending: "·",
};

export default function AnalysisAuditSection() {
  const { data, isLoading } = useQuery({
    queryKey: ["analysis-audit"],
    queryFn: () => getAnalysisAudit(30),
  });

  return (
    <div className="card">
      <h3>AI 분석 실행 감사</h3>
      <p className="muted">
        최근 AI 분석 run이 무엇을 분석했고, 토큰/비용은 얼마였고, 제안으로 이어졌는지 추적합니다.
        read-only 집계입니다.
      </p>

      {isLoading && <p className="muted">불러오는 중…</p>}
      {data && (data.length === 0 ? (
        <p className="muted">분석 실행 기록이 없습니다.</p>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>#</th><th>일시</th><th>상태</th><th>mode</th>
                <th>provider/model</th><th>전략버전</th><th>토큰</th>
                <th>비용</th><th>제안</th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td>{r.created_at?.slice(0, 16).replace("T", " ") ?? "-"}</td>
                  <td>{STATUS_LABEL[r.status] ?? r.status}{r.truncated ? " ✂️" : ""}{r.warnings > 0 ? ` ⚠️${r.warnings}` : ""}</td>
                  <td>{r.mode}</td>
                  <td>{r.provider}/{r.model}</td>
                  <td>{r.strategy_version_id ?? "-"}</td>
                  <td>{r.total_tokens.toLocaleString()}</td>
                  <td>${r.est_cost_usd.toFixed(r.est_cost_usd < 1 ? 4 : 2)}</td>
                  <td>{r.proposals_created > 0 ? `📝 ${r.proposals_created}` : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
