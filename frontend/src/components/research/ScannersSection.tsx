import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createScannerRule,
  createScannerVersion,
  getScannerRules,
  getScannerVersions,
  scanMarket,
  updateScannerVersionStatus,
} from "../../api/research";
import type { ScannerCondition, ScannerRuleStatus } from "../../types/research";

const STATUS_OPTIONS: ScannerRuleStatus[] = ["draft", "testing", "active", "archived"];

const CONDITION_PRESETS: Record<string, ScannerCondition> = {
  volume_spike: { type: "volume_spike", params: { multiplier: 2.0 } },
  price_change_pct: { type: "price_change_pct", params: { min_pct: 5.0 } },
  turnover_rank: { type: "turnover_rank", params: { max_rank: 100 } },
  investor_flow: { type: "investor_flow", params: { foreign: "net_buy" } },
  time_bucket: { type: "time_bucket", params: { buckets: ["morning"] } },
};

function VersionsPanel({ ruleId }: { ruleId: number }) {
  const queryClient = useQueryClient();
  const [picked, setPicked] = useState<string[]>(["volume_spike"]);
  const [symbols, setSymbols] = useState("005930,000660");
  const [scanResult, setScanResult] = useState<string | null>(null);

  const { data } = useQuery({
    queryKey: ["scanner-versions", ruleId],
    queryFn: () => getScannerVersions(ruleId),
  });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["scanner-versions", ruleId] });

  const createMut = useMutation({
    mutationFn: () =>
      createScannerVersion(ruleId, {
        conditions: picked.map((k) => CONDITION_PRESETS[k]),
        status: "testing",
      }),
    onSuccess: invalidate,
  });
  const statusMut = useMutation({
    mutationFn: ({ vid, status }: { vid: number; status: ScannerRuleStatus }) =>
      updateScannerVersionStatus(ruleId, vid, status),
    onSuccess: invalidate,
  });
  const scanMut = useMutation({
    mutationFn: (vid: number) =>
      scanMarket(ruleId, vid, { symbol_codes: symbols.split(",").map((s) => s.trim()).filter(Boolean) }),
    onSuccess: (r) => setScanResult(`스캔 ${r.scanned}종목 중 ${r.matched}종목 매칭됨.`),
    onError: (e) => setScanResult((e as Error)?.message ?? "스캔 실패 (시장 데이터 필요)"),
  });

  return (
    <div>
      <div className="form-row">
        {Object.keys(CONDITION_PRESETS).map((k) => (
          <label key={k} className="param-chip">
            <input type="checkbox" checked={picked.includes(k)}
              onChange={(e) =>
                setPicked((prev) => (e.target.checked ? [...prev, k] : prev.filter((x) => x !== k)))
              } />
            {k}
          </label>
        ))}
        <button className="primary" disabled={picked.length === 0 || createMut.isPending}
          onClick={() => createMut.mutate()}>버전 생성(조건)</button>
      </div>

      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead><tr><th>v</th><th>조건</th><th>상태</th><th>스캔</th></tr></thead>
            <tbody>
              {data.map((v) => (
                <tr key={v.id}>
                  <td>{v.version_no}</td>
                  <td><code>{v.conditions.map((c) => c.type).join(", ")}</code></td>
                  <td>
                    <select value={v.status}
                      onChange={(e) => statusMut.mutate({ vid: v.id, status: e.target.value as ScannerRuleStatus })}>
                      {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td>
                    <button disabled={scanMut.isPending} onClick={() => scanMut.mutate(v.id)}>
                      시장 스캔
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="form-row">
        <input value={symbols} onChange={(e) => setSymbols(e.target.value)}
          placeholder="종목코드 쉼표구분" style={{ minWidth: 240 }} />
        <span className="muted">스캔 대상 종목 (market_data 필요)</span>
      </div>
      {scanResult && <p className="action-result value">{scanResult}</p>}
    </div>
  );
}

export default function ScannersSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);

  const { data, isLoading } = useQuery({ queryKey: ["scanner-rules"], queryFn: getScannerRules });
  const createMut = useMutation({
    mutationFn: () => createScannerRule({ name }),
    onSuccess: () => {
      setName("");
      queryClient.invalidateQueries({ queryKey: ["scanner-rules"] });
    },
  });

  return (
    <div className="card">
      <h3>스캐너 룰 (시장 감시 조건)</h3>
      <p className="muted">조건을 만족하는 종목을 후보로 발견합니다. 룰 → 버전 → 시장 스캔 순으로 동작합니다.</p>
      <div className="form-row">
        <input placeholder="룰 이름 (예: 장초반 급등주)" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="primary" disabled={!name || createMut.isPending} onClick={() => createMut.mutate()}>
          룰 생성
        </button>
      </div>
      {isLoading && <p className="muted">불러오는 중...</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead><tr><th>ID</th><th>이름</th><th>시장</th><th>버전수</th><th></th></tr></thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td><td>{r.name}</td><td>{r.market}</td><td>{r.version_count}</td>
                  <td><button onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                    {expanded === r.id ? "닫기" : "버전/스캔"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {expanded !== null && <div className="card"><VersionsPanel ruleId={expanded} /></div>}
    </div>
  );
}
