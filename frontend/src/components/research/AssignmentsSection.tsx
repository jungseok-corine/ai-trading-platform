import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createAssignmentRule, getAssignmentLogs, getAssignmentRules } from "../../api/research";

const STRATEGY_TYPES = [
  "moving_average_cross",
  "volume_confirmed_ma_cross",
  "flow_confirmed_volume_ma_cross",
];

export default function AssignmentsSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [strategyType, setStrategyType] = useState(STRATEGY_TYPES[0]);
  const [scannerRuleId, setScannerRuleId] = useState("");
  const [priority, setPriority] = useState("0");

  const { data: rules } = useQuery({ queryKey: ["assignment-rules"], queryFn: getAssignmentRules });
  const { data: logs } = useQuery({ queryKey: ["assignment-logs"], queryFn: () => getAssignmentLogs() });

  const createMut = useMutation({
    mutationFn: () =>
      createAssignmentRule({
        name,
        strategy_type: strategyType,
        scanner_rule_id: scannerRuleId ? Number(scannerRuleId) : null,
        priority: Number(priority),
      }),
    onSuccess: () => {
      setName("");
      queryClient.invalidateQueries({ queryKey: ["assignment-rules"] });
    },
  });

  return (
    <div className="card">
      <h3>전략 배정 규칙</h3>
      <p className="muted">후보 종목에 어떤 전략을 붙일지 결정합니다 (scanner_rule 지정 또는 전체 fallback, priority 우선).</p>
      <div className="form-row">
        <input placeholder="규칙 이름" value={name} onChange={(e) => setName(e.target.value)} />
        <select value={strategyType} onChange={(e) => setStrategyType(e.target.value)}>
          {STRATEGY_TYPES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <input placeholder="scanner_rule_id (선택)" value={scannerRuleId}
          onChange={(e) => setScannerRuleId(e.target.value)} style={{ width: 140 }} />
        <input placeholder="priority" value={priority} onChange={(e) => setPriority(e.target.value)} style={{ width: 80 }} />
        <button className="primary" disabled={!name || createMut.isPending} onClick={() => createMut.mutate()}>
          규칙 생성
        </button>
      </div>

      {rules && rules.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead><tr><th>ID</th><th>이름</th><th>전략</th><th>scanner</th><th>priority</th></tr></thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td><td>{r.name}</td><td>{r.strategy_type}</td>
                  <td>{r.scanner_rule_id ?? "fallback"}</td><td>{r.priority}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h4>배정 로그</h4>
      {logs && logs.length === 0 && <p className="muted">아직 배정 기록이 없습니다.</p>}
      {logs && logs.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead><tr><th>후보</th><th>종목</th><th>배정 전략</th><th>시각</th></tr></thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id}>
                  <td>#{l.candidate_event_id}</td><td>{l.symbol_code}</td>
                  <td>{l.strategy_type}</td><td>{new Date(l.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
