import { useQuery } from "@tanstack/react-query";
import { getStrategies } from "../api/client";
import StrategyCreateForm from "./StrategyCreateForm";

interface StrategyListProps {
  selectedStrategyId: number | null;
  onSelect: (strategyId: number) => void;
}

export default function StrategyList({ selectedStrategyId, onSelect }: StrategyListProps) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["strategies"],
    queryFn: getStrategies,
  });

  return (
    <div className="card">
      <h2>전략 목록</h2>
      {isLoading && <p className="muted">불러오는 중...</p>}
      {isError && <p className="value error">{(error as Error)?.message ?? "조회 실패"}</p>}
      {data && data.length === 0 && <p className="muted">생성된 전략이 없습니다.</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th></th>
                <th>ID</th>
                <th>이름</th>
                <th>설명</th>
                <th>생성일</th>
                <th>버전 수</th>
              </tr>
            </thead>
            <tbody>
              {data.map((strategy) => (
                <tr
                  key={strategy.id}
                  className={strategy.id === selectedStrategyId ? "selected" : undefined}
                  onClick={() => onSelect(strategy.id)}
                  style={{ cursor: "pointer" }}
                >
                  <td>
                    <input
                      type="radio"
                      checked={strategy.id === selectedStrategyId}
                      onChange={() => onSelect(strategy.id)}
                    />
                  </td>
                  <td>{strategy.id}</td>
                  <td>{strategy.name}</td>
                  <td>{strategy.description ?? "-"}</td>
                  <td>{strategy.created_at}</td>
                  <td>{strategy.version_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <StrategyCreateForm />
    </div>
  );
}
