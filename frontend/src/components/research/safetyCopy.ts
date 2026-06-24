// C-2.30: 승인 리포트 카드에서 사용하는 안전 안내 문구 상수.
//
// 이 문구들은 백엔드 응답 문자열에 의존하지 않고 프론트엔드 상수로만 렌더링한다.
// (백엔드 문구가 바뀌더라도 사용자에게 보이는 안전 고지는 고정되어야 한다.)

export const SAFETY_COPY = {
  newVersionTesting: "새 버전은 TESTING 상태로 생성됩니다 (실거래·자동매매 아님)",
  previousVersionsKept: "기존 버전은 그대로 유지됩니다 (변경·강등·삭제 없음)",
  autoTradeStaysOff: "자동매매는 켜지지 않습니다 (auto_trade_enabled = false 고정)",
  noRealOrders: "실전 주문은 실행되지 않습니다",
  livePromotionReviewOnly:
    "실전 승격은 '사람이 검토를 승인했다'는 기록일 뿐, 실전 배치가 아닙니다",
  noAutoActive: "ACTIVE 전환은 자동으로 수행되지 않습니다",
} as const;

// "승인하면 이렇게 됩니다" — 전략 제안.
export const STRATEGY_WILL_HAPPEN: readonly string[] = [
  SAFETY_COPY.newVersionTesting,
  SAFETY_COPY.previousVersionsKept,
];

// "승인해도 일어나지 않는 일" — 전략 제안.
export const STRATEGY_WILL_NOT_HAPPEN: readonly string[] = [
  SAFETY_COPY.autoTradeStaysOff,
  SAFETY_COPY.noAutoActive,
  SAFETY_COPY.noRealOrders,
];

// "승인하면 이렇게 됩니다" — 스캐너 제안 (auto_trade 문구 제외).
export const SCANNER_WILL_HAPPEN: readonly string[] = [
  SAFETY_COPY.newVersionTesting,
  SAFETY_COPY.previousVersionsKept,
];

// "승인해도 일어나지 않는 일" — 스캐너 제안 (auto_trade 문구 제외).
export const SCANNER_WILL_NOT_HAPPEN: readonly string[] = [
  SAFETY_COPY.noAutoActive,
  SAFETY_COPY.noRealOrders,
];

// 실전 승격 검토 카드 상단 배너.
export const LIVE_PROMOTION_BANNER =
  "실전 승격은 검토 승인 기록일 뿐입니다. 실거래는 켜지지 않습니다.";

// 실전 승격 카드 "일어나지 않는 일".
export const LIVE_PROMOTION_WILL_NOT_HAPPEN: readonly string[] = [
  SAFETY_COPY.livePromotionReviewOnly,
  SAFETY_COPY.autoTradeStaysOff,
  SAFETY_COPY.noRealOrders,
  SAFETY_COPY.noAutoActive,
];
