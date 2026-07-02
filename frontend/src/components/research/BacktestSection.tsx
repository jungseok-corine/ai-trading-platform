// C-6.8: 백테스트 콘솔 — 저장된 시세로 전략 파라미터를 즉시 검증하는 사람용 도구.
// 주문/브로커 호출 없음 (read-only 시뮬레이션).
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type BacktestRun, getBacktests, runBacktest } from "../../api/research";

const STRATEGY_TYPES = [
  "moving_average_cross",
  "volume_confirmed_ma_cross",
  "flow_confirmed_volume_ma_cross",
  "rsi_reversion",
  "macd_trend",
  "breakout_high",
  "pullback_trend",
  "momentum_surge",
];

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${v.toFixed(2)}%`;
}

function MetricsTable({ run }: { run: BacktestRun }) {
  if (run.status !== "succeeded" || !run.metrics) {
    return <p className="error">실패: {run.error_message}</p>;
  }
  const m = run.metrics;
  return (
    <table className="compact-table">
      <tbody>
        <tr>
          <td>수익률</td>
          <td>{pct(m.return_pct)}</td>
          <td>단순보유</td>
          <td>{pct(m.buy_hold_return_pct)}</td>
        </tr>
        <tr>
          <td>승률</td>
          <td>{m.win_rate === null ? "—" : `${(m.win_rate * 100).toFixed(0)}%`}</td>
          <td>거래</td>
          <td>
            {m.trade_count} ({m.win_count}승 {m.loss_count}패)
          </td>
        </tr>
        <tr>
          <td>MDD</td>
          <td>{pct(m.max_drawdown_pct)}</td>
          <td>수수료 합계</td>
          <td>{Number(m.total_fees).toLocaleString()}</td>
        </tr>
        <tr>
          <td>기대값</td>
          <td>{m.expectancy === null ? "—" : Number(m.expectancy).toLocaleString()}</td>
          <td>봉 수</td>
          <td>{m.bars.toLocaleString()}</td>
        </tr>
      </tbody>
    </table>
  );
}

export default function BacktestSection() {
  const qc = useQueryClient();
  const [strategyType, setStrategyType] = useState("moving_average_cross");
  const [symbol, setSymbol] = useState("005930");
  const [timeframe, setTimeframe] = useState("1m");
  const [days, setDays] = useState(14);
  const [paramsJson, setParamsJson] = useState('{"short_window": 5, "long_window": 20}');
  const [paramsError, setParamsError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestRun | null>(null);

  const recent = useQuery({ queryKey: ["backtests"], queryFn: () => getBacktests(10) });

  const mut = useMutation({
    mutationFn: () => {
      const end = new Date();
      const start = new Date(end.getTime() - days * 24 * 3600 * 1000);
      return runBacktest({
        strategy_type: strategyType,
        parameters: JSON.parse(paramsJson),
        symbol_code: symbol.trim(),
        timeframe,
        start_ts: start.toISOString(),
        end_ts: end.toISOString(),
      });
    },
    onSuccess: (data) => {
      setResult(data);
      qc.invalidateQueries({ queryKey: ["backtests"] });
    },
  });

  const submit = () => {
    setParamsError(null);
    try {
      JSON.parse(paramsJson);
    } catch {
      setParamsError("파라미터 JSON이 유효하지 않습니다.");
      return;
    }
    mut.mutate();
  };

  return (
    <div className="card">
      <h3>백테스트 콘솔</h3>
      <p className="muted">
        저장된 시세로 전략 파라미터를 즉시 시뮬레이션합니다. 주문 없음 · 계좌 영향 없음 —
        결과는 참고용이며 미래 수익을 보장하지 않습니다.
      </p>
      <div className="form-row">
        <label>
          전략:{" "}
          <select value={strategyType} onChange={(e) => setStrategyType(e.target.value)}>
            {STRATEGY_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label>
          종목: <input value={symbol} onChange={(e) => setSymbol(e.target.value)} size={8} />
        </label>
        <label>
          분봉:{" "}
          <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
            <option value="1m">1m</option>
            <option value="5m">5m</option>
            <option value="1d">1d</option>
          </select>
        </label>
        <label>
          기간:{" "}
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>7일</option>
            <option value={14}>14일</option>
            <option value={30}>30일</option>
            <option value={90}>90일</option>
          </select>
        </label>
      </div>
      <div className="form-row">
        <label style={{ flex: 1 }}>
          파라미터(JSON):{" "}
          <textarea
            value={paramsJson}
            onChange={(e) => setParamsJson(e.target.value)}
            rows={2}
            style={{ width: "100%", fontFamily: "monospace" }}
          />
        </label>
      </div>
      {paramsError && <p className="error">{paramsError}</p>}
      <button className="primary" onClick={submit} disabled={mut.isPending}>
        {mut.isPending ? "실행 중…" : "백테스트 실행"}
      </button>
      {mut.isError && <p className="error">실행 실패 — 입력을 확인하세요.</p>}

      {result && (
        <div className="approval-block">
          <strong>
            결과 #{result.id} — {result.symbol_code} · {result.timeframe} ·{" "}
            {result.strategy_type}
          </strong>
          <MetricsTable run={result} />
        </div>
      )}

      <h4>최근 실행</h4>
      {recent.data && recent.data.length === 0 && <p className="muted">기록 없음</p>}
      {recent.data && recent.data.length > 0 && (
        <table className="compact-table">
          <thead>
            <tr>
              <th>#</th>
              <th>전략</th>
              <th>종목</th>
              <th>분봉</th>
              <th>수익률</th>
              <th>거래</th>
              <th>MDD</th>
              <th>상태</th>
            </tr>
          </thead>
          <tbody>
            {recent.data.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.strategy_type}</td>
                <td>{r.symbol_code}</td>
                <td>{r.timeframe}</td>
                <td>{pct(r.metrics?.return_pct)}</td>
                <td>{r.metrics?.trade_count ?? "—"}</td>
                <td>{pct(r.metrics?.max_drawdown_pct)}</td>
                <td>{r.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
