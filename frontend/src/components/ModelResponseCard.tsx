import type { AIModelResponse } from "../types";
import { useSettings } from "../i18n/SettingsContext";

interface ModelResponseCardProps {
  response: AIModelResponse;
  index: number;
}

const ROLE_ORDER = [
  "primary_analysis",
  "secondary_analysis",
  "primary_critique",
  "secondary_critique",
  "synthesis",
];

function roleLabel(role: string): string {
  const labels: Record<string, string> = {
    primary_analysis: "Primary Analysis",
    secondary_analysis: "Secondary Analysis",
    primary_critique: "Primary Critique",
    secondary_critique: "Secondary Critique",
    synthesis: "Synthesis",
  };
  return labels[role] ?? role;
}

function roleBadgeClass(role: string): string {
  if (role === "synthesis") return "role-badge synthesis";
  if (role.includes("critique")) return "role-badge critique";
  return "role-badge analysis";
}

export default function ModelResponseCard({ response, index }: ModelResponseCardProps) {
  const { t } = useSettings();
  const ta = t.aiAnalysis;
  const isError = !!response.error_message;
  const isTruncated = response.finish_reason === "length";

  return (
    <div className={`model-response-card ${isError ? "response-error" : ""}`}>
      <div className="response-header">
        <span className="response-index">{index}</span>
        <span className={roleBadgeClass(response.role)}>{roleLabel(response.role)}</span>
        <span className="response-provider">{response.provider} / {response.model}</span>
      </div>

      {isTruncated && !isError && (
        <p className="warn-truncated">{ta.lengthWarningImpact(roleLabel(response.role))}</p>
      )}

      {isError ? (
        <div className="response-error-body">
          <span className="label">{ta.errorLabel}:</span>
          <span className="value error">{response.error_message}</span>
        </div>
      ) : (
        <div className="response-meta">
          <span>
            <span className="label">{ta.finishLabel}:</span>{" "}
            <span className={isTruncated ? "value error" : "value"}>
              {response.finish_reason ?? "-"}
            </span>
          </span>
          {response.total_tokens != null && (
            <span>
              <span className="label">{ta.tokensLabel}:</span>{" "}
              <span className="value">
                {response.prompt_tokens ?? 0} in / {response.completion_tokens ?? 0} out /{" "}
                {response.total_tokens} total
              </span>
            </span>
          )}
          {response.latency_ms != null && (
            <span>
              <span className="label">{ta.latencyLabel}:</span>{" "}
              <span className="value">{(response.latency_ms / 1000).toFixed(1)}s</span>
            </span>
          )}
        </div>
      )}

      {response.content && (
        <details className="response-content-details">
          <summary>{ta.contentLabel}</summary>
          <pre className="response-content">{response.content}</pre>
        </details>
      )}
    </div>
  );
}

export { ROLE_ORDER, roleLabel };
