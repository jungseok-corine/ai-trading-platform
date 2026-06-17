import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createStrategyAnalysisRun, getAIProviderStatuses } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";
import type { AnalysisRunCreateRequest, AnalysisRunMode, PromptType } from "../types";
import AIProviderStatusPanel from "./AIProviderStatusPanel";
import AnalysisRunDetail from "./AnalysisRunDetail";
import AnalysisRunList from "./AnalysisRunList";

interface StrategyAnalysisRunPanelProps {
  strategyId: number;
  versionId: number;
}

const PROMPT_TYPES: PromptType[] = ["overview", "risk", "improvement"];
const PROVIDERS = ["fake", "openai", "anthropic"];

export default function StrategyAnalysisRunPanel({
  strategyId,
  versionId,
}: StrategyAnalysisRunPanelProps) {
  const { t } = useSettings();
  const ta = t.aiAnalysis;
  const queryClient = useQueryClient();

  const [showRuns, setShowRuns] = useState(false);
  const [showResult, setShowResult] = useState(false);

  // form state — defaults to recommended values
  const [promptType, setPromptType] = useState<PromptType>("overview");
  const [mode, setMode] = useState<AnalysisRunMode>("dual");
  const [provider, setProvider] = useState("openai");
  const [secondaryProvider, setSecondaryProvider] = useState("anthropic");
  const [enableCritique, setEnableCritique] = useState(true);
  const [enableSynthesis, setEnableSynthesis] = useState(true);

  const { data: providerStatuses } = useQuery({
    queryKey: ["ai-provider-statuses"],
    queryFn: getAIProviderStatuses,
    staleTime: 60_000,
  });

  const isProviderMissing = (name: string): boolean => {
    if (!providerStatuses) return false;
    const s = providerStatuses.find((p) => p.provider === name);
    return !!s && s.status !== "available";
  };

  const primaryMissing = isProviderMissing(provider);
  const secondaryMissing = mode === "dual" && isProviderMissing(secondaryProvider);
  const canRun = !primaryMissing && !secondaryMissing;

  const createMutation = useMutation({
    mutationFn: (req: AnalysisRunCreateRequest) =>
      createStrategyAnalysisRun(strategyId, versionId, req),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["analysis-runs", strategyId, versionId] });
      setShowResult(true);
      setShowRuns(true);
    },
  });

  const handleRun = () => {
    if (!canRun || createMutation.isPending) return;
    const req: AnalysisRunCreateRequest = {
      prompt_type: promptType,
      provider,
      mode,
      enable_critique: enableCritique,
      enable_synthesis: enableSynthesis,
    };
    if (mode === "dual") {
      req.secondary_provider = secondaryProvider;
    }
    createMutation.mutate(req);
  };

  return (
    <div className="strategy-analysis-run-panel">
      {/* safety note */}
      <div className="ai-safety-note">
        <span>⚠</span>
        <span>{ta.safetyNote}</span>
        <span>{ta.safetyNote2}</span>
      </div>

      <AIProviderStatusPanel />

      {/* run form */}
      <div className="analysis-run-form">
        <h5>{ta.runFormTitle}</h5>

        <div className="form-row">
          <label>{ta.labelPromptType}</label>
          <select
            value={promptType}
            onChange={(e) => setPromptType(e.target.value as PromptType)}
            disabled={createMutation.isPending}
          >
            {PROMPT_TYPES.map((pt) => (
              <option key={pt} value={pt}>{pt}</option>
            ))}
          </select>
        </div>

        <div className="form-row">
          <label>{ta.labelMode}</label>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as AnalysisRunMode)}
            disabled={createMutation.isPending}
          >
            <option value="single">single</option>
            <option value="dual">dual</option>
          </select>
        </div>

        <div className="form-row">
          <label>{ta.labelProvider}</label>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            disabled={createMutation.isPending}
          >
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>

        {mode === "dual" && (
          <div className="form-row">
            <label>{ta.labelSecondaryProvider}</label>
            <select
              value={secondaryProvider}
              onChange={(e) => setSecondaryProvider(e.target.value)}
              disabled={createMutation.isPending}
            >
              {PROVIDERS.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
        )}

        {mode === "dual" && (
          <>
            <div className="form-row checkbox-row">
              <label>
                <input
                  type="checkbox"
                  checked={enableCritique}
                  onChange={(e) => setEnableCritique(e.target.checked)}
                  disabled={createMutation.isPending}
                />
                {" "}{ta.labelEnableCritique}
              </label>
            </div>
            <div className="form-row checkbox-row">
              <label>
                <input
                  type="checkbox"
                  checked={enableSynthesis}
                  onChange={(e) => setEnableSynthesis(e.target.checked)}
                  disabled={createMutation.isPending}
                />
                {" "}{ta.labelEnableSynthesis}
              </label>
            </div>
          </>
        )}

        {(primaryMissing || secondaryMissing) && (
          <p className="value error config-warning">{ta.warningMissingConfig}</p>
        )}

        <div className="actions">
          <button
            className="primary"
            onClick={handleRun}
            disabled={!canRun || createMutation.isPending}
          >
            {createMutation.isPending ? ta.btnRunning : ta.btnRun}
          </button>
        </div>

        {createMutation.isError && (
          <p className="value error">
            {ta.createError}:{" "}
            {(createMutation.error as Error)?.message ?? "unknown error"}
          </p>
        )}
      </div>

      {/* latest result */}
      {showResult && createMutation.data && (
        <AnalysisRunDetail run={createMutation.data} />
      )}

      {/* history */}
      <div className="analysis-run-history">
        <button
          className="outcome-expand-btn"
          onClick={() => setShowRuns(!showRuns)}
        >
          {showRuns ? ta.btnHideRuns : ta.btnShowRuns}
        </button>

        {showRuns && (
          <AnalysisRunList strategyId={strategyId} versionId={versionId} />
        )}
      </div>
    </div>
  );
}
