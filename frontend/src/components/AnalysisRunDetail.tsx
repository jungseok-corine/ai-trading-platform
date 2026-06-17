import type { AnalysisRun } from "../types";
import { useSettings } from "../i18n/SettingsContext";
import ModelResponseCard, { ROLE_ORDER } from "./ModelResponseCard";

interface AnalysisRunDetailProps {
  run: AnalysisRun;
}

function statusClass(status: string): string {
  if (status === "succeeded") return "value success";
  if (status === "failed") return "value error";
  return "value muted";
}

export default function AnalysisRunDetail({ run }: AnalysisRunDetailProps) {
  const { t } = useSettings();
  const ta = t.aiAnalysis;

  const sortedResponses = [...run.responses].sort((a, b) => {
    const ai = ROLE_ORDER.indexOf(a.role);
    const bi = ROLE_ORDER.indexOf(b.role);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });

  return (
    <div className="analysis-run-detail">
      <h5>{ta.detailTitle} #{run.id}</h5>

      <div className="run-meta-row">
        <span>
          <span className="label">{ta.detailStatus}:</span>{" "}
          <span className={statusClass(run.status)}>{run.status.toUpperCase()}</span>
        </span>
        <span>
          <span className="label">Mode:</span> <span className="value">{run.mode}</span>
        </span>
        <span>
          <span className="label">{ta.labelProvider}:</span>{" "}
          <span className="value">{run.provider}</span>
        </span>
        {run.secondary_provider && (
          <span>
            <span className="label">{ta.labelSecondaryProvider}:</span>{" "}
            <span className="value">{run.secondary_provider}</span>
          </span>
        )}
        {run.input_hash && (
          <span>
            <span className="label">{ta.detailInputHash}:</span>{" "}
            <code className="hash-value">{run.input_hash.slice(0, 16)}…</code>
          </span>
        )}
      </div>

      {run.error_message && (
        <p className="value error run-error">{ta.detailError}: {run.error_message}</p>
      )}

      {run.warnings && run.warnings.length > 0 && (
        <ul className="run-warnings">
          {run.warnings.map((w, i) => (
            <li key={i} className="muted warn-item">{w}</li>
          ))}
        </ul>
      )}

      <div className="run-responses">
        <h6>{ta.detailResponses} ({sortedResponses.length})</h6>
        {sortedResponses.map((resp, i) => (
          <ModelResponseCard key={resp.id} response={resp} index={i + 1} />
        ))}
      </div>
    </div>
  );
}
