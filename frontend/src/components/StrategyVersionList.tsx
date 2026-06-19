import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  archiveStrategyVersion,
  deleteStrategyVersion,
  getStrategyVersions,
  updateStrategyVersion,
} from "../api/client";
import { useSettings } from "../i18n/SettingsContext";
import type { StrategyVersion, StrategyVersionStatus } from "../types";
import StrategyVersionCreateForm from "./StrategyVersionCreateForm";
import StrategyVersionEditor from "./StrategyVersionEditor";
import StrategyVersionPerformancePanel from "./StrategyVersionPerformancePanel";
import StrategyAnalysisRunPanel from "./StrategyAnalysisRunPanel";

interface StrategyVersionListProps {
  strategyId: number;
}

const STATUS_OPTIONS: StrategyVersionStatus[] = [
  "draft",
  "testing",
  "active",
  "retired",
  "archived",
];

/** parameters JSONB에서 핵심 식별 필드를 요약해 보여준다 (JSON 전체 덤프 대신). */
function ParamSummary({ parameters }: { parameters: Record<string, unknown> }) {
  const rows: [string, unknown][] = [
    ["strategy_type", parameters.strategy_type],
    ["symbol_code", parameters.symbol_code],
    ["account_id", parameters.account_id],
    ["auto_trade_enabled", parameters.auto_trade_enabled],
  ];
  return (
    <div className="param-summary">
      {rows.map(([key, value]) => (
        <span key={key} className="param-chip">
          <span className="param-chip-key">{key}</span>
          <span
            className={
              key === "auto_trade_enabled"
                ? value
                  ? "param-chip-val danger"
                  : "param-chip-val ok"
                : "param-chip-val"
            }
          >
            {value === undefined || value === null ? "-" : String(value)}
          </span>
        </span>
      ))}
    </div>
  );
}

/** 버전 archive/delete 액션. 삭제 정책 위반(409)은 안내 메시지로 표시한다. */
function VersionActions({ version }: { version: StrategyVersion }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["strategy-versions", version.strategy_id] });

  const archiveMutation = useMutation({
    mutationFn: () => archiveStrategyVersion(version.strategy_id, version.id),
    onSuccess: () => {
      setMessage(null);
      invalidate();
    },
    onError: (e) => setMessage((e as Error)?.message ?? "아카이브 실패"),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteStrategyVersion(version.strategy_id, version.id),
    onSuccess: () => {
      setMessage(null);
      invalidate();
    },
    onError: (e: unknown) => {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (e as Error)?.message;
      setMessage(detail ?? "삭제할 수 없습니다.");
    },
  });

  const busy = archiveMutation.isPending || deleteMutation.isPending;
  const isArchived = version.status === "archived";

  return (
    <div className="version-actions">
      {!isArchived && (
        <button
          disabled={busy}
          onClick={() => {
            if (window.confirm(`버전 #${version.version_no}을 아카이브할까요? (목록에서 숨겨집니다)`)) {
              archiveMutation.mutate();
            }
          }}
        >
          아카이브
        </button>
      )}
      <button
        className="danger"
        disabled={busy}
        onClick={() => {
          if (
            window.confirm(
              `버전 #${version.version_no}을 완전히 삭제할까요?\nDRAFT이고 신호/거래 기록이 없을 때만 가능합니다.`,
            )
          ) {
            deleteMutation.mutate();
          }
        }}
      >
        삭제
      </button>
      {message && <p className="action-result value error">{message}</p>}
    </div>
  );
}

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
  const [analysisVersionId, setAnalysisVersionId] = useState<number | null>(null);
  const [includeArchived, setIncludeArchived] = useState(false);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["strategy-versions", strategyId, includeArchived],
    queryFn: () => getStrategyVersions(strategyId, includeArchived),
  });

  const editingVersion = data?.find((v) => v.id === editingVersionId) ?? null;

  return (
    <div className="card">
      <div className="card-header-row">
        <h3>전략 버전</h3>
        <label className="include-archived-toggle">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
          />
          아카이브 포함
        </label>
      </div>
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
                <th>AI 분석</th>
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
                      <ParamSummary
                        parameters={version.parameters as unknown as Record<string, unknown>}
                      />
                      <details className="parameters-details">
                        <summary>전체 JSON</summary>
                        <pre className="parameters-cell">
                          {JSON.stringify(version.parameters, null, 2)}
                        </pre>
                      </details>
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
                      <VersionActions version={version} />
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
                    <td>
                      <button
                        className="outcome-expand-btn"
                        onClick={() =>
                          setAnalysisVersionId(
                            analysisVersionId === version.id ? null : version.id,
                          )
                        }
                      >
                        {analysisVersionId === version.id
                          ? t.aiAnalysis.btnHideRuns
                          : t.aiAnalysis.sectionTitle}
                      </button>
                    </td>
                  </tr>
                  {performingVersionId === version.id && (
                    <tr className="outcome-panel-row">
                      <td colSpan={12}>
                        <StrategyVersionPerformancePanel
                          strategyId={strategyId}
                          versionId={version.id}
                        />
                      </td>
                    </tr>
                  )}
                  {analysisVersionId === version.id && (
                    <tr className="outcome-panel-row">
                      <td colSpan={12}>
                        <StrategyAnalysisRunPanel
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
