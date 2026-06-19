import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { generateDailyReport, getDailyReports } from "../../api/research";

export default function ReportsSection() {
  const queryClient = useQueryClient();
  const [date, setDate] = useState("");

  const { data, isLoading } = useQuery({ queryKey: ["daily-reports"], queryFn: getDailyReports });
  const genMut = useMutation({
    mutationFn: () => generateDailyReport(date || undefined),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["daily-reports"] }),
  });

  return (
    <div className="card">
      <h3>일일 리서치 리포트</h3>
      <p className="muted">매일 장마감 후 신호/체결/후보/전략 활동을 집계합니다 (수동 생성도 가능).</p>
      <div className="form-row">
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <button className="primary" disabled={genMut.isPending} onClick={() => genMut.mutate()}>
          리포트 생성 (기본 오늘)
        </button>
      </div>
      {isLoading && <p className="muted">불러오는 중...</p>}
      {data && data.length === 0 && <p className="muted">리포트가 없습니다.</p>}
      {data && data.map((r) => (
        <div key={r.id} className="card" style={{ background: "#f8f9fa" }}>
          <strong>{r.report_date} ({r.market})</strong>
          <p>{r.summary}</p>
          <details>
            <summary className="muted">집계 상세 (JSON)</summary>
            <pre className="parameters-cell">{JSON.stringify(r.sections, null, 2)}</pre>
          </details>
        </div>
      ))}
    </div>
  );
}
