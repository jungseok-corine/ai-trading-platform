import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createStrategyVersion } from "../api/client";
import {
  DEFAULT_STRATEGY_VERSION_PARAMETERS,
  type StrategyVersionParameters,
  type StrategyVersionStatus,
} from "../types";
import StrategyVersionParametersFields from "./StrategyVersionParametersFields";

interface StrategyVersionCreateFormProps {
  strategyId: number;
}

export default function StrategyVersionCreateForm({ strategyId }: StrategyVersionCreateFormProps) {
  const [parameters, setParameters] = useState<StrategyVersionParameters>({
    ...DEFAULT_STRATEGY_VERSION_PARAMETERS,
  });
  const [changeDescription, setChangeDescription] = useState("");
  const [status, setStatus] = useState<StrategyVersionStatus>("draft");
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: () =>
      createStrategyVersion(strategyId, {
        parameters,
        change_description: changeDescription.trim() || null,
        status,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strategy-versions", strategyId] });
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
      setParameters({ ...DEFAULT_STRATEGY_VERSION_PARAMETERS });
      setChangeDescription("");
      setStatus("draft");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!parameters.symbol_code.trim()) return;
    createMutation.mutate();
  };

  return (
    <form className="strategy-version-create-form" onSubmit={handleSubmit}>
      <h4>새 버전 생성</h4>
      <StrategyVersionParametersFields
        parameters={parameters}
        onChange={setParameters}
        idPrefix={`new-version-${strategyId}`}
      />
      <div className="form-row">
        <label htmlFor={`new-version-${strategyId}-status`}>status</label>
        <select
          id={`new-version-${strategyId}-status`}
          value={status}
          onChange={(e) => setStatus(e.target.value as StrategyVersionStatus)}
        >
          <option value="draft">draft</option>
          <option value="testing">testing</option>
          <option value="active">active</option>
          <option value="retired">retired</option>
        </select>
      </div>
      <div className="form-row">
        <label htmlFor={`new-version-${strategyId}-change-description`}>change_description</label>
        <input
          id={`new-version-${strategyId}-change-description`}
          type="text"
          value={changeDescription}
          onChange={(e) => setChangeDescription(e.target.value)}
        />
      </div>
      <div className="actions">
        <button className="primary" type="submit" disabled={createMutation.isPending}>
          버전 생성
        </button>
      </div>
      {createMutation.isError && (
        <p className="action-result value error">{(createMutation.error as Error)?.message ?? "생성 실패"}</p>
      )}
    </form>
  );
}
