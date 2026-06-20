import type { ChartData } from "../../api/research";

// 의존성 없는 SVG 캔들차트 + 매매 마커 (C-2.60, 사람 직관용).
const W = 920;
const H = 420;
const PAD = { top: 16, right: 56, bottom: 28, left: 8 };

export default function TradeChart({ data }: { data: ChartData }) {
  const candles = data.candles;
  if (candles.length === 0) return <p className="muted">표시할 캔들이 없습니다.</p>;

  const prices = candles.flatMap((c) => [c.h, c.l]).concat(data.markers.map((m) => m.price));
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || 1;
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const cw = plotW / candles.length;

  const x = (i: number) => PAD.left + i * cw + cw / 2;
  const y = (p: number) => PAD.top + (1 - (p - min) / span) * plotH;
  const tsIndex = new Map(candles.map((c, i) => [c.ts, i]));

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => min + f * span);
  const xTicks = [0, Math.floor(candles.length / 2), candles.length - 1];

  return (
    <div className="table-wrapper">
      <svg width={W} height={H} style={{ background: "#fff", border: "1px solid #eee" }}>
        {/* y축 그리드 + 가격 라벨 */}
        {yTicks.map((p, k) => (
          <g key={`y${k}`}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(p)} y2={y(p)} stroke="#f0f0f0" />
            <text x={W - PAD.right + 4} y={y(p) + 3} fontSize="10" fill="#888">
              {p.toLocaleString()}
            </text>
          </g>
        ))}
        {/* x축 시간 라벨 */}
        {xTicks.map((i, k) => (
          <text key={`x${k}`} x={x(i)} y={H - 10} fontSize="10" fill="#888" textAnchor="middle">
            {new Date(candles[i].ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </text>
        ))}
        {/* 캔들 */}
        {candles.map((c, i) => {
          const up = c.c >= c.o;
          const color = up ? "#d32f2f" : "#1976d2"; // 한국식: 상승 빨강 / 하락 파랑
          const bodyTop = y(Math.max(c.o, c.c));
          const bodyH = Math.max(1, Math.abs(y(c.o) - y(c.c)));
          const bw = Math.max(1, cw * 0.6);
          return (
            <g key={i}>
              <line x1={x(i)} x2={x(i)} y1={y(c.h)} y2={y(c.l)} stroke={color} />
              <rect x={x(i) - bw / 2} y={bodyTop} width={bw} height={bodyH} fill={color} />
            </g>
          );
        })}
        {/* 매매 마커 */}
        {data.markers.map((m, k) => {
          const i = tsIndex.get(m.ts) ?? nearestIndex(candles, m.ts);
          const mx = x(i);
          const my = y(m.price);
          const buy = m.side === "buy";
          const color = buy ? "#e64a19" : "#0288d1";
          const tri = buy ? `${mx},${my + 12} ${mx - 6},${my + 22} ${mx + 6},${my + 22}`
                          : `${mx},${my - 12} ${mx - 6},${my - 22} ${mx + 6},${my - 22}`;
          return (
            <g key={`m${k}`}>
              <circle cx={mx} cy={my} r={3} fill={m.kind === "entry" ? color : "#fff"}
                stroke={color} strokeWidth={1.5} />
              <polygon points={tri} fill={m.kind === "entry" ? color : "none"}
                stroke={color} strokeWidth={1.2} />
            </g>
          );
        })}
      </svg>
      <p className="muted" style={{ fontSize: 12 }}>
        캔들: 상승=빨강/하락=파랑 · 마커: ▲매수/▼매도, 채움=진입/빈=청산 ·
        {data.symbol_code} {data.trading_day} ({candles.length}봉)
      </p>
    </div>
  );
}

function nearestIndex(candles: { ts: string }[], ts: string): number {
  const target = new Date(ts).getTime();
  let best = 0;
  let bestDiff = Infinity;
  candles.forEach((c, i) => {
    const d = Math.abs(new Date(c.ts).getTime() - target);
    if (d < bestDiff) {
      bestDiff = d;
      best = i;
    }
  });
  return best;
}
