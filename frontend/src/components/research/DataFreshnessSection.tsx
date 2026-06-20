import { useQuery } from "@tanstack/react-query";
import { getDataFreshness } from "../../api/research";

const SOURCE_LABEL: Record<string, string> = {
  market_data: "시세(분봉)", us_market: "미국장 스냅샷", news: "뉴스", dart: "DART 공시",
};

function age(hours: number | null): string {
  if (hours === null) return "-";
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.floor(hours / 24)}일 ${Math.round(hours % 24)}시간 전`;
}

export default function DataFreshnessSection() {
  const { data, isLoading } = useQuery({
    queryKey: ["data-freshness"],
    queryFn: getDataFreshness,
  });

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
        </>
      )}
    </div>
  );
}
