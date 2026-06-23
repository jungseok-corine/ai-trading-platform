import { useSettings } from "../i18n/SettingsContext";
import type { StrategyVersionParameters } from "../types";
import AccountSelect from "./AccountSelect";
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
  { value: "rsi_reversion", labelKey: "strategyTypeRsiReversion" as const },
  { value: "macd_trend", labelKey: "strategyTypeMacdTrend" as const },
  { value: "breakout_high", labelKey: "strategyTypeBreakoutHigh" as const },
  { value: "pullback_trend", labelKey: "strategyTypePullbackTrend" as const },
];

const UNIVERSES = [
  { value: "", labelKey: "universeNone" as const },
  { value: "scanner_candidates", labelKey: "universeScannerCandidates" as const },
  { value: "watchlist", labelKey: "universeWatchlist" as const },
];

const EXIT_MODES = [
  { value: "overbought", labelKey: "exitModeOverbought" as const },
  { value: "midline", labelKey: "exitModeMidline" as const },
];

// short_window/long_window 입력을 노출하는 MA 계열 전략 타입.
const MA_WINDOW_TYPES = new Set([
  "moving_average_cross",
  "volume_confirmed_ma_cross",
  "flow_confirmed_volume_ma_cross",
  "pullback_trend",
]);

const FLOW_MODES = [
  { value: "foreign_or_institution", labelKey: "flowModeForeignOrInstitution" as const },
  { value: "foreign_and_institution", labelKey: "flowModeForeignAndInstitution" as const },
  { value: "smart_money_vs_retail", labelKey: "flowModeSmartMoneyVsRetail" as const },
];

function getValidationErrors(p: StrategyVersionParameters, t: ReturnType<typeof useSettings>["t"]) {
  const errors: string[] = [];
  if (MA_WINDOW_TYPES.has(p.strategy_type) && p.long_window <= p.short_window) {
    errors.push(t.strategyParams.errorLongWindowGtShort);
  }
  const isVolume =
    p.strategy_type === "volume_confirmed_ma_cross" ||
    p.strategy_type === "flow_confirmed_volume_ma_cross";
  if (isVolume) {
    if (p.volume_window <= 0) errors.push(t.strategyParams.errorVolumeWindowGt0);
    if (p.volume_multiplier <= 0) errors.push(t.strategyParams.errorVolumeMultiplierGt0);
  }
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
    parameters.strategy_type === "flow_confirmed_volume_ma_cross" ||
    parameters.strategy_type === "momentum_surge";
  const isFlowType = parameters.strategy_type === "flow_confirmed_volume_ma_cross";
  const isMaType = MA_WINDOW_TYPES.has(parameters.strategy_type);
  const isRsiType = parameters.strategy_type === "rsi_reversion";
  const isMacdType = parameters.strategy_type === "macd_trend";
  const isBreakoutType = parameters.strategy_type === "breakout_high";
  const isMomentumSurgeType = parameters.strategy_type === "momentum_surge";
  const universeMode = !!parameters.universe;
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
        <label htmlFor={`${idPrefix}-market`}>{sp.labelMarket}</label>
        <select
          id={`${idPrefix}-market`}
          value={parameters.market ?? "KR"}
          onChange={(e) => update("market", e.target.value)}
        >
          <option value="KR">{sp.marketKr}</option>
          <option value="US">{sp.marketUs}</option>
        </select>
      </div>
      {(parameters.market ?? "KR") === "US" && (
        <div className="form-row">
          <label htmlFor={`${idPrefix}-exchange`}>{sp.labelExchange}</label>
          <select
            id={`${idPrefix}-exchange`}
            value={parameters.exchange ?? "NAS"}
            onChange={(e) => update("exchange", e.target.value)}
          >
            <option value="NAS">NAS (NASDAQ)</option>
            <option value="NYS">NYS (NYSE)</option>
            <option value="AMS">AMS (AMEX)</option>
          </select>
        </div>
      )}
      <div className="form-row">
        <label htmlFor={`${idPrefix}-universe`}>{sp.labelUniverse}</label>
        <select
          id={`${idPrefix}-universe`}
          value={parameters.universe ?? ""}
          onChange={(e) => {
            const value = e.target.value || null;
            // 유니버스 모드는 신호 생성 전용 — 자동매매를 강제로 끈다.
            onChange({
              ...parameters,
              universe: value,
              auto_trade_enabled: value ? false : parameters.auto_trade_enabled,
            });
          }}
        >
          {UNIVERSES.map(({ value, labelKey }) => (
            <option key={value} value={value}>
              {sp[labelKey]}
            </option>
          ))}
        </select>
      </div>
      {universeMode && (
        <div className="form-row">
          <label htmlFor={`${idPrefix}-universe-market`}>{sp.labelUniverseMarket}</label>
          <select
            id={`${idPrefix}-universe-market`}
            value={parameters.universe_market ?? ""}
            onChange={(e) => update("universe_market", e.target.value || null)}
          >
            <option value="">{sp.universeMarketAll}</option>
            <option value="KR">KR</option>
            <option value="US">US</option>
          </select>
        </div>
      )}
      {!universeMode && (
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
      )}
      {universeMode && <p className="section-description">{sp.hintUniverse}</p>}
      {universeMode && (
        <>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-universe-auto-trade`}>{sp.labelUniverseAutoTrade}</label>
            <input
              id={`${idPrefix}-universe-auto-trade`}
              type="checkbox"
              checked={parameters.universe_auto_trade ?? false}
              onChange={(e) => update("universe_auto_trade", e.target.checked)}
            />
          </div>
          {parameters.universe_auto_trade && (
            <>
              <div className="form-row">
                <label htmlFor={`${idPrefix}-universe-account`}>{sp.labelAccountId}</label>
                <AccountSelect
                  id={`${idPrefix}-universe-account`}
                  value={parameters.account_id ?? null}
                  onChange={(next) => update("account_id", next)}
                  paperOnly
                />
              </div>
              <div className="form-row">
                <label htmlFor={`${idPrefix}-max-orders`}>{sp.labelMaxOrdersPerRun}</label>
                <input
                  id={`${idPrefix}-max-orders`}
                  type="number"
                  min={1}
                  value={parameters.max_orders_per_run ?? 5}
                  onChange={(e) => update("max_orders_per_run", Number(e.target.value) || 0)}
                />
              </div>
              <p className="section-description">{sp.hintUniverseAutoTrade}</p>
            </>
          )}
        </>
      )}
      {isMaType && (
        <>
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
        </>
      )}
      {isRsiType && (
        <>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-rsi-period`}>{sp.labelRsiPeriod}</label>
            <input
              id={`${idPrefix}-rsi-period`}
              type="number"
              min={2}
              value={parameters.rsi_period ?? 14}
              onChange={(e) => update("rsi_period", Number(e.target.value) || 0)}
            />
          </div>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-oversold`}>{sp.labelOversold}</label>
            <input
              id={`${idPrefix}-oversold`}
              type="number"
              min={0}
              value={parameters.oversold ?? 30}
              onChange={(e) => update("oversold", Number(e.target.value) || 0)}
            />
          </div>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-overbought`}>{sp.labelOverbought}</label>
            <input
              id={`${idPrefix}-overbought`}
              type="number"
              min={0}
              value={parameters.overbought ?? 70}
              onChange={(e) => update("overbought", Number(e.target.value) || 0)}
            />
          </div>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-exit-mode`}>{sp.labelExitMode}</label>
            <select
              id={`${idPrefix}-exit-mode`}
              value={parameters.exit_mode ?? "overbought"}
              onChange={(e) => update("exit_mode", e.target.value)}
            >
              {EXIT_MODES.map(({ value, labelKey }) => (
                <option key={value} value={value}>
                  {sp[labelKey]}
                </option>
              ))}
            </select>
          </div>
        </>
      )}
      {isMacdType && (
        <>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-fast-period`}>{sp.labelFastPeriod}</label>
            <input
              id={`${idPrefix}-fast-period`}
              type="number"
              min={1}
              value={parameters.fast_period ?? 12}
              onChange={(e) => update("fast_period", Number(e.target.value) || 0)}
            />
          </div>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-slow-period`}>{sp.labelSlowPeriod}</label>
            <input
              id={`${idPrefix}-slow-period`}
              type="number"
              min={2}
              value={parameters.slow_period ?? 26}
              onChange={(e) => update("slow_period", Number(e.target.value) || 0)}
            />
          </div>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-signal-period`}>{sp.labelSignalPeriod}</label>
            <input
              id={`${idPrefix}-signal-period`}
              type="number"
              min={1}
              value={parameters.signal_period ?? 9}
              onChange={(e) => update("signal_period", Number(e.target.value) || 0)}
            />
          </div>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-require-above-zero`}>{sp.labelRequireAboveZero}</label>
            <input
              id={`${idPrefix}-require-above-zero`}
              type="checkbox"
              checked={parameters.require_above_zero ?? false}
              onChange={(e) => update("require_above_zero", e.target.checked)}
            />
          </div>
        </>
      )}
      {isBreakoutType && (
        <>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-breakout-lookback`}>{sp.labelBreakoutLookback}</label>
            <input
              id={`${idPrefix}-breakout-lookback`}
              type="number"
              min={1}
              value={parameters.breakout_lookback ?? 20}
              onChange={(e) => update("breakout_lookback", Number(e.target.value) || 0)}
            />
          </div>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-exit-lookback`}>{sp.labelExitLookback}</label>
            <input
              id={`${idPrefix}-exit-lookback`}
              type="number"
              min={1}
              value={parameters.exit_lookback ?? 10}
              onChange={(e) => update("exit_lookback", Number(e.target.value) || 0)}
            />
          </div>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-volume-confirm`}>{sp.labelVolumeConfirm}</label>
            <input
              id={`${idPrefix}-volume-confirm`}
              type="checkbox"
              checked={parameters.volume_confirm ?? false}
              onChange={(e) => update("volume_confirm", e.target.checked)}
            />
          </div>
        </>
      )}
      {isMomentumSurgeType && (
        <>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-surge-lookback`}>{sp.labelSurgeLookback}</label>
            <input
              id={`${idPrefix}-surge-lookback`}
              type="number"
              min={1}
              value={parameters.surge_lookback ?? 5}
              onChange={(e) => update("surge_lookback", Number(e.target.value) || 0)}
            />
          </div>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-surge-threshold`}>{sp.labelSurgeThresholdPct}</label>
            <input
              id={`${idPrefix}-surge-threshold`}
              type="number"
              min={0.01}
              step={0.1}
              value={parameters.surge_threshold_pct ?? 5}
              onChange={(e) => update("surge_threshold_pct", Number(e.target.value) || 0)}
            />
          </div>
          <div className="form-row">
            <label htmlFor={`${idPrefix}-exit-drop`}>{sp.labelExitDropPct}</label>
            <input
              id={`${idPrefix}-exit-drop`}
              type="number"
              min={0.01}
              step={0.1}
              value={parameters.exit_drop_pct ?? 3}
              onChange={(e) => update("exit_drop_pct", Number(e.target.value) || 0)}
            />
          </div>
        </>
      )}
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
        <label htmlFor={`${idPrefix}-quantity-mode`}>{sp.labelQuantityMode}</label>
        <select
          id={`${idPrefix}-quantity-mode`}
          value={parameters.quantity_mode ?? "fixed"}
          onChange={(e) => update("quantity_mode", e.target.value)}
        >
          <option value="fixed">{sp.quantityModeFixed}</option>
          <option value="cash_amount">{sp.quantityModeCashAmount}</option>
          <option value="cash_pct">{sp.quantityModeCashPct}</option>
        </select>
      </div>
      {(parameters.quantity_mode ?? "fixed") === "fixed" && (
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
      )}
      {parameters.quantity_mode === "cash_amount" && (
        <div className="form-row">
          <label htmlFor={`${idPrefix}-cash-amount`}>{sp.labelCashAmount}</label>
          <input
            id={`${idPrefix}-cash-amount`}
            type="number"
            min={0}
            value={parameters.cash_amount ?? 0}
            onChange={(e) => update("cash_amount", Number(e.target.value) || 0)}
          />
        </div>
      )}
      {parameters.quantity_mode === "cash_pct" && (
        <div className="form-row">
          <label htmlFor={`${idPrefix}-cash-pct`}>{sp.labelCashPct}</label>
          <input
            id={`${idPrefix}-cash-pct`}
            type="number"
            min={0}
            max={100}
            value={parameters.cash_pct ?? 0}
            onChange={(e) => update("cash_pct", Number(e.target.value) || 0)}
          />
        </div>
      )}
      <div className="form-row">
        <label htmlFor={`${idPrefix}-timeframe`}>{sp.labelTimeframe}</label>
        <input
          id={`${idPrefix}-timeframe`}
          type="text"
          value={parameters.timeframe}
          onChange={(e) => update("timeframe", e.target.value)}
        />
      </div>
      {!universeMode && (
        <div className="form-row">
          <label htmlFor={`${idPrefix}-account-id`}>{sp.labelAccountId}</label>
          <AccountSelect
            id={`${idPrefix}-account-id`}
            value={parameters.account_id ?? null}
            onChange={(next) => update("account_id", next)}
          />
        </div>
      )}
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
        <label htmlFor={`${idPrefix}-exit-on-close`}>{sp.labelExitOnClose}</label>
        <input
          id={`${idPrefix}-exit-on-close`}
          type="checkbox"
          checked={parameters.exit_on_close}
          onChange={(e) => update("exit_on_close", e.target.checked)}
        />
      </div>
      <p className="section-description">{sp.hintExitOnClose}</p>
      <div className="form-row">
        <label htmlFor={`${idPrefix}-stop-loss-pct`}>{sp.labelStopLossPct}</label>
        <input
          id={`${idPrefix}-stop-loss-pct`}
          type="number"
          min="0"
          step="0.1"
          placeholder="-"
          value={parameters.stop_loss_pct ?? ""}
          onChange={(e) =>
            update("stop_loss_pct", e.target.value === "" ? null : parseFloat(e.target.value))
          }
        />
      </div>
      <div className="form-row">
        <label htmlFor={`${idPrefix}-take-profit-pct`}>{sp.labelTakeProfitPct}</label>
        <input
          id={`${idPrefix}-take-profit-pct`}
          type="number"
          min="0"
          step="0.1"
          placeholder="-"
          value={parameters.take_profit_pct ?? ""}
          onChange={(e) =>
            update("take_profit_pct", e.target.value === "" ? null : parseFloat(e.target.value))
          }
        />
      </div>
      <p className="section-description">{sp.hintSlTp}</p>
      {!universeMode && (
        <div className="form-row">
          <AutoTradeToggle
            value={parameters.auto_trade_enabled}
            accountId={parameters.account_id}
            quantity={parameters.quantity}
            onChange={(next) => update("auto_trade_enabled", next)}
          />
        </div>
      )}
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
