// Action Inbox: 검토가 필요한 항목을 한곳에 모아 보여준다 (읽기 전용).
// 승인/거절·잡 토글·실행 버튼 없음 — 조치는 각 전용 화면에서 사람만 한다.
// v2: 항목을 해당 전용 섹션으로 '이동'만 가능(네비게이션 전용, 상태 변경 없음).
import { useQuery } from "@tanstack/react-query";
import { getActionInbox } from "../../api/research";
import { useSettings } from "../../i18n/SettingsContext";

// related_url "research:<section>" → ResearchPage 섹션 키. 실제 존재하는 섹션만 이동 허용.
const NAVIGABLE_SECTIONS = new Set([
  "proposals",
  "scanner-proposals",
  "autonomous-jobs",
  "freshness",
  "ops",
  "promotion-readiness",
  "candidates",
]);

function targetSection(relatedUrl: string | null): string | null {
  if (!relatedUrl || !relatedUrl.startsWith("research:")) return null;
  const key = relatedUrl.slice("research:".length);
  return NAVIGABLE_SECTIONS.has(key) ? key : null;
}

interface Props {
  // 부모(ResearchPage)가 해당 섹션으로 전환. 네비게이션 전용 — 어떤 상태도 바꾸지 않는다.
  onNavigate?: (section: string) => void;
}

export default function ActionInboxSection({ onNavigate }: Props) {
  const { formatDateTime } = useSettings();
  const { data, isLoading } = useQuery({
    queryKey: ["action-inbox"],
    queryFn: getActionInbox,
  });

  return (
    <div className="card">
      <h3>액션 인박스 (검토 대기)</h3>
      <p className="muted">
        검토가 필요한 항목을 한곳에 모았습니다. 읽기 전용 — 승인·실행은 각 전용 화면에서 사람만
        합니다. (v1)
      </p>

      {isLoading && <p className="muted">불러오는 중…</p>}
      {data && (
        <>
          <p className="action-result value">
            {data.counts.total === 0
              ? "✅ 검토 대기 항목 없음"
              : `검토 대기 ${data.counts.total}건 (긴급 ${data.counts.alert} · 확인 ${data.counts.attention})`}
          </p>

          {data.items.length > 0 && (
            <ul className="inbox-list">
              {data.items.map((it) => {
                const target = targetSection(it.related_url);
                return (
                  <li key={it.id} className={`inbox-item inbox-${it.severity}`}>
                    <strong>
                      {it.severity === "alert" ? "‼️" : "•"} {it.title}
                    </strong>
                    <div className="muted" style={{ fontSize: "0.88em" }}>
                      {it.description}
                    </div>
                    <div className="muted" style={{ fontSize: "0.78em" }}>
                      출처: {it.source}
                      {target && onNavigate && (
                        <button
                          className="link-button"
                          style={{ marginLeft: 8 }}
                          onClick={() => onNavigate(target)}
                        >
                          보기 →
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <p className="muted" style={{ fontSize: "0.85em" }}>
            기준 시각: {formatDateTime(data.generated_at)}
          </p>
        </>
      )}
    </div>
  );
}
