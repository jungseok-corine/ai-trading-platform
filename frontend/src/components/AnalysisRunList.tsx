import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getStrategyAnalysisRuns } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";
import AnalysisRunDetail from "./AnalysisRunDetail";

interface AnalysisRunListProps {
  strategyId: number;
  versionId: number;
}

function statusClass(status: string): string {
  if (status === "succeeded") return "value success";
  if (status === "failed") return "value error";
  return "value muted";
}

export default function AnalysisRunList({ strategyId, versionId }: AnalysisRunListProps) {
  const { t } = useSettings();
  const ta = t.aiAnalysis;
  const [expandedRunId, setExpandedRunId] = useState<number | null>(null);

  const { data, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ["analysis-runs", strategyId, versionId],
    queryFn: () => getStrategyAnalysisRuns(strategyId, versionId),
    retry: false,
  });

  const refreshBtn = (
    <button
      className="outcome-refresh-btn"
      onClick={() => refetch()}
      disabled={isFetching}
    >
      {isFetching ? "..." : ta.btnRefresh}
    </button>
  );

  if (isLoading) return <p className="muted">{ta.runListLoading}</p>;
  if (isError) return (
    <div className="analysis-run-list">
      <p className="value error">{ta.loadError}</p>
      {refreshBtn}
    </div>
  );

  return (
    <div className="analysis-run-list">
      <div className="run-list-header">
        <h5>{ta.runListTitle}</h5>
        {refreshBtn}
      </div>

      {(!data || data.length === 0) && (
        <p className="muted">{ta.runListEmpty}</p>
      )}

      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table className="run-list-table">
            <thead>
              <tr>
                <th>{ta.colRunId}</th>
                <th>{ta.colMode}</th>
                <th>{ta.colStatus}</th>
                <th>{ta.colProvider}</th>
                <th>{ta.colPromptType}</th>
                <th>{ta.colCreatedAt}</th>
                <th>{ta.colActions}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((run) => (
                <React.Fragment key={run.id}>
                  <tr>
                    <td>{run.id}</td>
                    <td>{run.mode}</td>
                    <td>
                      <span className={statusClass(run.status)}>
                        {run.status}
                      </span>
                    </td>
                    <td>
                      {run.provider}
                      {run.secondary_provider ? ` + ${run.secondary_provider}` : ""}
                    </td>
                    <td>{run.prompt_type}</td>
                    <td>{new Date(run.created_at).toLocaleString()}</td>
                    <td>
                      <button
                        onClick={() =>
                          setExpandedRunId(expandedRunId === run.id ? null : run.id)
                        }
                      >
                        {expandedRunId === run.id ? ta.btnHideDetail : ta.btnDetail}
                      </button>
                    </td>
                  </tr>
                  {expandedRunId === run.id && (
                    <tr className="run-detail-row">
                      <td colSpan={7}>
                        <AnalysisRunDetail run={run} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
