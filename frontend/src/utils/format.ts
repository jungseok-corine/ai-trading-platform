const amountFormatter = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 });
const integerFormatter = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 });

type NumericInput = string | number | null | undefined;

/** 금액/가격을 천 단위 콤마와 최대 소수점 2자리로 표시한다. 내부 계산값은 그대로 유지한다. */
export function formatAmount(value: NumericInput): string {
  if (value === null || value === undefined) return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return "-";
  return amountFormatter.format(num);
}

/** 평균단가/현재가 등 가격 표시에 사용한다. */
export const formatPrice = formatAmount;

/** 수량을 정수(천 단위 콤마)로 표시한다. */
export function formatQuantity(value: NumericInput): string {
  if (value === null || value === undefined) return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return "-";
  return integerFormatter.format(num);
}

/** 퍼센트 값을 소수점 둘째 자리까지 표시한다 (예: -0.1290320518 -> "-0.13%"). */
export function formatPercent(value: NumericInput): string {
  if (value === null || value === undefined) return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return "-";
  let rounded = num.toFixed(2);
  if (Number(rounded) === 0) rounded = "0.00";
  return `${rounded}%`;
}
