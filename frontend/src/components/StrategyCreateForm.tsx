import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createStrategy } from "../api/client";

export default function StrategyCreateForm() {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: createStrategy,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
      setName("");
      setDescription("");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    createMutation.mutate({ name: name.trim(), description: description.trim() || null });
  };

  return (
    <form className="strategy-create-form" onSubmit={handleSubmit}>
      <h3>새 전략 생성</h3>
      <div className="form-row">
        <label htmlFor="strategy-name">이름</label>
        <input
          id="strategy-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </div>
      <div className="form-row">
        <label htmlFor="strategy-description">설명</label>
        <input
          id="strategy-description"
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <div className="actions">
        <button className="primary" type="submit" disabled={createMutation.isPending}>
          전략 생성
        </button>
      </div>
      {createMutation.isError && (
        <p className="action-result value error">{(createMutation.error as Error)?.message ?? "생성 실패"}</p>
      )}
    </form>
  );
}
