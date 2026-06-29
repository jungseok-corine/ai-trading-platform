import { useQuery } from "@tanstack/react-query";
import { getLeaderTrendCandidates } from "../../api/research";
import type { LeaderTrendCandidateResult } from "../../types/research";

// M2.15E: 주도주(Leader Trend) 리서치 후보 — **읽기 전용 · 매수 신호 아님.**
// 기존 read-only API(GET /leader-trend/candidates)만 소비한다. 주문/거래/제안/영속화 버튼이 없다.

function num(v: number | null, digits = 0): string {
  return v === null || v === undefined ? "-" : v.toLocaleString("ko-KR", {
    maximumFractionDigits: digits,
  });
}

function bucketLabel(b: string): string {
  switch (b) {
    case "A": return "후보 A";
    case "B": return "후보 B";
    case "A_raw_needs_adjusted_review": return "후보 A(검토 필요)";
    case "B_raw_needs_adjusted_review": return "후보 B(검토 필요)";
    case "none": return "해당 없음";
    case "insufficient_data": return "데이터 부족";
    case "invalid_data": return "데이터 이상";
    default: return b;
  }
}

function ResultRow({ r }: { r: LeaderTrendCandidateResult }) {
  return (
    <tr>
      <td><strong>{r.symbol}</strong></td>
      <td>{bucketLabel(r.candidate_bucket_operational)}</td>
      <td>{num(r.current_close)}</td>
      <td>{num(r.high_52w)}</td>
      <td>{num(r.low_52w)}</td>
      <td>{num(r.low_52w_gain_pct, 1)}%</td>
      <td>{num(r.drawdown_from_52w_high_pct, 1)}%</td>
      <td>{num(r.ma20)}</td>
      <td>{num(r.ma50)}</td>
      <td>{r.daily_count}</td>
      <td>{r.is_strategy_extreme ? "⚠️ 고변동(극단)" : "-"}</td>
      <td>{r.operationally_safe_for_classification ? "🟢" : "·"}</td>
    </tr>
  );
}

export default function LeaderTrendSection() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["leader-trend-candidates"],
    queryFn: getLeaderTrendCandidates,
  });

  return (
    <div className="card">
      <h3>주도주 리서치 후보 (읽기 전용)</h3>

      {/* 강한 경고 배너: 매수 신호 아님 + 출처 한계 */}
      <div className="card" style={{ borderLeft: "4px solid #c0392b" }}>
        <p className="value">⚠️ 이 결과는 <strong>매수 신호가 아닙니다(NOT buy signals)</strong>.
          연구용 필터일 뿐이며 주문·진입·거래·추천을 의미하지 않습니다.</p>
        {data && (
          <>
            <p className="muted">안전: {data.safety_warning}</p>
            <p className="muted">출처/한계: {data.provenance_warning}</p>
          </>
        )}
      </div>

      <p className="muted">
        검증된 파일럿 5종(pilot_5)만 스캔합니다. 라이브 시세 호출·DB 쓰기·후보 저장·주문 생성이 없습니다.
      </p>

      {isLoading && <p className="muted">불러오는 중…</p>}
      {isError && (
        <p className="value error">후보를 불러오지 못했습니다. 백엔드 API 상태를 확인하세요.</p>
      )}

      {data && (
        <>
          <p className="action-result value">
            범위 {data.universe_scope} · 스캔 {data.total_symbols_scanned}종 ·
            연구 후보 {data.total_operational_candidates}종
            {data.research_only ? " · research-only" : ""}
          </p>
          {data.results.length === 0 ? (
            <p className="muted">표시할 결과가 없습니다.</p>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>종목</th><th>분류</th><th>현재가</th><th>52주고</th><th>52주저</th>
                    <th>저점대비</th><th>고점낙폭</th><th>MA20</th><th>MA50</th><th>일봉수</th>
                    <th>비고</th><th>운영분류</th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((r) => <ResultRow key={r.symbol} r={r} />)}
                </tbody>
              </table>
            </div>
          )}

          {/* 후보별 경고 상세(읽기 전용 · 행동 버튼 없음) */}
          {data.candidates.map((c) => (
            <div key={c.symbol} className="card" style={{ marginTop: 8 }}>
              <strong>{c.symbol} — {bucketLabel(c.candidate_bucket_operational)} (매수 신호 아님)</strong>
              {c.strategy_extreme_warnings.length > 0 && (
                <p className="muted">전략-극단 경고: {c.strategy_extreme_warnings.join(", ")}</p>
              )}
              {c.adjustment_warnings.length > 0 && (
                <p className="value">조정 의심 경고: {c.adjustment_warnings.join(", ")}</p>
              )}
              {c.hard_errors.length > 0 && (
                <p className="value error">데이터 이상: {c.hard_errors.join(", ")}</p>
              )}
              <p className="muted">기간: {c.oldest_date} ~ {c.newest_date} · 52주 준비:
                {c.ready_for_52w ? " 예" : " 아니오"}</p>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
