import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { assignCandidate, getCandidateAnalysis, getCandidates } from "../../api/research";
import type { BucketStat } from "../../types/research";

function StatRows({ data }: { data: Record<string, BucketStat> }) {
  const keys = Object.keys(data);
  if (keys.length === 0) return <p className="muted">데이터 없음</p>;
  return (
    <table>
      <thead><tr><th>구분</th><th>개수</th><th>승률%</th><th>평균수익%</th></tr></thead>
      <tbody>
        {keys.map((k) => (
          <tr key={k}>
            <td>{k}</td>
            <td>{data[k].count}</td>
            <td>{data[k].win_rate ?? "-"}</td>
            <td>{data[k].avg_return_pct ?? "-"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function CandidatesSection() {
  const queryClient = useQueryClient();
  const [showAnalysis, setShowAnalysis] = useState(false);
  const { data, isLoading } = useQuery({ queryKey: ["candidates"], queryFn: () => getCandidates({ limit: 100 }) });
  const { data: analysis } = useQuery({
    queryKey: ["candidate-analysis"],
    queryFn: () => getCandidateAnalysis(30),
    enabled: showAnalysis,
  });

  const assignMut = useMutation({
    mutationFn: (id: number) => assignCandidate(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["assignment-logs"] }),
  });

  return (
    <div className="card">
      <h3>후보 종목 (Candidate Events)</h3>
      <p className="muted">스캐너 룰에 걸린 종목입니다. "왜 후보가 됐는지"가 facts/matched_conditions에 남습니다.</p>

      <div className="form-row">
        <button onClick={() => setShowAnalysis((v) => !v)}>
          {showAnalysis ? "성과 분석 닫기" : "성과 분석 (30분 후 수익률)"}
        </button>
      </div>
      {showAnalysis && analysis && (
        <div className="card" style={{ background: "#f8f9fa" }}>
          <strong>
            전체: {analysis.analyzed}/{analysis.total}건 분석 · 승률 {analysis.overall.win_rate ?? "-"}% · 평균 {analysis.overall.avg_return_pct ?? "-"}%
          </strong>
          <h4>조건별</h4>
          <StatRows data={analysis.by_condition} />
          <h4>시간대별</h4>
          <StatRows data={analysis.by_time_bucket} />
        </div>
      )}
      {isLoading && <p className="muted">불러오는 중...</p>}
      {data && data.length === 0 && <p className="muted">후보가 없습니다. 스캐너에서 시장 스캔을 실행하세요.</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr><th>ID</th><th>종목</th><th>점수</th><th>매칭 조건</th><th>facts</th><th>발견시각</th><th>배정</th></tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id}>
                  <td>{c.id}</td>
                  <td>{c.symbol_code}</td>
                  <td>{c.score}</td>
                  <td><code>{(c.matched_conditions ?? []).join(", ")}</code></td>
                  <td><pre className="parameters-cell">{JSON.stringify(c.facts, null, 1)}</pre></td>
                  <td>{new Date(c.triggered_at).toLocaleString()}</td>
                  <td>
                    <button disabled={assignMut.isPending} onClick={() => assignMut.mutate(c.id)}>
                      전략 배정
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {assignMut.isSuccess && (
        <p className="action-result value">
          {assignMut.data ? `전략 배정됨: ${assignMut.data.strategy_type}` : "매칭되는 배정 규칙이 없습니다."}
        </p>
      )}
    </div>
  );
}
