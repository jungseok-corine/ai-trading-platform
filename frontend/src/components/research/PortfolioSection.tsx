import { useQuery } from "@tanstack/react-query";
import { getPortfolioSummary } from "../../api/research";

function won(n: number): string {
  return `₩${Math.round(n).toLocaleString()}`;
}

function pnl(n: number): string {
  const s = `₩${Math.round(Math.abs(n)).toLocaleString()}`;
  return n >= 0 ? `+${s}` : `-${s}`;
}

export default function PortfolioSection() {
  const { data, isLoading } = useQuery({
    queryKey: ["portfolio-summary"],
    queryFn: getPortfolioSummary,
  });

  return (
    <div className="card">
      <h3>포트폴리오 (보유 포지션·노출)</h3>
      <p className="muted">
        현재 보유 포지션의 시가평가·미실현손익·종목별 노출 비중입니다. 시세는 동기화 잡이 갱신한
        last_price를 사용합니다(read-only 집계).
      </p>

      {isLoading && <p className="muted">불러오는 중…</p>}
      {data && (
        <>
          <p className="action-result value">
            보유 {data.open_positions}종목 · 평가액 {won(data.total_market_value)} ·
            미실현 <strong>{pnl(data.total_unrealized_pnl)}</strong> ·
            실현 {pnl(data.total_realized_pnl)}
          </p>
          {data.positions.length === 0 ? (
            <p className="muted">보유 중인 포지션이 없습니다.</p>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>종목</th><th>수량</th><th>평단</th><th>현재가</th>
                    <th>평가액</th><th>미실현(%)</th><th>노출%</th>
                  </tr>
                </thead>
                <tbody>
                  {data.positions.map((p) => (
                    <tr key={`${p.account_id}/${p.symbol_code}`}>
                      <td>{p.symbol_name ?? p.symbol_code} ({p.symbol_code})</td>
                      <td>{p.quantity.toLocaleString()}</td>
                      <td>{p.avg_entry_price.toLocaleString()}</td>
                      <td>{p.last_price.toLocaleString()}{p.has_price ? "" : " *"}</td>
                      <td>{won(p.market_value)}</td>
                      <td>{pnl(p.unrealized_pnl)}{p.unrealized_pct !== null ? ` (${p.unrealized_pct}%)` : ""}</td>
                      <td>{p.exposure_pct !== null ? `${p.exposure_pct}%` : "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted">* 현재가 미수신 — 평단으로 평가</p>
        </>
      )}
    </div>
  );
}
