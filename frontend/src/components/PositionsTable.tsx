import { useQuery } from "@tanstack/react-query";
import { getPositions } from "../api/client";
import { useSettings } from "../i18n/SettingsContext";

function multiply(a: string, b: number): number {
  return Number(a) * b;
}

export default function PositionsTable() {
  const { t, formatDateTime, accountId } = useSettings();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["positions", accountId],
    queryFn: () => getPositions(accountId),
  });

  return (
    <div className="card">
      <h2>{t.positions.title}</h2>
      <p className="section-description">{t.positions.description}</p>
      {isLoading && <p className="muted">{t.common.loading}</p>}
      {isError && <p className="value error">{(error as Error)?.message ?? t.common.loadError}</p>}
      {data && data.length === 0 && <p className="muted">{t.positions.empty}</p>}
      {data && data.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t.positions.colSymbol}</th>
                <th>{t.positions.colQuantity}</th>
                <th>{t.positions.colAvgEntryPrice}</th>
                <th>{t.positions.colLastPrice}</th>
                <th>{t.positions.colCostAmount}</th>
                <th>{t.positions.colEvalAmount}</th>
                <th>{t.positions.colUnrealizedPnl}</th>
                <th>{t.positions.colUnrealizedPnlPct}</th>
                <th>{t.positions.colRealizedPnl}</th>
                <th>{t.positions.colUpdatedAt}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((position) => {
                const costAmount = multiply(position.avg_entry_price, position.quantity);
                const evalPrice = position.last_price ?? position.avg_entry_price;
                const evalAmount = multiply(evalPrice, position.quantity);
                const unrealizedPnl = Number(position.unrealized_pnl);
                const unrealizedPnlPct = costAmount !== 0 ? (unrealizedPnl / costAmount) * 100 : 0;
                return (
                  <tr key={position.id}>
                    <td>
                      {position.symbol_name
                        ? `${position.symbol_code} (${position.symbol_name})`
                        : position.symbol_code}
                    </td>
                    <td>{position.quantity}</td>
                    <td>{position.avg_entry_price}</td>
                    <td>{position.last_price ?? "-"}</td>
                    <td>{costAmount}</td>
                    <td>{evalAmount}</td>
                    <td className={unrealizedPnl >= 0 ? "value ok" : "value error"}>
                      {position.unrealized_pnl}
                    </td>
                    <td className={unrealizedPnlPct >= 0 ? "value ok" : "value error"}>
                      {unrealizedPnlPct.toFixed(2)}%
                    </td>
                    <td className={Number(position.realized_pnl) >= 0 ? "value ok" : "value error"}>
                      {position.realized_pnl}
                    </td>
                    <td>{formatDateTime(position.updated_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
