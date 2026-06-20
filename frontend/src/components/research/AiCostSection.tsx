import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAiCostSummary } from "../../api/research";

const DAY_OPTIONS = [7, 30, 90];

function usd(n: number): string {
  return `$${n.toFixed(n < 1 ? 4 : 2)}`;
}

function num(n: number): string {
  return n.toLocaleString();
}

export default function AiCostSection() {
  const [days, setDays] = useState(30);
  const { data, isLoading } = useQuery({
    queryKey: ["ai-cost", days],
    queryFn: () => getAiCostSummary(days),
  });

  return (
    <div className="card">
      <h3>AI 비용·사용량 (비용 가드)</h3>
      <p className="muted">
        AI 분석 호출의 토큰 사용량과 추정 비용입니다. 단가는 추정치이며, 단가 미상 모델은
        비용 0으로 표시되니 토큰량으로 함께 판단하세요. read-only 집계입니다.
      </p>
      <div className="sub-nav">
        {DAY_OPTIONS.map((d) => (
          <button key={d} className={days === d ? "primary" : undefined}
            onClick={() => setDays(d)}>
            최근 {d}일
          </button>
        ))}
      </div>

      {isLoading && <p className="muted">불러오는 중…</p>}
      {data && (
        <>
          <p className="action-result value">
            총 호출 {num(data.total.responses)}건 · 토큰 {num(data.total.total_tokens)} ·
            추정비용 <strong>{usd(data.total.est_cost_usd)}</strong>
          </p>
          {data.unpriced_models.length > 0 && (
            <p className="muted">⚠️ 단가 미상(비용 0 처리): {data.unpriced_models.join(", ")}</p>
          )}

          <h4>모델별</h4>
          {data.by_model.length === 0 ? (
            <p className="muted">기간 내 AI 호출 기록이 없습니다.</p>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>provider</th><th>model</th><th>호출</th>
                    <th>입력토큰</th><th>출력토큰</th><th>추정비용</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_model.map((m) => (
                    <tr key={`${m.provider}/${m.model}`}>
                      <td>{m.provider}</td>
                      <td>{m.model}{m.priced ? "" : " (단가 미상)"}</td>
                      <td>{num(m.responses)}</td>
                      <td>{num(m.prompt_tokens)}</td>
                      <td>{num(m.completion_tokens)}</td>
                      <td>{usd(m.est_cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h4>일자별</h4>
          {data.by_day.length === 0 ? (
            <p className="muted">기간 내 기록이 없습니다.</p>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr><th>날짜</th><th>호출</th><th>토큰</th><th>추정비용</th></tr>
                </thead>
                <tbody>
                  {data.by_day.map((d) => (
                    <tr key={d.date}>
                      <td>{d.date}</td>
                      <td>{num(d.responses)}</td>
                      <td>{num(d.total_tokens)}</td>
                      <td>{usd(d.est_cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
