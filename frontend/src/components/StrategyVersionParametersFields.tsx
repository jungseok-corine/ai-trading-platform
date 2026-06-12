import type { StrategyVersionParameters } from "../types";
import AutoTradeToggle from "./AutoTradeToggle";

interface StrategyVersionParametersFieldsProps {
  parameters: StrategyVersionParameters;
  onChange: (next: StrategyVersionParameters) => void;
  idPrefix: string;
}

export default function StrategyVersionParametersFields({
  parameters,
  onChange,
  idPrefix,
}: StrategyVersionParametersFieldsProps) {
  const update = <K extends keyof StrategyVersionParameters>(key: K, value: StrategyVersionParameters[K]) => {
    onChange({ ...parameters, [key]: value });
  };

  return (
    <div className="parameters-form">
      <div className="form-row">
        <label htmlFor={`${idPrefix}-strategy-type`}>strategy_type</label>
        <select
          id={`${idPrefix}-strategy-type`}
          value={parameters.strategy_type}
          onChange={(e) => update("strategy_type", e.target.value)}
        >
          <option value="moving_average_cross">moving_average_cross</option>
        </select>
      </div>
      <div className="form-row">
        <label htmlFor={`${idPrefix}-symbol-code`}>symbol_code</label>
        <input
          id={`${idPrefix}-symbol-code`}
          type="text"
          value={parameters.symbol_code}
          onChange={(e) => update("symbol_code", e.target.value)}
          required
        />
      </div>
      <div className="form-row">
        <label htmlFor={`${idPrefix}-short-window`}>short_window</label>
        <input
          id={`${idPrefix}-short-window`}
          type="number"
          min={1}
          value={parameters.short_window}
          onChange={(e) => update("short_window", Number(e.target.value) || 0)}
        />
      </div>
      <div className="form-row">
        <label htmlFor={`${idPrefix}-long-window`}>long_window</label>
        <input
          id={`${idPrefix}-long-window`}
          type="number"
          min={1}
          value={parameters.long_window}
          onChange={(e) => update("long_window", Number(e.target.value) || 0)}
        />
      </div>
      <div className="form-row">
        <label htmlFor={`${idPrefix}-quantity`}>quantity</label>
        <input
          id={`${idPrefix}-quantity`}
          type="number"
          min={1}
          value={parameters.quantity}
          onChange={(e) => update("quantity", Number(e.target.value) || 0)}
        />
      </div>
      <div className="form-row">
        <label htmlFor={`${idPrefix}-timeframe`}>timeframe</label>
        <input
          id={`${idPrefix}-timeframe`}
          type="text"
          value={parameters.timeframe}
          onChange={(e) => update("timeframe", e.target.value)}
        />
      </div>
      <div className="form-row">
        <label htmlFor={`${idPrefix}-account-id`}>account_id</label>
        <input
          id={`${idPrefix}-account-id`}
          type="number"
          value={parameters.account_id ?? ""}
          onChange={(e) => update("account_id", e.target.value === "" ? null : Number(e.target.value))}
        />
      </div>
      <div className="form-row">
        <label htmlFor={`${idPrefix}-enabled`}>enabled</label>
        <input
          id={`${idPrefix}-enabled`}
          type="checkbox"
          checked={parameters.enabled}
          onChange={(e) => update("enabled", e.target.checked)}
        />
      </div>
      <div className="form-row">
        <AutoTradeToggle
          value={parameters.auto_trade_enabled}
          accountId={parameters.account_id}
          quantity={parameters.quantity}
          onChange={(next) => update("auto_trade_enabled", next)}
        />
      </div>
      <p className="section-description">
        auto_trade_enabled가 OFF이면 신호(Signal)만 생성되어 기록되고, 실제 KIS 주문은 실행되지 않습니다.
        ON으로 설정하면 RiskManager 검증을 통과한 신호에 한해 자동으로 주문이 전송됩니다.
      </p>
    </div>
  );
}
