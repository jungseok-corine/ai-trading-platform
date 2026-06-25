import { Fragment, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { assignCandidate, getCandidateAnalysis, getCandidates } from "../../api/research";
import type { BucketStat } from "../../types/research";
import CandidateStrategyProposalPanel from "./CandidateStrategyProposalPanel";

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

// by_condition 중 평균수익률이 가장 좋은/나쁜 조건을 뽑는다 (count>0, avg_return_pct 존재).
function bestWorstCondition(byCondition: Record<string, BucketStat>) {
  const entries = Object.entries(byCondition).filter(
    ([, s]) => s.count > 0 && s.avg_return_pct != null,
  );
  if (entries.length === 0) return { best: null, worst: null };
  const sorted = [...entries].sort(
    (a, b) => (b[1].avg_return_pct ?? 0) - (a[1].avg_return_pct ?? 0),
  );
  return { best: sorted[0], worst: sorted[sorted.length - 1] };
}

function fmtPct(v: number | null | undefined) {
  return v == null ? "-" : `${v}%`;
}

export default function CandidatesSection() {
  const queryClient = useQueryClient();
  const [showDetail, setShowDetail] = useState(false);
  // 전략 제안(미리보기) 패널을 펼친 후보 id. 읽기 전용 — 어떤 상태도 저장하지 않는다.
  const [proposalFor, setProposalFor] = useState<number | null>(null);
  const { data, isLoading } = useQuery({ queryKey: ["candidates"], queryFn: () => getCandidates({ limit: 100 }) });
  // 성과 보드는 읽기 전용 집계 — 마운트 시 자동 로드(외부 API 호출 없음, DB 집계만).
  const { data: analysis, isLoading: analysisLoading } = useQuery({
    queryKey: ["candidate-analysis"],
    queryFn: () => getCandidateAnalysis(30),
  });

  const { best, worst } = useMemo(
    () => (analysis ? bestWorstCondition(analysis.by_condition) : { best: null, worst: null }),
    [analysis],
  );

  const assignMut = useMutation({
    mutationFn: (id: number) => assignCandidate(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["assignment-logs"] }),
  });

  return (
    <div className="card">
      <h3>후보 종목 (Candidate Events)</h3>
      <p className="muted">스캐너 룰에 걸린 종목입니다. "왜 후보가 됐는지"가 facts/matched_conditions에 남습니다.</p>

      {/* 성과 보드: 후보 발견이 실제로 유용했는지 한눈에 본다 (읽기 전용). */}
      <div className="card outcome-board" style={{ background: "#f8f9fa" }}>
        <h4 style={{ marginTop: 0 }}>후보 성과 보드 <span className="muted" style={{ fontWeight: 400 }}>(발견 후 30분 forward 수익률)</span></h4>
        {analysisLoading && <p className="muted">집계 중…</p>}
        {analysis && analysis.analyzed === 0 && (
          <p className="muted">
            분석 가능한 후보가 없습니다 (총 {analysis.total}건 중 시세 데이터로 수익률을 계산할 수 있는 후보 없음).
          </p>
        )}
        {analysis && analysis.analyzed > 0 && (
          <>
            <div className="outcome-metrics">
              <span className="metric">
                <span className="metric-label">분석 후보</span>
                <span className="metric-value">{analysis.analyzed}/{analysis.total}건</span>
              </span>
              <span className="metric">
                <span className="metric-label">평균 forward 수익률</span>
                <span className="metric-value">{fmtPct(analysis.overall.avg_return_pct)}</span>
              </span>
              <span className="metric">
                <span className="metric-label">승률(양의 수익 비율)</span>
                <span className="metric-value">{fmtPct(analysis.overall.win_rate)}</span>
              </span>
            </div>
            {(best || worst) && (
              <div className="muted" style={{ fontSize: "0.9em", marginTop: 6 }}>
                {best && (
                  <span>가장 좋은 조건: <strong>{best[0]}</strong> ({fmtPct(best[1].avg_return_pct)}, {best[1].count}건)</span>
                )}
                {best && worst && best[0] !== worst[0] && " · "}
                {worst && worst[0] !== best?.[0] && (
                  <span>가장 나쁜 조건: <strong>{worst[0]}</strong> ({fmtPct(worst[1].avg_return_pct)}, {worst[1].count}건)</span>
                )}
              </div>
            )}
            <div className="form-row" style={{ marginTop: 8 }}>
              <button onClick={() => setShowDetail((v) => !v)}>
                {showDetail ? "조건/시간대 상세 닫기" : "조건/시간대 상세 보기"}
              </button>
            </div>
            {showDetail && (
              <>
                <h4>조건별</h4>
                <StatRows data={analysis.by_condition} />
                <h4>시간대별</h4>
                <StatRows data={analysis.by_time_bucket} />
              </>
            )}
          </>
        )}
      </div>

      {isLoading && <p className="muted">불러오는 중...</p>}
      {data && data.length === 0 && <p className="muted">후보가 없습니다. 스캐너에서 시장 스캔을 실행하세요.</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr><th>ID</th><th>종목</th><th>점수</th><th>매칭 조건</th><th>facts</th><th>발견시각</th><th>다음 단계</th></tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <Fragment key={c.id}>
                  <tr>
                    <td>{c.id}</td>
                    <td>{c.symbol_code}</td>
                    <td>{c.score}</td>
                    <td><code>{(c.matched_conditions ?? []).join(", ")}</code></td>
                    <td><pre className="parameters-cell">{JSON.stringify(c.facts, null, 1)}</pre></td>
                    <td>{new Date(c.triggered_at).toLocaleString()}</td>
                    <td>
                      <button
                        onClick={() => setProposalFor((id) => (id === c.id ? null : c.id))}
                      >
                        {proposalFor === c.id ? "전략 제안 닫기" : "전략 제안 보기"}
                      </button>{" "}
                      <button disabled={assignMut.isPending} onClick={() => assignMut.mutate(c.id)}>
                        전략 배정
                      </button>
                    </td>
                  </tr>
                  {proposalFor === c.id && (
                    <tr>
                      <td colSpan={7}>
                        <CandidateStrategyProposalPanel
                          candidate={c}
                          onClose={() => setProposalFor(null)}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
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
