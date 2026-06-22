import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getStrategies, updateStrategy } from "../api/client";
import StrategyCreateForm from "./StrategyCreateForm";

interface StrategyListProps {
  selectedStrategyId: number | null;
  onSelect: (strategyId: number) => void;
}

export default function StrategyList({ selectedStrategyId, onSelect }: StrategyListProps) {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["strategies"],
    queryFn: getStrategies,
  });

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");

  const updateMutation = useMutation({
    mutationFn: (vars: { id: number; name: string; description: string }) =>
      updateStrategy(vars.id, { name: vars.name.trim(), description: vars.description.trim() || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
      setEditingId(null);
    },
  });

  const startEdit = (id: number, name: string, description: string | null) => {
    setEditingId(id);
    setEditName(name);
    setEditDesc(description ?? "");
  };

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
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              {data.map((strategy) => {
                const isEditing = strategy.id === editingId;
                return (
                  <tr
                    key={strategy.id}
                    className={strategy.id === selectedStrategyId ? "selected" : undefined}
                    onClick={() => !isEditing && onSelect(strategy.id)}
                    style={{ cursor: isEditing ? "default" : "pointer" }}
                  >
                    <td>
                      <input
                        type="radio"
                        checked={strategy.id === selectedStrategyId}
                        onChange={() => onSelect(strategy.id)}
                      />
                    </td>
                    <td>{strategy.id}</td>
                    <td>
                      {isEditing ? (
                        <input
                          type="text"
                          value={editName}
                          onClick={(e) => e.stopPropagation()}
                          onChange={(e) => setEditName(e.target.value)}
                          style={{ width: "100%" }}
                        />
                      ) : (
                        strategy.name
                      )}
                    </td>
                    <td>
                      {isEditing ? (
                        <input
                          type="text"
                          value={editDesc}
                          onClick={(e) => e.stopPropagation()}
                          onChange={(e) => setEditDesc(e.target.value)}
                          style={{ width: "100%" }}
                        />
                      ) : (
                        strategy.description ?? "-"
                      )}
                    </td>
                    <td>{strategy.created_at}</td>
                    <td>{strategy.version_count}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {isEditing ? (
                        <div className="actions">
                          <button
                            className="primary"
                            disabled={!editName.trim() || updateMutation.isPending}
                            onClick={() =>
                              updateMutation.mutate({ id: strategy.id, name: editName, description: editDesc })
                            }
                          >
                            저장
                          </button>
                          <button disabled={updateMutation.isPending} onClick={() => setEditingId(null)}>
                            취소
                          </button>
                        </div>
                      ) : (
                        <button onClick={() => startEdit(strategy.id, strategy.name, strategy.description)}>
                          수정
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {updateMutation.isError && (
        <p className="value error">{(updateMutation.error as Error)?.message ?? "수정 실패"}</p>
      )}

      <StrategyCreateForm />
    </div>
  );
}
