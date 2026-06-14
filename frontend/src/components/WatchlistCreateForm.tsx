import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createWatchlist } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";

export default function WatchlistCreateForm() {
  const { t } = useSettings();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: createWatchlist,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
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
      <h3>{t.watchlists.createTitle}</h3>
      <div className="form-row">
        <label htmlFor="watchlist-name">{t.watchlists.name}</label>
        <input
          id="watchlist-name"
          type="text"
          value={name}
          placeholder={t.watchlists.namePlaceholder}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </div>
      <div className="form-row">
        <label htmlFor="watchlist-description">{t.watchlists.colDescription}</label>
        <input
          id="watchlist-description"
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <div className="actions">
        <button className="primary" type="submit" disabled={createMutation.isPending}>
          {t.watchlists.create}
        </button>
      </div>
      {createMutation.isError && (
        <p className="action-result value error">
          {(createMutation.error as Error)?.message ?? t.watchlists.createFailed}
        </p>
      )}
    </form>
  );
}
