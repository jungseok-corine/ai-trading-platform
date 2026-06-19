import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addExperimentVariant,
  compareExperiment,
  createExperiment,
  getExperiment,
  getExperiments,
} from "../../api/research";
import type { ComparisonResult, VariantRole } from "../../types/research";

function ExperimentDetailPanel({ experimentId }: { experimentId: number }) {
  const queryClient = useQueryClient();
  const [versionId, setVersionId] = useState("");
  const [role, setRole] = useState<VariantRole>("challenger");
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);

  const { data } = useQuery({
    queryKey: ["experiment", experimentId],
    queryFn: () => getExperiment(experimentId),
  });

  const addMut = useMutation({
    mutationFn: () => addExperimentVariant(experimentId, { strategy_version_id: Number(versionId), role }),
    onSuccess: () => {
      setVersionId("");
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId] });
    },
  });
  const compareMut = useMutation({
    mutationFn: () => compareExperiment(experimentId, true),
    onSuccess: (r) => setComparison(r),
  });

  return (
    <div>
      <div className="form-row">
        <input placeholder="strategy_version_id" value={versionId} onChange={(e) => setVersionId(e.target.value)} />
        <select value={role} onChange={(e) => setRole(e.target.value as VariantRole)}>
          <option value="champion">champion</option>
          <option value="challenger">challenger</option>
        </select>
        <button className="primary" disabled={!versionId || addMut.isPending} onClick={() => addMut.mutate()}>
          variant 추가
        </button>
        <button disabled={compareMut.isPending} onClick={() => compareMut.mutate()}>성과 비교</button>
      </div>

      {data && data.variants.length > 0 && (
        <p className="muted">variants: {data.variants.map((v) => `v${v.strategy_version_id}(${v.role})`).join(", ")}</p>
      )}

      {comparison && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr><th>variant</th><th>거래</th><th>승률%</th><th>기대값</th><th>손익비</th><th>MDD</th><th></th></tr>
            </thead>
            <tbody>
              {comparison.variants.map((c) => (
                <tr key={c.variant_id} className={c.variant_id === comparison.winner_variant_id ? "winner-row" : undefined}>
                  <td>#{c.strategy_version_id} ({c.role})</td>
                  <td>{c.metrics.trades_count}</td>
                  <td>{c.metrics.win_rate}</td>
                  <td>{c.metrics.expectancy}</td>
                  <td>{c.metrics.profit_factor ?? "-"}</td>
                  <td>{c.metrics.max_drawdown}</td>
                  <td>{c.variant_id === comparison.winner_variant_id ? "🏆 승자" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {comparison.winner_variant_id === null && <p className="muted">승자 없음 (무거래/동률).</p>}
        </div>
      )}
    </div>
  );
}

export default function ExperimentsSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);

  const { data } = useQuery({ queryKey: ["experiments"], queryFn: getExperiments });
  const createMut = useMutation({
    mutationFn: () => createExperiment({ name }),
    onSuccess: () => {
      setName("");
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
    },
  });

  return (
    <div className="card">
      <h3>Paper 실험 (챔피언/챌린저)</h3>
      <p className="muted">전략 버전들을 묶어 paper 성과를 비교합니다. 기대값이 가장 높은 variant가 승자입니다.</p>
      <div className="form-row">
        <input placeholder="실험 이름 (예: v1 vs v2)" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="primary" disabled={!name || createMut.isPending} onClick={() => createMut.mutate()}>
          실험 생성
        </button>
      </div>
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead><tr><th>ID</th><th>이름</th><th>상태</th><th></th></tr></thead>
            <tbody>
              {data.map((e) => (
                <tr key={e.id}>
                  <td>{e.id}</td><td>{e.name}</td><td>{e.status}</td>
                  <td><button onClick={() => setExpanded(expanded === e.id ? null : e.id)}>
                    {expanded === e.id ? "닫기" : "variant/비교"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {expanded !== null && <div className="card"><ExperimentDetailPanel experimentId={expanded} /></div>}
    </div>
  );
}
