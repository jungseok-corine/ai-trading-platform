import { useQuery } from "@tanstack/react-query";
import { getSchedulerRuns } from "../api/client";
import type { SchedulerRunErrorEntry, SchedulerRunSummary } from "../types";

const ERROR_CATEGORY_LABELS: Record<string, string> = {
  invalid_price_tick: "주문 가격이 호가 단위에 맞지 않아 거절됨",
  token_error: "인증 토큰 오류",
  rate_limit_or_repeated_call: "API 호출 빈도 제한",
  market_closed: "장 운영시간 외 요청",
  insufficient_balance: "잔고/예수금 부족",
  unknown: "분류되지 않은 오류",
};

function describeCategory(category: string | null): string | null {
  if (!category) return null;
  return ERROR_CATEGORY_LABELS[category] ?? category;
}

function SummaryCounts({ summary }: { summary: SchedulerRunSummary }) {
  const counts = Object.entries(summary).filter(([key]) => key !== "errors");
  if (counts.length === 0) return null;
  return (
    <div className="muted">
      {counts.map(([key, value]) => `${key}: ${String(value)}`).join(", ")}
    </div>
  );
}

function ErrorList({ errors }: { errors: SchedulerRunErrorEntry[] }) {
  if (errors.length === 0) return null;
  return (
    <ul className="scheduler-error-list">
      {errors.map((err, idx) => (
        <li key={idx}>
          {err.symbol_code && <span className="muted">[{err.symbol_code}] </span>}
          {err.category && (
            <span className="value error">{describeCategory(err.category)}</span>
          )}
          <div className="muted">{err.message}</div>
        </li>
      ))}
    </ul>
  );
}

export default function SchedulerRunsCard() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["scheduler-runs"],
    queryFn: () => getSchedulerRuns(20),
  });

  return (
    <div className="card">
      <h2>Scheduler Logs</h2>
      <p className="section-description">
        strategy_runner/order_sync 같은 자동 작업이 언제 실행됐고 성공/실패했는지 기록합니다.
      </p>
      {isLoading && <p className="muted">불러오는 중...</p>}
      {isError && <p className="value error">{(error as Error)?.message ?? "조회 실패"}</p>}
      {data && data.length === 0 && <p className="muted">실행 기록이 없습니다.</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Job</th>
                <th>Status</th>
                <th>Started At</th>
                <th>Duration (ms)</th>
                <th>Errors</th>
                <th>Summary</th>
              </tr>
            </thead>
            <tbody>
              {data.map((run) => (
                <tr key={run.id}>
                  <td>{run.job_id}</td>
                  <td>
                    <span className={`value ${run.status === "failed" ? "error" : "ok"}`}>{run.status}</span>
                  </td>
                  <td>{run.started_at}</td>
                  <td>{run.duration_ms ?? "-"}</td>
                  <td>
                    {run.summary?.errors && run.summary.errors.length > 0 ? (
                      <ErrorList errors={run.summary.errors} />
                    ) : (
                      "-"
                    )}
                  </td>
                  <td>{run.summary ? <SummaryCounts summary={run.summary} /> : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
