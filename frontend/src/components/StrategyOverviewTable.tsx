// C-6.19: 전략 분류 요약 — "뭐가 살아 있고, 뭐가 신호를 내고, 뭐가 자동매매 중인가"를
// 한 표로. 전량 아카이브된 전략은 기본 숨김(토글로 표시) — 삭제 없이 정리.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getStrategiesOverview } from "../api/client";

export default function StrategyOverviewTable({
  onSelect,
}: {
  onSelect: (id: number) => void;
}) {
  const [showArchived, setShowArchived] = useState(false);
  const { data } = useQuery({
    queryKey: ["strategies-overview"],
    queryFn: getStrategiesOverview,
    refetchInterval: 60_000,
  });

  if (!data) return null;
  const live = data.filter((s) => s.live_versions > 0);
  const archived = data.filter((s) => s.live_versions === 0);
  const rows = showArchived ? data : live;

  return (
    <div className="card">
      <h3>전략 분류 요약</h3>
      <p className="muted">
        🟢 신호 발생 중(3일) · 🤖 자동매매 · 💤 휴면(살아있지만 신호 없음). 전량 아카이브된
        전략 {archived.length}개는 기본 숨김.
      </p>
      <table className="compact-table" style={{ width: "100%" }}>
        <thead>
          <tr>
            <th>전략</th>
            <th>상태</th>
            <th>버전(살아있음/전체)</th>
            <th>분봉</th>
            <th>신호(3일)</th>
            <th>마지막 신호</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => {
            const dormant = s.live_versions > 0 && s.signals_3d === 0;
            return (
              <tr
                key={s.id}
                style={{ cursor: "pointer", opacity: s.live_versions === 0 ? 0.5 : 1 }}
                onClick={() => onSelect(s.id)}
              >
                <td style={{ textAlign: "left" }}>
                  #{s.id} {s.name}
                </td>
                <td style={{ textAlign: "left" }}>
                  {s.live_versions === 0 && "📦 아카이브"}
                  {s.auto_trade && "🤖 자동매매 "}
                  {s.signals_3d > 0 && "🟢 신호 발생 중"}
                  {dormant && "💤 휴면"}
                </td>
                <td>
                  {s.live_versions}/{s.versions_total}{" "}
                  <span className="muted">({s.live_statuses.join(",")})</span>
                </td>
                <td>{s.timeframes.join(",") || "—"}</td>
                <td>{s.signals_3d.toLocaleString()}</td>
                <td className="muted">
                  {s.last_signal_at
                    ? new Date(s.last_signal_at).toLocaleString("ko-KR", {
                        month: "numeric",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {archived.length > 0 && (
        <button onClick={() => setShowArchived(!showArchived)}>
          {showArchived ? "아카이브 전략 숨기기" : `아카이브 전략 ${archived.length}개 보기`}
        </button>
      )}
    </div>
  );
}
