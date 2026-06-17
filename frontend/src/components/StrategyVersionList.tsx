import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getStrategyVersions, updateStrategyVersion } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";
import type { StrategyVersion, StrategyVersionStatus } from "../types";
import StrategyVersionCreateForm from "./StrategyVersionCreateForm";
import StrategyVersionEditor from "./StrategyVersionEditor";
import StrategyVersionPerformancePanel from "./StrategyVersionPerformancePanel";

interface StrategyVersionListProps {
  strategyId: number;
}

const STATUS_OPTIONS: StrategyVersionStatus[] = ["draft", "testing", "active", "retired"];

function StatusSelect({ version }: { version: StrategyVersion }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<StrategyVersionStatus>(version.status);

  const updateMutation = useMutation({
    mutationFn: (next: StrategyVersionStatus) =>
      updateStrategyVersion(version.strategy_id, version.id, { status: next }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strategy-versions", version.strategy_id] });
    },
  });

  return (
    <div className="status-select">
      <select
        value={status}
        onChange={(e) => setStatus(e.target.value as StrategyVersionStatus)}
        disabled={updateMutation.isPending}
      >
        {STATUS_OPTIONS.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      <button
        disabled={updateMutation.isPending || status === version.status}
        onClick={() => updateMutation.mutate(status)}
      >
        적용
      </button>
      {updateMutation.isError && (
        <p className="action-result value error">{(updateMutation.error as Error)?.message ?? "변경 실패"}</p>
      )}
    </div>
  );
}

export default function StrategyVersionList({ strategyId }: StrategyVersionListProps) {
  const { t } = useSettings();
  const [editingVersionId, setEditingVersionId] = useState<number | null>(null);
  const [performingVersionId, setPerformingVersionId] = useState<number | null>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["strategy-versions", strategyId],
    queryFn: () => getStrategyVersions(strategyId),
  });

  const editingVersion = data?.find((v) => v.id === editingVersionId) ?? null;

  return (
    <div className="card">
      <h3>전략 버전</h3>
      {isLoading && <p className="muted">불러오는 중...</p>}
      {isError && <p className="value error">{(error as Error)?.message ?? "조회 실패"}</p>}
      {data && data.length === 0 && <p className="muted">생성된 버전이 없습니다.</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>버전</th>
                <th>Status</th>
                <th>Parameters</th>
                <th>Win Rate</th>
                <th>Avg Profit</th>
                <th>Avg Loss</th>
                <th>MDD</th>
                <th>Updated At</th>
                <th>Actions</th>
                <th>성과</th>
              </tr>
            </thead>
            <tbody>
              {data.map((version) => (
                <React.Fragment key={version.id}>
                  <tr>
                    <td>{version.id}</td>
                    <td>{version.version_no}</td>
                    <td>
                      <StatusSelect version={version} />
                    </td>
                    <td>
                      <pre className="parameters-cell">{JSON.stringify(version.parameters, null, 2)}</pre>
                    </td>
                    <td>{version.win_rate ?? "-"}</td>
                    <td>{version.avg_profit ?? "-"}</td>
                    <td>{version.avg_loss ?? "-"}</td>
                    <td>{version.mdd ?? "-"}</td>
                    <td>{version.updated_at}</td>
                    <td>
                      <button
                        onClick={() =>
                          setEditingVersionId(editingVersionId === version.id ? null : version.id)
                        }
                      >
                        {editingVersionId === version.id ? "닫기" : "편집"}
                      </button>
                    </td>
                    <td>
                      <button
                        className="outcome-expand-btn"
                        onClick={() =>
                          setPerformingVersionId(
                            performingVersionId === version.id ? null : version.id,
                          )
                        }
                      >
                        {performingVersionId === version.id
                          ? t.performance.hidePerformance
                          : t.performance.showPerformance}
                      </button>
                    </td>
                  </tr>
                  {performingVersionId === version.id && (
                    <tr className="outcome-panel-row">
                      <td colSpan={11}>
                        <StrategyVersionPerformancePanel
                          strategyId={strategyId}
                          versionId={version.id}
                        />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editingVersion && (
        <StrategyVersionEditor version={editingVersion} onClose={() => setEditingVersionId(null)} />
      )}

      <StrategyVersionCreateForm strategyId={strategyId} />
    </div>
  );
}
