import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateStrategyVersion } from "../api/client";
import type { StrategyVersion, StrategyVersionParameters } from "../types";
import StrategyVersionParametersFields from "./StrategyVersionParametersFields";

interface StrategyVersionEditorProps {
  version: StrategyVersion;
  onClose: () => void;
}

export default function StrategyVersionEditor({ version, onClose }: StrategyVersionEditorProps) {
  const [parameters, setParameters] = useState<StrategyVersionParameters>({ ...version.parameters });
  const [changeDescription, setChangeDescription] = useState(version.change_description ?? "");
  const queryClient = useQueryClient();

  const updateMutation = useMutation({
    mutationFn: () =>
      updateStrategyVersion(version.strategy_id, version.id, {
        parameters,
        change_description: changeDescription.trim() || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strategy-versions", version.strategy_id] });
      onClose();
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // 유니버스(스캐너/관심종목) 전략은 symbol_code가 없다 — 단일종목 모드에서만 필수.
    if (!parameters.universe && !(parameters.symbol_code ?? "").trim()) return;
    updateMutation.mutate();
  };

  return (
    <form className="strategy-version-editor" onSubmit={handleSubmit}>
      <h4>버전 #{version.version_no} 편집 (parameters)</h4>
      <StrategyVersionParametersFields
        parameters={parameters}
        onChange={setParameters}
        idPrefix={`edit-version-${version.id}`}
      />
      <div className="form-row">
        <label htmlFor={`edit-version-${version.id}-change-description`}>change_description</label>
        <input
          id={`edit-version-${version.id}-change-description`}
          type="text"
          value={changeDescription}
          onChange={(e) => setChangeDescription(e.target.value)}
        />
      </div>
      <div className="actions">
        <button className="primary" type="submit" disabled={updateMutation.isPending}>
          저장
        </button>
        <button type="button" onClick={onClose} disabled={updateMutation.isPending}>
          취소
        </button>
      </div>
      {updateMutation.isError && (
        <p className="action-result value error">{(updateMutation.error as Error)?.message ?? "저장 실패"}</p>
      )}
    </form>
  );
}
