import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getOperationsTrend, recordOperationsSnapshot } from "../../api/research";

function pnl(n: number): string {
  return `${n >= 0 ? "+" : ""}₩${Math.round(n).toLocaleString()}`;
}

export default function OperationsTrendSection() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["operations-trend"],
    queryFn: () => getOperationsTrend(30),
  });
  const record = useMutation({
    mutationFn: recordOperationsSnapshot,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["operations-trend"] }),
  });

  return (
    <div className="card">
      <h3>운영 추세</h3>
      <p className="muted">
        일자별 운영 종합 헤드라인(비용·실현손익·검토 대기·승격 후보)의 추세입니다. 스냅샷은 다이제스트
        잡이 매일 적재하거나, 아래 버튼으로 지금 한 건 적재할 수 있습니다. read-only 집계입니다.
      </p>
      <button onClick={() => record.mutate()} disabled={record.isPending}>
        {record.isPending ? "적재 중…" : "지금 스냅샷 적재"}
      </button>

      {isLoading && <p className="muted">불러오는 중…</p>}
      {data && (data.length === 0 ? (
        <p className="muted">아직 적재된 스냅샷이 없습니다.</p>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>날짜</th><th>안전</th><th>검토대기</th><th>승격후보</th>
                <th>AI비용</th><th>실현손익</th><th>승률</th>
              </tr>
            </thead>
            <tbody>
              {[...data].reverse().map((s) => (
                <tr key={s.snapshot_date}>
                  <td>{s.snapshot_date}</td>
                  <td>{s.invariants_ok ? "✅" : "⚠️"}</td>
                  <td>{s.pending_total}</td>
                  <td>{s.promotion_ready}</td>
                  <td>${s.est_cost_usd.toFixed(2)}</td>
                  <td>{pnl(s.total_pnl)}</td>
                  <td>{s.win_rate !== null ? `${s.win_rate}%` : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
