import { useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { getStrategies, getStrategyVersions } from "../api/client";
import StrategyList from "../components/StrategyList";
import StrategyOverviewTable from "../components/StrategyOverviewTable";
import StrategyVersionList from "../components/StrategyVersionList";

export default function StrategiesPage() {
  const [selectedStrategyId, setSelectedStrategyId] = useState<number | null>(null);

  const { data: strategies } = useQuery({
    queryKey: ["strategies"],
    queryFn: getStrategies,
  });

  const versionQueries = useQueries({
    queries: (strategies ?? []).map((strategy) => ({
      queryKey: ["strategy-versions", strategy.id],
      queryFn: () => getStrategyVersions(strategy.id),
    })),
  });

  const activeVersionCount = versionQueries.reduce((count, query) => {
    const versions = query.data ?? [];
    return count + versions.filter((v) => v.status === "active").length;
  }, 0);

  return (
    <div className="app">
      <h1>전략 관리</h1>

      {activeVersionCount > 1 && (
        <div className="card warning-banner">
          현재 status가 active인 전략 버전이 {activeVersionCount}개입니다. 여러 전략 버전이 동시에
          active 상태이면 자동매매 시 의도치 않은 중복 주문이 발생할 수 있습니다. 운영 전 확인하세요.
        </div>
      )}

      <StrategyOverviewTable onSelect={setSelectedStrategyId} />

      <StrategyList selectedStrategyId={selectedStrategyId} onSelect={setSelectedStrategyId} />

      {selectedStrategyId !== null && <StrategyVersionList strategyId={selectedStrategyId} />}
    </div>
  );
}
