import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createPromotionCriteria,
  evaluatePromotion,
  getPromotionCriteria,
} from "../../api/research";
import type { PromotionEvaluation } from "../../types/research";

export default function PromotionsSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [minTrades, setMinTrades] = useState("50");
  const [minDays, setMinDays] = useState("30");
  const [versionId, setVersionId] = useState("");
  const [criteriaId, setCriteriaId] = useState("");
  const [result, setResult] = useState<PromotionEvaluation | null>(null);

  const { data: criteria } = useQuery({ queryKey: ["promotion-criteria"], queryFn: getPromotionCriteria });

  const createMut = useMutation({
    mutationFn: () =>
      createPromotionCriteria({ name, min_trade_count: Number(minTrades), min_days: Number(minDays) }),
    onSuccess: () => {
      setName("");
      queryClient.invalidateQueries({ queryKey: ["promotion-criteria"] });
    },
  });
  const evalMut = useMutation({
    mutationFn: () => evaluatePromotion(Number(versionId), Number(criteriaId), true),
    onSuccess: (r) => setResult(r),
    onError: () => setResult(null),
  });

  return (
    <div className="card">
      <h3>실전 승격 게이트</h3>
      <p className="muted">
        paper 검증된 전략만 실전 후보로 승격합니다. ⚠️ 게이트 통과는 판단일 뿐, 실거래를 자동으로 켜지 않습니다.
      </p>

      <div className="card" style={{ background: "#f8f9fa" }}>
        <strong>승격 기준 생성</strong>
        <div className="form-row">
          <input placeholder="기준 이름" value={name} onChange={(e) => setName(e.target.value)} />
          <input placeholder="min_trade_count" value={minTrades} onChange={(e) => setMinTrades(e.target.value)} style={{ width: 130 }} />
          <input placeholder="min_days" value={minDays} onChange={(e) => setMinDays(e.target.value)} style={{ width: 100 }} />
          <button className="primary" disabled={!name || createMut.isPending} onClick={() => createMut.mutate()}>생성</button>
        </div>
      </div>

      {criteria && criteria.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead><tr><th>ID</th><th>이름</th><th>min거래</th><th>min일수</th><th>min기대값</th></tr></thead>
            <tbody>
              {criteria.map((c) => (
                <tr key={c.id}><td>{c.id}</td><td>{c.name}</td><td>{c.min_trade_count}</td><td>{c.min_days}</td><td>{c.min_expectancy}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="form-row">
        <input placeholder="strategy_version_id" value={versionId} onChange={(e) => setVersionId(e.target.value)} />
        <input placeholder="criteria_id" value={criteriaId} onChange={(e) => setCriteriaId(e.target.value)} />
        <button className="primary" disabled={!versionId || !criteriaId || evalMut.isPending} onClick={() => evalMut.mutate()}>
          승격 평가
        </button>
      </div>
      {evalMut.isError && <p className="value error">평가 실패 (version/criteria 확인)</p>}
      {result && (
        <div className="card">
          <strong>결과: {result.passed ? "✅ 통과" : "❌ 미달"}</strong>
          <table>
            <thead><tr><th>항목</th><th>실제</th><th>기준</th><th>통과</th></tr></thead>
            <tbody>
              {result.checks.map((c) => (
                <tr key={c.name}><td>{c.name}</td><td>{c.actual}</td><td>{c.threshold}</td><td>{c.passed ? "✓" : "✗"}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
