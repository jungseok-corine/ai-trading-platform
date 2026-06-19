import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createNews, getNews, getUsSnapshots, refreshUsSnapshot, upsertUsSnapshot } from "../../api/research";

export default function MarketContextSection() {
  const queryClient = useQueryClient();
  const [headline, setHeadline] = useState("");
  const [symbol, setSymbol] = useState("");
  const [sentiment, setSentiment] = useState<"positive" | "neutral" | "negative">("neutral");

  const [usDate, setUsDate] = useState("");
  const [nasdaq, setNasdaq] = useState("");

  const { data: news } = useQuery({ queryKey: ["news"], queryFn: () => getNews() });
  const { data: usSnaps } = useQuery({ queryKey: ["us-snapshots"], queryFn: getUsSnapshots });

  const newsMut = useMutation({
    mutationFn: () =>
      createNews({
        headline,
        published_at: new Date().toISOString(),
        symbol_code: symbol || null,
        sentiment,
      }),
    onSuccess: () => {
      setHeadline("");
      setSymbol("");
      queryClient.invalidateQueries({ queryKey: ["news"] });
    },
  });
  const usMut = useMutation({
    mutationFn: () => upsertUsSnapshot({ session_date: usDate, nasdaq_change_pct: nasdaq || null }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["us-snapshots"] }),
  });
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null);
  const refreshMut = useMutation({
    mutationFn: () => refreshUsSnapshot(),
    onSuccess: (r) => {
      setRefreshMsg(
        r.updated
          ? `provider(${r.provider})에서 ${r.session_date} 스냅샷 수집됨.`
          : `provider(${r.provider}): 수집할 데이터 없음 (${r.reason ?? "manual 모드"}).`,
      );
      queryClient.invalidateQueries({ queryKey: ["us-snapshots"] });
    },
  });

  return (
    <div className="card">
      <h3>시장 맥락 (뉴스 / 미국장)</h3>
      <p className="muted">뉴스·미국장 흐름을 기록해 전략 분석 맥락으로 사용합니다.</p>

      <div className="card" style={{ background: "#f8f9fa" }}>
        <strong>뉴스 등록</strong>
        <div className="form-row">
          <input placeholder="헤드라인" value={headline} onChange={(e) => setHeadline(e.target.value)} style={{ minWidth: 240 }} />
          <input placeholder="종목코드(선택)" value={symbol} onChange={(e) => setSymbol(e.target.value)} style={{ width: 140 }} />
          <select value={sentiment} onChange={(e) => setSentiment(e.target.value as typeof sentiment)}>
            <option value="positive">positive</option>
            <option value="neutral">neutral</option>
            <option value="negative">negative</option>
          </select>
          <button className="primary" disabled={!headline || newsMut.isPending} onClick={() => newsMut.mutate()}>등록</button>
        </div>
      </div>

      {news && news.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead><tr><th>종목</th><th>헤드라인</th><th>감성</th><th>시각</th></tr></thead>
            <tbody>
              {news.slice(0, 20).map((n) => (
                <tr key={n.id}>
                  <td>{n.symbol_code ?? "시장"}</td><td>{n.headline}</td><td>{n.sentiment ?? "-"}</td>
                  <td>{new Date(n.published_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card" style={{ background: "#f8f9fa" }}>
        <strong>미국장 스냅샷 (일별)</strong>
        <div className="form-row">
          <input type="date" value={usDate} onChange={(e) => setUsDate(e.target.value)} />
          <input placeholder="나스닥 변화율%" value={nasdaq} onChange={(e) => setNasdaq(e.target.value)} style={{ width: 140 }} />
          <button className="primary" disabled={!usDate || usMut.isPending} onClick={() => usMut.mutate()}>저장</button>
          <button disabled={refreshMut.isPending} onClick={() => refreshMut.mutate()}>provider로 수집</button>
        </div>
        <p className="muted">
          기본 provider는 "manual"(외부 호출 없음). API 키를 설정하고 벤더 어댑터를 붙이면 자동 수집됩니다.
        </p>
        {refreshMsg && <p className="action-result value">{refreshMsg}</p>}
      </div>
      {usSnaps && usSnaps.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead><tr><th>날짜</th><th>나스닥%</th><th>SOX%</th></tr></thead>
            <tbody>
              {usSnaps.map((s) => (
                <tr key={s.id}><td>{s.session_date}</td><td>{s.nasdaq_change_pct ?? "-"}</td><td>{s.sox_change_pct ?? "-"}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
