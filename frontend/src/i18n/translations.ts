export type Language = "ko" | "en";

export interface Translations {
  nav: {
    dashboard: string;
    strategies: string;
  };
  common: {
    loading: string;
    loadError: string;
    refresh: string;
    buy: string;
    sell: string;
    none: string;
  };
  orderStatus: Record<string, string>;
  schedulerStatus: Record<string, string>;
  dashboard: {
    title: string;
    actions: string;
    runOnce: string;
    syncOrders: string;
  };
  engineStatus: {
    title: string;
    schedulerRunning: string;
    running: string;
    stopped: string;
    registeredJobs: string;
    activeStrategies: string;
    autoTradeEnabled: string;
    lastRunAt: string;
    lastError: string;
    orderSyncLastRunAt: string;
    orderSyncLastError: string;
    warningTitle: string;
    schedulerErrorPrefix: string;
    orderSyncErrorPrefix: string;
    recentFailureWarning: string;
    multipleActiveWarning: (n: number) => string;
    autoTradeWarning: (n: number) => string;
  };
  scheduler: {
    title: string;
    description: string;
    loading: string;
    empty: string;
    colJob: string;
    colStatus: string;
    colStartedAt: string;
    colDuration: string;
    colErrors: string;
    colSummary: string;
    jobLabels: Record<string, string>;
    summaryKeyLabels: Record<string, string>;
    errorCategoryLabels: Record<string, { title: string; description: string }>;
    skippedReasonLabels: Record<string, string>;
    showDetails: string;
    hideDetails: string;
  };
  risk: {
    title: string;
    accountId: string;
    accountIdPlaceholder: string;
    notFound: (id: number) => string;
    emergencyStop: string;
    maxDailyLossAmount: string;
    maxPositionSize: string;
    maxOpenPositions: string;
    maxTradesPerDay: string;
    consecutiveLossLimit: string;
    emergencyStopOn: string;
    emergencyStopOff: string;
    changeFailed: string;
  };
  runOnce: {
    colStrategyVersion: string;
    colSymbol: string;
    colSignal: string;
    colAutoTrade: string;
    colResult: string;
    empty: string;
  };
  signals: {
    title: string;
    description: string;
    empty: string;
    colId: string;
    colSymbol: string;
    colType: string;
    colShortMa: string;
    colLongMa: string;
    colReason: string;
    colGeneratedAt: string;
  };
  trades: {
    title: string;
    description: string;
    empty: string;
    colId: string;
    colSymbol: string;
    colSide: string;
    colOrderStatus: string;
    colBrokerOrder: string;
    colQuantity: string;
    colEntryPrice: string;
    colExitPrice: string;
    colPositionAppliedQty: string;
    colCreatedAt: string;
    colAge: string;
    brokerOrderPresent: string;
    brokerOrderAbsent: string;
    ageMinutes: (n: number) => string;
    unmatchedIndicator: string;
  };
  positions: {
    title: string;
    description: string;
    empty: string;
    colSymbol: string;
    colQuantity: string;
    colAvgEntryPrice: string;
    colLastPrice: string;
    colCostAmount: string;
    colEvalAmount: string;
    colUnrealizedPnl: string;
    colUnrealizedPnlPct: string;
    colRealizedPnl: string;
    colUpdatedAt: string;
  };
  portfolio: {
    title: string;
    positionCount: string;
    totalQuantity: string;
    totalCostAmount: string;
    totalEvalAmount: string;
    totalUnrealizedPnl: string;
    totalUnrealizedPnlPct: string;
    totalRealizedPnl: string;
    totalPnl: string;
    refreshPrices: string;
    refreshing: string;
    lastRefreshedAt: string;
    autoRefresh: string;
    autoRefreshOff: string;
    autoRefresh30s: string;
    autoRefresh60s: string;
    disclaimer: string;
    refreshFailed: string;
    syncFromBroker: string;
    syncing: string;
    syncFailed: string;
    syncResult: (created: number, updated: number, zeroed: number) => string;
    disclaimerHoldings: string;
    disclaimerRealizedPnl: string;
  };
  settings: {
    language: string;
    languageKo: string;
    languageEn: string;
    timezone: string;
    timezoneSeoul: string;
    timezoneBangkok: string;
    timezoneUtc: string;
  };
}

export const translations: Record<Language, Translations> = {
  ko: {
    nav: {
      dashboard: "대시보드",
      strategies: "전략 관리",
    },
    common: {
      loading: "불러오는 중...",
      loadError: "조회 실패",
      refresh: "새로고침",
      buy: "매수",
      sell: "매도",
      none: "-",
    },
    orderStatus: {
      pending: "대기중",
      filled: "체결완료",
      partial: "부분체결",
      cancelled: "취소",
      rejected: "거부",
    },
    schedulerStatus: {
      success: "성공",
      failed: "실패",
      skipped: "건너뜀",
    },
    dashboard: {
      title: "AI 트레이딩 플랫폼 대시보드",
      actions: "실행",
      runOnce: "전략 1회 실행",
      syncOrders: "주문 동기화",
    },
    engineStatus: {
      title: "엔진 상태",
      schedulerRunning: "스케줄러 실행 상태",
      running: "실행중",
      stopped: "정지됨",
      registeredJobs: "등록된 작업",
      activeStrategies: "활성 전략 수",
      autoTradeEnabled: "자동매매 활성화 전략 수",
      lastRunAt: "마지막 실행 시각",
      lastError: "마지막 오류",
      orderSyncLastRunAt: "주문 동기화 마지막 실행 시각",
      orderSyncLastError: "주문 동기화 마지막 오류",
      warningTitle: "운영 경고",
      schedulerErrorPrefix: "스케줄러 오류",
      orderSyncErrorPrefix: "주문 동기화 오류",
      recentFailureWarning: "최근 scheduler 실행 기록 중 실패한 작업이 있습니다.",
      multipleActiveWarning: (n: number) => `활성 전략이 ${n}개 동시에 실행 중입니다.`,
      autoTradeWarning: (n: number) =>
        `자동매매(auto_trade_enabled)가 활성화된 전략이 ${n}개 있습니다.`,
    },
    scheduler: {
      title: "자동 실행 로그",
      description: "전략 실행 작업/주문 체결 동기화 작업이 언제 실행됐고 성공/실패했는지 기록합니다.",
      loading: "불러오는 중...",
      empty: "실행 기록이 없습니다.",
      colJob: "작업",
      colStatus: "상태",
      colStartedAt: "시작 시각",
      colDuration: "소요 시간(ms)",
      colErrors: "오류",
      colSummary: "요약",
      jobLabels: {
        strategy_runner: "전략 실행 작업",
        order_sync: "주문 체결 동기화 작업",
      } as Record<string, string>,
      summaryKeyLabels: {
        versions_run: "실행 전략 수",
        signals_created: "생성 신호 수",
        trades_attempted: "주문 시도 수",
        checked: "확인한 주문 수",
        updated: "갱신된 주문 수",
        matched: "매칭된 주문 수",
        unmatched: "미매칭 주문 수",
        unmatched_order_ids: "미매칭 주문번호",
      } as Record<string, string>,
      errorCategoryLabels: {
        invalid_price_tick: {
          title: "호가 단위 오류",
          description: "주문 가격이 허용된 호가 단위와 맞지 않아 거절되었습니다.",
        },
        token_error: {
          title: "인증 토큰 오류",
          description: "KIS API 인증 토큰을 발급/갱신하는 중 오류가 발생했습니다.",
        },
        rate_limit_or_repeated_call: {
          title: "호출 제한",
          description: "KIS 모의투자 API 호출이 일시적으로 많아 요청이 제한되었습니다. 잠시 후 다시 시도됩니다.",
        },
        market_closed: {
          title: "장 종료",
          description: "모의투자 장 운영 시간이 아니어서 주문/조회가 제한되었습니다.",
        },
        insufficient_balance: {
          title: "잔고 부족",
          description: "주문 가능 금액 또는 보유 수량이 부족합니다.",
        },
        unknown: {
          title: "API 오류",
          description: "KIS API 요청 중 오류가 발생했습니다. 상세 로그를 확인하세요.",
        },
      } as Record<string, { title: string; description: string }>,
      skippedReasonLabels: {
        no_pending_orders: "대기 중인 주문이 없어 건너뜀",
      } as Record<string, string>,
      showDetails: "상세 보기",
      hideDetails: "숨기기",
    },
    risk: {
      title: "리스크 제어",
      accountId: "계정 ID",
      accountIdPlaceholder: "account_id를 입력하세요.",
      notFound: (id: number) => `해당 account_id(${id})의 risk_config가 없습니다.`,
      emergencyStop: "긴급 정지",
      maxDailyLossAmount: "일일 최대 손실 허용액",
      maxPositionSize: "최대 포지션 크기",
      maxOpenPositions: "최대 동시 보유 종목 수",
      maxTradesPerDay: "일일 최대 거래 횟수",
      consecutiveLossLimit: "연속 손실 제한",
      emergencyStopOn: "긴급 정지 ON",
      emergencyStopOff: "긴급 정지 OFF",
      changeFailed: "변경 실패",
    },
    runOnce: {
      colStrategyVersion: "전략 버전",
      colSymbol: "종목코드",
      colSignal: "신호",
      colAutoTrade: "자동매매",
      colResult: "결과",
      empty: "실행할 활성 전략이 없습니다.",
    },
    signals: {
      title: "매매 신호",
      description:
        "전략이 생성한 매수/매도 신호입니다. 실제 주문이 실행됐다는 뜻은 아니며, auto_trade_enabled=false인 전략은 신호만 기록되고 자동 주문은 실행되지 않습니다.",
      empty: "생성된 시그널이 없습니다.",
      colId: "ID",
      colSymbol: "종목코드",
      colType: "신호유형",
      colShortMa: "단기 이동평균",
      colLongMa: "장기 이동평균",
      colReason: "이유",
      colGeneratedAt: "생성 시각",
    },
    trades: {
      title: "주문/거래 기록",
      description: "KIS VTS로 주문이 전송되었거나 주문 기록으로 저장된 실제 거래 시도 내역입니다.",
      empty: "거래 내역이 없습니다.",
      colId: "ID",
      colSymbol: "종목코드",
      colSide: "매매구분",
      colOrderStatus: "주문상태",
      colBrokerOrder: "브로커 주문번호",
      colQuantity: "수량",
      colEntryPrice: "진입가",
      colExitPrice: "청산가",
      colPositionAppliedQty: "포지션 반영 수량",
      colCreatedAt: "생성 시각",
      colAge: "대기 시간",
      brokerOrderPresent: "KIS 주문번호 있음",
      brokerOrderAbsent: "주문 미전송",
      ageMinutes: (n: number) => `${n}분 경과`,
      unmatchedIndicator: "체결조회 미매칭",
    },
    positions: {
      title: "보유 포지션",
      description: "체결 동기화 후 반영된 현재 보유 포지션과 손익입니다.",
      empty: "보유 포지션이 없습니다.",
      colSymbol: "종목코드",
      colQuantity: "보유수량",
      colAvgEntryPrice: "평균단가",
      colLastPrice: "현재가",
      colCostAmount: "매입금액",
      colEvalAmount: "평가금액",
      colUnrealizedPnl: "평가손익",
      colUnrealizedPnlPct: "평가손익률",
      colRealizedPnl: "실현손익",
      colUpdatedAt: "마지막 갱신시간",
    },
    portfolio: {
      title: "포트폴리오 요약",
      positionCount: "총 보유 종목 수",
      totalQuantity: "총 보유 수량",
      totalCostAmount: "총 매입금액",
      totalEvalAmount: "총 평가금액",
      totalUnrealizedPnl: "총 평가손익",
      totalUnrealizedPnlPct: "총 평가손익률",
      totalRealizedPnl: "총 실현손익",
      totalPnl: "총 손익",
      refreshPrices: "현재가 갱신",
      refreshing: "갱신 중...",
      lastRefreshedAt: "마지막 갱신",
      autoRefresh: "자동 갱신",
      autoRefreshOff: "끄기",
      autoRefresh30s: "30초",
      autoRefresh60s: "60초",
      disclaimer: "현재 손익은 마지막 현재가 갱신 기준입니다.",
      refreshFailed: "현재가 갱신 실패",
      syncFromBroker: "KIS 잔고 동기화",
      syncing: "동기화 중...",
      syncFailed: "KIS 잔고 동기화 실패",
      syncResult: (created, updated, zeroed) =>
        `신규 ${created}건, 갱신 ${updated}건, 0으로 정리 ${zeroed}건`,
      disclaimerHoldings: "보유수량과 평균단가는 KIS 잔고 동기화 기준입니다.",
      disclaimerRealizedPnl: "실현손익은 내부 체결 기록 기준이며, KIS 앱과 다를 수 있습니다.",
    },
    settings: {
      language: "언어",
      languageKo: "한국어",
      languageEn: "English",
      timezone: "시간대",
      timezoneSeoul: "한국 시간",
      timezoneBangkok: "태국 시간",
      timezoneUtc: "서버 시간 (UTC)",
    },
  },
  en: {
    nav: {
      dashboard: "Dashboard",
      strategies: "Strategies",
    },
    common: {
      loading: "Loading...",
      loadError: "Failed to load",
      refresh: "Refresh",
      buy: "BUY",
      sell: "SELL",
      none: "-",
    },
    orderStatus: {
      pending: "PENDING",
      filled: "FILLED",
      partial: "PARTIAL",
      cancelled: "CANCELLED",
      rejected: "REJECTED",
    },
    schedulerStatus: {
      success: "SUCCESS",
      failed: "FAILED",
      skipped: "SKIPPED",
    },
    dashboard: {
      title: "AI Trading Platform Dashboard",
      actions: "Actions",
      runOnce: "Run Once",
      syncOrders: "Sync Orders",
    },
    engineStatus: {
      title: "Engine Status",
      schedulerRunning: "Scheduler Running",
      running: "Running",
      stopped: "Stopped",
      registeredJobs: "Registered Jobs",
      activeStrategies: "Active Strategies",
      autoTradeEnabled: "Auto Trade Enabled",
      lastRunAt: "Last Run At",
      lastError: "Last Error",
      orderSyncLastRunAt: "Order Sync Last Run At",
      orderSyncLastError: "Order Sync Last Error",
      warningTitle: "Operational Warnings",
      schedulerErrorPrefix: "Scheduler error",
      orderSyncErrorPrefix: "Order sync error",
      recentFailureWarning: "Some recent scheduler runs have failed.",
      multipleActiveWarning: (n: number) => `${n} active strategies are running at the same time.`,
      autoTradeWarning: (n: number) => `${n} strategies have auto_trade_enabled.`,
    },
    scheduler: {
      title: "Scheduler Logs",
      description: "Records when strategy_runner/order_sync jobs ran and whether they succeeded or failed.",
      loading: "Loading...",
      empty: "No run history.",
      colJob: "Job",
      colStatus: "Status",
      colStartedAt: "Started At",
      colDuration: "Duration (ms)",
      colErrors: "Errors",
      colSummary: "Summary",
      jobLabels: {
        strategy_runner: "Strategy Runner",
        order_sync: "Order Sync",
      } as Record<string, string>,
      summaryKeyLabels: {
        versions_run: "Versions Run",
        signals_created: "Signals Created",
        trades_attempted: "Trades Attempted",
        checked: "Checked",
        updated: "Updated",
        matched: "Matched",
        unmatched: "Unmatched",
        unmatched_order_ids: "Unmatched Order IDs",
      } as Record<string, string>,
      errorCategoryLabels: {
        invalid_price_tick: {
          title: "Invalid Price Tick",
          description: "The order price does not match the allowed tick size and was rejected.",
        },
        token_error: {
          title: "Auth Token Error",
          description: "An error occurred while issuing/refreshing the KIS API auth token.",
        },
        rate_limit_or_repeated_call: {
          title: "Rate Limited",
          description: "KIS paper trading API calls were temporarily rate-limited. The request will be retried shortly.",
        },
        market_closed: {
          title: "Market Closed",
          description: "The paper trading market is not open, so orders/queries are restricted.",
        },
        insufficient_balance: {
          title: "Insufficient Balance",
          description: "Insufficient buying power or holding quantity.",
        },
        unknown: {
          title: "API Error",
          description: "An error occurred while calling the KIS API. Check the detailed logs.",
        },
      } as Record<string, { title: string; description: string }>,
      skippedReasonLabels: {
        no_pending_orders: "Skipped: no pending orders",
      } as Record<string, string>,
      showDetails: "Show details",
      hideDetails: "Hide",
    },
    risk: {
      title: "Risk Controls",
      accountId: "Account ID",
      accountIdPlaceholder: "Enter an account_id.",
      notFound: (id: number) => `No risk_config found for account_id(${id}).`,
      emergencyStop: "Emergency Stop",
      maxDailyLossAmount: "Max Daily Loss Amount",
      maxPositionSize: "Max Position Size",
      maxOpenPositions: "Max Open Positions",
      maxTradesPerDay: "Max Trades Per Day",
      consecutiveLossLimit: "Consecutive Loss Limit",
      emergencyStopOn: "Emergency Stop ON",
      emergencyStopOff: "Emergency Stop OFF",
      changeFailed: "Failed to change",
    },
    runOnce: {
      colStrategyVersion: "Strategy Version",
      colSymbol: "Symbol",
      colSignal: "Signal",
      colAutoTrade: "Auto Trade",
      colResult: "Result",
      empty: "No active strategies to run.",
    },
    signals: {
      title: "Signals",
      description:
        "Buy/sell signals generated by strategies. This does not mean an order was actually executed; if auto_trade_enabled=false, only the signal is recorded and no order is placed.",
      empty: "No signals generated.",
      colId: "ID",
      colSymbol: "Symbol",
      colType: "Type",
      colShortMa: "Short MA",
      colLongMa: "Long MA",
      colReason: "Reason",
      colGeneratedAt: "Generated At",
    },
    trades: {
      title: "Trades",
      description: "Actual order attempts sent to KIS VTS or recorded as trades.",
      empty: "No trades found.",
      colId: "ID",
      colSymbol: "Symbol",
      colSide: "Side",
      colOrderStatus: "Order Status",
      colBrokerOrder: "Broker Order",
      colQuantity: "Quantity",
      colEntryPrice: "Entry Price",
      colExitPrice: "Exit Price",
      colPositionAppliedQty: "Position Applied Qty",
      colCreatedAt: "Created At",
      colAge: "Pending For",
      brokerOrderPresent: "Has KIS order ID",
      brokerOrderAbsent: "Not sent",
      ageMinutes: (n: number) => `${n} min`,
      unmatchedIndicator: "Not matched in fill check",
    },
    positions: {
      title: "Positions",
      description: "Current holdings and PnL reflected after order sync.",
      empty: "No open positions.",
      colSymbol: "Symbol",
      colQuantity: "Quantity",
      colAvgEntryPrice: "Avg Entry Price",
      colLastPrice: "Last Price",
      colCostAmount: "Cost Amount",
      colEvalAmount: "Eval Amount",
      colUnrealizedPnl: "Unrealized PnL",
      colUnrealizedPnlPct: "Unrealized PnL %",
      colRealizedPnl: "Realized PnL",
      colUpdatedAt: "Updated At",
    },
    portfolio: {
      title: "Portfolio Summary",
      positionCount: "Total Positions",
      totalQuantity: "Total Quantity",
      totalCostAmount: "Total Cost Amount",
      totalEvalAmount: "Total Eval Amount",
      totalUnrealizedPnl: "Total Unrealized PnL",
      totalUnrealizedPnlPct: "Total Unrealized PnL %",
      totalRealizedPnl: "Total Realized PnL",
      totalPnl: "Total PnL",
      refreshPrices: "Refresh Prices",
      refreshing: "Refreshing...",
      lastRefreshedAt: "Last Refreshed",
      autoRefresh: "Auto Refresh",
      autoRefreshOff: "Off",
      autoRefresh30s: "30s",
      autoRefresh60s: "60s",
      disclaimer: "PnL reflects prices as of the last price refresh.",
      refreshFailed: "Failed to refresh prices",
      syncFromBroker: "Sync KIS Balance",
      syncing: "Syncing...",
      syncFailed: "Failed to sync KIS balance",
      syncResult: (created, updated, zeroed) =>
        `${created} created, ${updated} updated, ${zeroed} zeroed out`,
      disclaimerHoldings: "Holding quantity and average entry price are based on the last KIS balance sync.",
      disclaimerRealizedPnl: "Realized PnL is based on internal trade records and may differ from the KIS app.",
    },
    settings: {
      language: "Language",
      languageKo: "한국어",
      languageEn: "English",
      timezone: "Timezone",
      timezoneSeoul: "Korea Time",
      timezoneBangkok: "Thailand Time",
      timezoneUtc: "Server Time (UTC)",
    },
  },
};
