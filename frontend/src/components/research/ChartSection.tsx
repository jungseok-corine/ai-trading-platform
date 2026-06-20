import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { getChartData } from "../../api/research";
import TradeChart from "./TradeChart";

export default function ChartSection() {
  const [versionId, setVersionId] = useState("");
  const [day, setDay] = useState("");

  const mut = useMutation({
    mutationFn: () => getChartData(Number(versionId), day),
  });

  return (
    <div className="card">
      <h3>매매 차트 (분봉 + 매매 마킹)</h3>
      <p className="muted">
        전략 버전의 그날 분봉 위에 내가 사고/판 지점을 표시합니다. (AI는 텍스트로, 사람은 이 차트로)
      </p>
      <div className="form-row">
        <input placeholder="strategy_version_id" value={versionId}
          onChange={(e) => setVersionId(e.target.value)} />
        <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
        <button className="primary" disabled={!versionId || !day || mut.isPending}
          onClick={() => mut.mutate()}>
          {mut.isPending ? "불러오는 중..." : "차트 보기"}
        </button>
      </div>
      {mut.isError && <p className="value error">불러오기 실패 (버전/날짜 확인)</p>}
      {mut.data && <TradeChart data={mut.data} />}
    </div>
  );
}
