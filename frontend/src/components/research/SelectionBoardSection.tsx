// C-7.4: 전략 종합 선정 보드 — "기록들을 합해서 알맞은 전략을 골라".
// read-only 랭킹 — 실전 배치는 승격 게이트(사람).
import { useQuery } from "@tanstack/react-query";
import { getSelectionBoard } from "../../api/research";

function bar(v: number, max: number): string {
  return `${((v / max) * 100).toFixed(0)}%`;
}

export default function SelectionBoardSection() {
  const { data, isLoading } = useQuery({
    queryKey: ["selection-board"],
    queryFn: getSelectionBoard,
    refetchInterval: 120_000,
  });

  return (
    <div className="card">
      <h3>전략 종합 선정 보드</h3>
      <p className="muted">
        백테스트(30) + Paper 실적(40) + 회고(15) + 레짐 적합(15) 종합 점수. 표본 없는 축은
        중립 — 실적이 쌓이며 갈립니다. 실전 배치는 승격 게이트에서 사람이 결정합니다.
      </p>
      {isLoading && <p className="muted">불러오는 중…</p>}
      {data && (
        <>
          <p className="muted">현재 매크로 레짐: {data.current_regime ?? "unknown"}</p>
          <table className="compact-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>#</th>
                <th>전략</th>
                <th>분봉</th>
                <th>적합 레짐</th>
                <th>표본</th>
                <th>종합</th>
                <th>백테스트</th>
                <th>Paper</th>
                <th>회고</th>
                <th>레짐</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r, i) => (
                <tr key={r.strategy_version_id}>
                  <td>{i + 1}</td>
                  <td style={{ textAlign: "left" }}>
                    v{r.strategy_version_id} {r.strategy_name}
                    <span className="muted"> ({r.strategy_type})</span>
                  </td>
                  <td>{r.timeframe}</td>
                  <td>{r.regime_fit ?? "—"}</td>
                  <td>{r.paper_samples}</td>
                  <td>
                    <strong>{r.score.total}</strong>
                  </td>
                  <td>{bar(r.score.backtest, 30)}</td>
                  <td>{bar(r.score.paper, 40)}</td>
                  <td>{bar(r.score.retrospective, 15)}</td>
                  <td>{bar(r.score.regime, 15)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
