import { useSettings } from "../i18n/SettingsContext";
import type { StrategyVersionParameters } from "../types";
import AutoTradeToggle from "./AutoTradeToggle";

interface StrategyVersionParametersFieldsProps {
  parameters: StrategyVersionParameters;
  onChange: (next: StrategyVersionParameters) => void;
  idPrefix: string;
}

const STRATEGY_TYPES = [
  { value: "moving_average_cross", labelKey: "strategyTypeMovingAverage" as const },
  { value: "volume_confirmed_ma_cross", labelKey: "strategyTypeVolumeConfirmed" as const },
  { value: "flow_confirmed_volume_ma_cross", labelKey: "strategyTypeFlowConfirmed" as const },
];

const FLOW_MODES = [
  { value: "foreign_or_institution", labelKey: "flowModeForeignOrInstitution" as const },
  { value: "foreign_and_institution", labelKey: "flowModeForeignAndInstitution" as const },
  { value: "smart_money_vs_retail", labelKey: "flowModeSmartMoneyVsRetail" as const },
];

function getValidationErrors(p: StrategyVersionParameters, t: ReturnType<typeof useSettings>["t"]) {
  const errors: string[] = [];
  if (p.long_window <= p.short_window) errors.push(t.strategyParams.errorLongWindowGtShort);
  if (p.volume_window <= 0) errors.push(t.strategyParams.errorVolumeWindowGt0);
  if (p.volume_multiplier <= 0) errors.push(t.strategyParams.errorVolumeMultiplierGt0);
  if (p.strategy_type === "flow_confirmed_volume_ma_cross") {
    if (p.flow_lookback_days <= 0) errors.push(t.strategyParams.errorFlowLookbackDaysGt0);
    if (p.max_flow_age_days <= 0) errors.push(t.strategyParams.errorMaxFlowAgeDaysGt0);
  }
  return errors;
}

export default function StrategyVersionParametersFields({
  parameters,
  onChange,
  idPrefix,
}: StrategyVersionParametersFieldsProps) {
  const { t } = useSettings();
  const sp = t.strategyParams;

  const update = <K extends keyof StrategyVersionParameters>(key: K, value: StrategyVersionParameters[K]) => {
    onChange({ ...parameters, [key]: value });
  };

  const isVolumeType =
    parameters.strategy_type === "volume_confirmed_ma_cross" ||
    parameters.strategy_type === "flow_confirmed_volume_ma_cross";
  const isFlowType = parameters.strategy_type === "flow_confirmed_volume_ma_cross";
  const validationErrors = getValidationErrors(parameters, t);

  return (
    <div className="parameters-form">
      <div className="form-row">
        <label htmlFor={`${idPrefix}-strategy-type`}>{sp.labelStrategyType}</label>
        <select
          id={`${idPrefix}-strategy-type`}
          value={parameters.strategy_type}
          onChange={(e) => update("strategy_type", e.target.value)}
        >
          {STRATEGY_TYPES.map(({ value, labelKey }) => (
            <option key={value} value={value}>
              {sp[labelKey]}
            </option>
          ))}
        </select>
      </div>
      <div className="form-row">
        <label htmlFor={`${idPrefix}-symbol-code`}>{sp.labelSymbolCode}</label>
        <input
          id={`${idPrefix}-symbol-code`}
          type="text"
          value={parameters.symbol_code}
          onChange={(e) => update("symbol_code", e.target.value)}
          required
        />
      </div>
      <div className="form-row">
        <label htmlFor={`${idPrefix}-short-window`}>{sp.labelShortWindow}</label>
        <input
          id={`${idPrefix}-short-window`}
          type="number"
          min={1}
          value={parameters.short_window}
          onChange={(e) => update("short_window", Number(e.target.value) || 0)}
        />
      </div>
      <div className="form-row">
        <label htmlFor={`${idPrefix}-long-window`}>{sp.labelLongWindow}</label>
        <input
          id={`${idPrefix}-long-window`}
          type="number"
          min={1}
          value={parameters.long_window}
          onChange={(e) => update("long_window", Number(e.target.value) || 0)}
        />
      </div>
      {isVolumeType && (
        <>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-volume-window`}>{sp.labelVolumeWindow}</label>
            <input
              id={`${idPrefix}-volume-window`}
              type="number"
              min={1}
              value={parameters.volume_window}
              onChange={(e) => update("volume_window", Number(e.target.value) || 0)}
            />
          </div>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-volume-multiplier`}>{sp.labelVolumeMultiplier}</label>
            <input
              id={`${idPrefix}-volume-multiplier`}
              type="number"
              min={0.01}
              step={0.1}
              value={parameters.volume_multiplier}
              onChange={(e) => update("volume_multiplier", Number(e.target.value) || 0)}
            />
          </div>
        </>
      )}
      {isFlowType && (
        <>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-flow-lookback-days`}>{sp.labelFlowLookbackDays}</label>
            <input
              id={`${idPrefix}-flow-lookback-days`}
              type="number"
              min={1}
              value={parameters.flow_lookback_days}
              onChange={(e) => update("flow_lookback_days", Number(e.target.value) || 0)}
            />
          </div>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-max-flow-age-days`}>{sp.labelMaxFlowAgeDays}</label>
            <input
              id={`${idPrefix}-max-flow-age-days`}
              type="number"
              min={1}
              value={parameters.max_flow_age_days}
              onChange={(e) => update("max_flow_age_days", Number(e.target.value) || 0)}
            />
          </div>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-flow-mode`}>{sp.labelFlowMode}</label>
            <select
              id={`${idPrefix}-flow-mode`}
              value={parameters.flow_mode}
              onChange={(e) => update("flow_mode", e.target.value)}
            >
              {FLOW_MODES.map(({ value, labelKey }) => (
                <option key={value} value={value}>
                  {sp[labelKey]}
                </option>
              ))}
            </select>
          </div>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-require-flow-data`}>{sp.labelRequireFlowData}</label>
            <input
              id={`${idPrefix}-require-flow-data`}
              type="checkbox"
              checked={parameters.require_flow_data}
              onChange={(e) => update("require_flow_data", e.target.checked)}
            />
          </div>
          <p className="section-description">{sp.hintFlowData}</p>
        </>
      )}
      <div className="form-row">
        <label htmlFor={`${idPrefix}-quantity`}>{sp.labelQuantity}</label>
        <input
          id={`${idPrefix}-quantity`}
          type="number"
          min={1}
          value={parameters.quantity}
          onChange={(e) => update("quantity", Number(e.target.value) || 0)}
        />
      </div>
      <div className="form-row">
        <label htmlFor={`${idPrefix}-timeframe`}>{sp.labelTimeframe}</label>
        <input
          id={`${idPrefix}-timeframe`}
          type="text"
          value={parameters.timeframe}
          onChange={(e) => update("timeframe", e.target.value)}
        />
      </div>
      <div className="form-row">
        <label htmlFor={`${idPrefix}-account-id`}>{sp.labelAccountId}</label>
        <input
          id={`${idPrefix}-account-id`}
          type="number"
          value={parameters.account_id ?? ""}
          onChange={(e) => update("account_id", e.target.value === "" ? null : Number(e.target.value))}
        />
      </div>
      <div className="form-row">
        <label htmlFor={`${idPrefix}-enabled`}>{sp.labelEnabled}</label>
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
      {validationErrors.length > 0 && (
        <ul className="validation-errors">
          {validationErrors.map((msg) => (
            <li key={msg} className="validation-error">
              {msg}
            </li>
          ))}
        </ul>
      )}
      <p className="section-description">{sp.hintAutoTrade}</p>
    </div>
  );
}
