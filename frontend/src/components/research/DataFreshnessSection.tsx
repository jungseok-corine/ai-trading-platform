import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getDataFreshness } from "../../api/research";
import { AutonomousJob, getAutonomousJobs, runAutonomousJob } from "../../api/client";
import { useSettings } from "../../i18n/SettingsContext";

const SOURCE_LABEL: Record<string, string> = {
  market_data: "시세(분봉)", us_market: "미국장 스냅샷", news: "뉴스", dart: "DART 공시",
};

// C-OPS-3.3: freshness source → 이를 갱신하는 자율 잡. 현재 us_market만 지원한다.
// (다른 source는 mapping이 명확하지 않아 이번 작업 범위에서 제외.)
const SOURCE_JOB: Record<string, string> = {
  us_market: "us_market_refresh",
};

function age(hours: number | null): string {
  if (hours === null) return "-";
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.floor(hours / 24)}일 ${Math.round(hours % 24)}시간 전`;
}

export default function DataFreshnessSection() {
  const { formatDateTime } = useSettings();
  const qc = useQueryClient();
  const [msg, setMsg] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["data-freshness"],
    queryFn: getDataFreshness,
  });
  // 기존 autonomous-jobs 쿼리 캐시를 재사용 (AutonomousJobsSection과 동일 키 → 동작 변경 없음).
  const { data: jobs } = useQuery({
    queryKey: ["autonomous-jobs"],
    queryFn: getAutonomousJobs,
  });

  // 수동 갱신: 버튼 클릭 시에만 run-now 호출. page load에서는 외부 API를 호출하지 않는다.
  const refresh = useMutation({
    mutationFn: (jobId: string) => runAutonomousJob(jobId),
    onSuccess: () => {
      setMsg("갱신 요청 완료. 상태를 다시 불러오는 중입니다. 오류가 있으면 아래 '최근 오류'를 확인하세요.");
      qc.invalidateQueries({ queryKey: ["data-freshness"] });
      qc.invalidateQueries({ queryKey: ["autonomous-jobs"] });
    },
    onError: () => setMsg("갱신 요청 실패."),
  });

  const usMarket = data?.sources.find((s) => s.source === "us_market");
  const usJob: AutonomousJob | undefined = jobs?.find(
    (jb) => jb.job_id === SOURCE_JOB["us_market"],
  );

  return (
    <div className="card">
      <h3>데이터 신선도</h3>
      <p className="muted">
        수집 파이프라인이 멈춰 데이터가 늙어가는지 점검합니다. 데이터가 아예 없는 소스(미사용일 수
        있음)는 경보로 보지 않습니다. read-only 점검입니다.
      </p>

      {isLoading && <p className="muted">불러오는 중…</p>}
      {data && (
        <>
          <p className="action-result value">
            {data.stale_count === 0 ? "✅ 모든 소스 최신" : `⚠️ 오래된 소스 ${data.stale_count}개`}
          </p>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr><th>소스</th><th>최신</th><th>경과</th><th>임계</th><th>상태</th></tr>
              </thead>
              <tbody>
                {data.sources.map((s) => (
                  <tr key={s.source}>
                    <td>{SOURCE_LABEL[s.source] ?? s.source}</td>
                    <td>{s.last_at?.slice(0, 16).replace("T", " ") ?? "-"}</td>
                    <td>{age(s.age_hours)}</td>
                    <td>{s.threshold_hours}h</td>
                    <td>{!s.present ? "· 데이터 없음" : s.stale ? "⚠️ 오래됨" : "🟢 최신"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* C-OPS-3.3: 미국장 스냅샷 수동 갱신 경로 (us_market 한정) */}
          {usMarket && (
            <div className="card freshness-job-card">
              <strong>미국장 스냅샷 수동 갱신</strong>
              {usMarket.stale && (
                <p className="value">
                  ⚠️ 미국장 스냅샷이 오래되었습니다. <code>us_market_refresh</code> 작업을 수동으로
                  실행하면 최신 스냅샷을 가져올 수 있습니다.
                </p>
              )}
              <p className="muted">
                관련 작업: <strong>{SOURCE_JOB["us_market"]}</strong>
                {usJob && (
                  <> · {usJob.enabled ? "ON" : "OFF"}{usJob.running ? " · 등록됨" : ""}</>
                )}
              </p>
              <p className="muted">
                마지막 실행: {usJob?.last_run_at ? formatDateTime(usJob.last_run_at) : "-"}
              </p>
              {usJob?.last_error ? (
                <p className="value error">최근 오류: {usJob.last_error}</p>
              ) : (
                <p className="muted">최근 오류: 없음</p>
              )}
              <button
                className="primary"
                disabled={refresh.isPending}
                onClick={() => refresh.mutate(SOURCE_JOB["us_market"])}
              >
                수동 갱신
              </button>
              {msg && <p className="muted">{msg}</p>}
            </div>
          )}
        </>
      )}
    </div>
  );
}
