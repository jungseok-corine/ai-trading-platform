import { useQuery } from "@tanstack/react-query";
import { getAIProviderStatuses } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";
import type { AIProviderStatus } from "../types";

function statusClass(status: AIProviderStatus): string {
  if (status === "available") return "provider-status available";
  if (status === "missing_config") return "provider-status missing";
  return "provider-status not-impl";
}

export default function AIProviderStatusPanel() {
  const { t } = useSettings();
  const ta = t.aiAnalysis;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["ai-provider-statuses"],
    queryFn: getAIProviderStatuses,
    staleTime: 60_000,
  });

  if (isLoading) return <p className="muted">{t.common.loading}</p>;
  if (isError) return <p className="value error">{ta.loadError}</p>;
  if (!data) return null;

  const labelFor = (status: AIProviderStatus) => {
    if (status === "available") return ta.statusAvailable;
    if (status === "missing_config") return ta.statusMissingConfig;
    return ta.statusNotImplemented;
  };

  return (
    <div className="ai-provider-status-panel">
      <h5>{ta.providerTitle}</h5>
      <div className="provider-status-list">
        {data.map((p) => (
          <span key={p.provider} className={statusClass(p.status)}>
            <strong>{p.provider}</strong>
            {p.default_model ? ` (${p.default_model})` : ""}
            {" — "}
            {labelFor(p.status)}
          </span>
        ))}
      </div>
    </div>
  );
}
