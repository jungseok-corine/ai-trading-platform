export type Language = "ko" | "en";

export interface Translations {
  nav: {
    dashboard: string;
    strategies: string;
    watchlists: string;
    research: string;
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
    manyActiveStrategiesWarning: (n: number) => string;
    autoTradeWarning: (n: number) => string;
    autoTradeStrongWarning: (n: number) => string;
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
    executionsTitle: string;
    executionOrderId: string;
    executionFilledQuantity: string;
    executionFilledPrice: string;
  };
  schedulerSettings: {
    title: string;
    description: string;
    strategyInterval: string;
    orderSyncInterval: string;
    unitSeconds: string;
    minIntervalHint: string;
    save: string;
    saving: string;
    saveSuccess: string;
    saveFailed: string;
    invalidInterval: (min: number) => string;
    updatedAt: string;
  };
  autonomousJobs: {
    title: string;
    description: string;
    colJob: string;
    colSchedule: string;
    colStatus: string;
    colActions: string;
    on: string;
    off: string;
    turnOn: string;
    turnOff: string;
    runNow: string;
    runTriggered: string;
    lastRun: string;
    runningNow: string;
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
    colMarket: string;
    colType: string;
    colSignalPrice: string;
    colShortMa: string;
    colLongMa: string;
    colReason: string;
    colGeneratedAt: string;
    filterSymbol: string;
    filterType: string;
    filterDateFrom: string;
    filterDateTo: string;
    filterAll: string;
    filterBuy: string;
    filterSell: string;
    pagePrev: string;
    pageNext: string;
    pageInfo: (page: number, total: number) => string;
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
  watchlists: {
    title: string;
    description: string;
    empty: string;
    colId: string;
    colName: string;
    colDescription: string;
    colEnabled: string;
    colSymbolCount: string;
    enabledYes: string;
    enabledNo: string;
    createTitle: string;
    name: string;
    namePlaceholder: string;
    create: string;
    createFailed: string;
    selectWatchlistPrompt: string;
    symbolsTitle: string;
    symbolsEmpty: string;
    colSymbolCode: string;
    colSymbolName: string;
    colMarket: string;
    colNote: string;
    colActions: string;
    addSymbolTitle: string;
    symbolCode: string;
    symbolCodePlaceholder: string;
    symbolName: string;
    market: string;
    exchange: string;
    note: string;
    addSymbol: string;
    addSymbolFailed: string;
    duplicateSymbol: string;
    enable: string;
    disable: string;
    delete: string;
    deleteFailed: string;
    bulkCreateTitle: string;
    bulkCreateDescription: string;
    selectStrategy: string;
    selectStrategyPlaceholder: string;
    bulkCreate: string;
    bulkCreateFailed: string;
    bulkCreateAutoTradeBlocked: string;
    bulkResultTitle: string;
    bulkResultCreated: string;
    bulkResultSkipped: string;
    bulkResultReason: Record<string, string>;
    autoTradeBulkDisabledHint: string;
  };
  signalOutcome: {
    panelTitle: string;
    showOutcome: string;
    hideOutcome: string;
    entryPrice: string;
    mfe: string;
    mae: string;
    colHorizonMin: string;
    colDirectional: string;
    colWin: string;
    win: string;
    loss: string;
    noData: string;
    na: string;
    refresh: string;
    summaryTitle: string;
    summaryDescription: string;
    analyzedCount: string;
    skippedCount: string;
    colCount: string;
    colWinRate: string;
    colAvgReturn: string;
    noSummary: string;
  };
  performance: {
    showPerformance: string;
    hidePerformance: string;
    refresh: string;
    loading: string;
    loadError: string;
    totalSignals: string;
    analyzedSignals: string;
    skippedSignals: string;
    horizonTitle: string;
    colHorizon: string;
    colCount: string;
    colWinRate: string;
    colAvgDirectional: string;
    colMfe: string;
    colMae: string;
    signalTypeTitle: string;
    colSignalType: string;
    colSignalCount: string;
    colAnalyzedCount: string;
    colWinRate5m: string;
    colAvgDir5m: string;
    symbolTitle: string;
    colSymbol: string;
    tradingTitle: string;
    tradeCount: string;
    filledCount: string;
    totalPnl: string;
    winTrades: string;
    lossTrades: string;
    noPnlData: string;
    noSignalData: string;
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
  aiAnalysis: {
    sectionTitle: string;
    safetyNote: string;
    safetyNote2: string;
    providerTitle: string;
    statusAvailable: string;
    statusMissingConfig: string;
    statusNotImplemented: string;
    runFormTitle: string;
    labelPromptType: string;
    labelMode: string;
    labelProvider: string;
    labelSecondaryProvider: string;
    labelEnableCritique: string;
    labelEnableSynthesis: string;
    btnRun: string;
    btnRunning: string;
    btnRefresh: string;
    btnShowRuns: string;
    btnHideRuns: string;
    warningMissingConfig: string;
    runListTitle: string;
    runListEmpty: string;
    runListLoading: string;
    colRunId: string;
    colMode: string;
    colStatus: string;
    colProvider: string;
    colPromptType: string;
    colCreatedAt: string;
    colActions: string;
    btnDetail: string;
    btnHideDetail: string;
    detailTitle: string;
    detailStatus: string;
    detailError: string;
    detailInputHash: string;
    detailResponses: string;
    roleLabel: string;
    providerLabel: string;
    modelLabel: string;
    tokensLabel: string;
    latencyLabel: string;
    finishLabel: string;
    contentLabel: string;
    errorLabel: string;
    warnLengthTruncated: string;
    loadError: string;
    createError: string;
    runningLongNotice: string;
    elapsedSeconds: (n: number) => string;
    refreshRuns: string;
    refreshFailed: string;
    requestMayStillBeRunning: string;
    providerMissingConfig: (provider: string) => string;
    lengthWarningImpact: (role: string) => string;
  };
  strategyParams: {
    labelStrategyType: string;
    labelSymbolCode: string;
    labelShortWindow: string;
    labelLongWindow: string;
    labelQuantity: string;
    labelQuantityMode: string;
    quantityModeFixed: string;
    quantityModeCashAmount: string;
    quantityModeCashPct: string;
    labelCashAmount: string;
    labelCashPct: string;
    labelTimeframe: string;
    labelAccountId: string;
    labelEnabled: string;
    labelExitOnClose: string;
    hintExitOnClose: string;
    labelVolumeWindow: string;
    labelVolumeMultiplier: string;
    strategyTypeMovingAverage: string;
    strategyTypeVolumeConfirmed: string;
    strategyTypeFlowConfirmed: string;
    errorLongWindowGtShort: string;
    errorVolumeWindowGt0: string;
    errorVolumeMultiplierGt0: string;
    hintAutoTrade: string;
    labelFlowLookbackDays: string;
    labelMaxFlowAgeDays: string;
    labelFlowMode: string;
    labelRequireFlowData: string;
    flowModeForeignOrInstitution: string;
    flowModeForeignAndInstitution: string;
    flowModeSmartMoneyVsRetail: string;
    hintFlowData: string;
    errorFlowLookbackDaysGt0: string;
    errorMaxFlowAgeDaysGt0: string;
    strategyTypeRsiReversion: string;
    strategyTypeMacdTrend: string;
    strategyTypeBreakoutHigh: string;
    strategyTypePullbackTrend: string;
    labelUniverse: string;
    universeNone: string;
    universeScannerCandidates: string;
    universeWatchlist: string;
    labelUniverseMarket: string;
    universeMarketAll: string;
    hintUniverse: string;
    labelRsiPeriod: string;
    labelOversold: string;
    labelOverbought: string;
    labelExitMode: string;
    exitModeOverbought: string;
    exitModeMidline: string;
    labelFastPeriod: string;
    labelSlowPeriod: string;
    labelSignalPeriod: string;
    labelRequireAboveZero: string;
    labelBreakoutLookback: string;
    labelExitLookback: string;
    labelVolumeConfirm: string;
    labelSurgeLookback: string;
    labelSurgeThresholdPct: string;
    labelExitDropPct: string;
    labelMarket: string;
    marketKr: string;
    marketUs: string;
    labelExchange: string;
  };
}

export const translations: Record<Language, Translations> = {
  ko: {
    nav: {
      dashboard: "대시보드",
      strategies: "전략 관리",
      watchlists: "관심종목",
      research: "연구소",
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
      manyActiveStrategiesWarning: (n: number) =>
        `활성(active/testing) 전략 버전이 ${n}개입니다. 종목이 늘어날수록 스케줄러 부하와 KIS API 호출량이 증가하니 확인하세요.`,
      autoTradeWarning: (n: number) =>
        `자동매매(auto_trade_enabled)가 활성화된 전략이 ${n}개 있습니다.`,
      autoTradeStrongWarning: (n: number) =>
        `자동매매(auto_trade_enabled)가 활성화된 전략이 ${n}개입니다. 동시에 여러 종목이 자동주문될 수 있으니 반드시 확인하세요.`,
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
        strategy_runner: "전략 실행기",
        order_sync: "주문/체결 동기화",
        trading_state_sync: "거래 상태 동기화",
      } as Record<string, string>,
      summaryKeyLabels: {
        versions_run: "실행 전략 수",
        versions_succeeded: "성공 전략 수",
        versions_failed: "실패 전략 수",
        failed_symbols: "실패 종목",
        signals_created: "생성 신호 수",
        trades_attempted: "주문 시도 수",
        checked: "확인한 주문 수",
        updated: "갱신된 주문 수",
        matched: "매칭된 주문 수",
        unmatched: "미매칭 주문 수",
        unmatched_order_ids: "미매칭 주문번호",
        stale_cancelled: "자동취소(stale)",
        stale_pending_requires_review: "실전 검토 필요",
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
        connection_timeout: {
          title: "연결 타임아웃",
          description: "KIS API 서버 응답 대기 중 시간이 초과되었습니다. 네트워크 또는 KIS 서버 상태를 확인하세요.",
        },
        server_disconnect: {
          title: "서버 연결 끊김",
          description: "KIS API 서버가 응답 없이 연결을 종료했습니다. 잠시 후 자동으로 재시도됩니다.",
        },
        network_error: {
          title: "네트워크 오류",
          description: "KIS API 서버와의 통신 중 네트워크 오류가 발생했습니다.",
        },
      } as Record<string, { title: string; description: string }>,
      skippedReasonLabels: {
        no_pending_orders: "대기 중인 주문이 없어 건너뜀",
        no_active_orders: "모든 stale 주문 처리 완료 — 당일 대기 주문 없음",
      } as Record<string, string>,
      showDetails: "상세 보기",
      hideDetails: "숨기기",
      executionsTitle: "KIS 체결 내역",
      executionOrderId: "주문번호",
      executionFilledQuantity: "체결수량",
      executionFilledPrice: "체결가",
    },
    schedulerSettings: {
      title: "스케줄러 주기 설정",
      description: "전략 실행 작업과 주문 체결 동기화 작업의 실행 주기를 설정합니다.",
      strategyInterval: "전략 실행 주기",
      orderSyncInterval: "주문 동기화 주기",
      unitSeconds: "초",
      minIntervalHint: "KIS 모의투자 API 호출 제한을 고려해 60초 이상 권장",
      save: "저장",
      saving: "저장 중...",
      saveSuccess: "저장되었습니다.",
      saveFailed: "저장 실패",
      invalidInterval: (min: number) => `${min}초 이상으로 설정해야 합니다.`,
      updatedAt: "마지막 변경 시각",
    },
    autonomousJobs: {
      title: "자율 잡 제어판",
      description: "장마감 후 AI 분석·제안 등 자율 잡을 웹에서 켜고 끄거나 즉시 실행합니다. 설정은 DB에 저장되어 .env를 못 만지는 환경에서도 유지됩니다. 기본값은 모두 OFF이며, 켜도 실거래는 일어나지 않습니다.",
      colJob: "잡",
      colSchedule: "주기",
      colStatus: "상태",
      colActions: "동작",
      on: "ON",
      off: "OFF",
      turnOn: "켜기",
      turnOff: "끄기",
      runNow: "지금 실행",
      runTriggered: "실행을 시작했습니다.",
      lastRun: "마지막 실행",
      runningNow: "실행 중",
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
      colMarket: "시장",
      colType: "신호유형",
      colSignalPrice: "시그널 발생가",
      colShortMa: "단기 이동평균",
      colLongMa: "장기 이동평균",
      colReason: "이유",
      colGeneratedAt: "생성 시각",
      filterSymbol: "종목 필터",
      filterType: "신호유형",
      filterDateFrom: "시작일",
      filterDateTo: "종료일",
      filterAll: "전체",
      filterBuy: "매수",
      filterSell: "매도",
      pagePrev: "이전",
      pageNext: "다음",
      pageInfo: (page: number, total: number) => `${page}페이지 · ${total}건`,
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
      positionCount: "보유 종목 수",
      totalQuantity: "보유 수량 합계",
      totalCostAmount: "보유 매입금액",
      totalEvalAmount: "보유 평가금액",
      totalUnrealizedPnl: "보유 평가손익",
      totalUnrealizedPnlPct: "보유 평가손익률",
      totalRealizedPnl: "누적 실현손익",
      totalPnl: "총 거래손익",
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
    watchlists: {
      title: "관심종목 목록",
      description: "여러 종목을 묶어 관리하고, 한 번에 전략 버전을 생성할 수 있습니다.",
      empty: "생성된 관심종목 목록이 없습니다.",
      colId: "ID",
      colName: "이름",
      colDescription: "설명",
      colEnabled: "활성",
      colSymbolCount: "종목 수",
      enabledYes: "활성",
      enabledNo: "비활성",
      createTitle: "새 관심종목 목록 생성",
      name: "이름",
      namePlaceholder: "예: 코스피 대형주",
      create: "생성",
      createFailed: "생성 실패",
      selectWatchlistPrompt: "관심종목 목록을 선택하세요.",
      symbolsTitle: "종목 목록",
      symbolsEmpty: "등록된 종목이 없습니다.",
      colSymbolCode: "종목코드",
      colSymbolName: "종목명",
      colMarket: "시장",
      colNote: "메모",
      colActions: "작업",
      addSymbolTitle: "종목 추가",
      symbolCode: "종목코드",
      symbolCodePlaceholder: "예: 005930 / AAPL",
      symbolName: "종목명",
      market: "시장",
      exchange: "거래소",
      note: "메모",
      addSymbol: "추가",
      addSymbolFailed: "추가 실패",
      duplicateSymbol: "이미 등록된 종목코드입니다.",
      enable: "활성화",
      disable: "비활성화",
      delete: "삭제",
      deleteFailed: "삭제 실패",
      bulkCreateTitle: "전략 버전 일괄 생성",
      bulkCreateDescription:
        "활성화된 종목마다 선택한 전략에 strategy_version을 하나씩 생성합니다. auto_trade_enabled는 항상 false로 생성되며, 자동매매는 생성 후 개별 전략 버전 화면에서 하나씩 켜야 합니다.",
      selectStrategy: "전략 선택",
      selectStrategyPlaceholder: "전략을 선택하세요",
      bulkCreate: "전략 버전 생성",
      bulkCreateFailed: "생성 실패",
      bulkCreateAutoTradeBlocked: "bulk 생성에서는 auto_trade_enabled=true를 사용할 수 없습니다.",
      bulkResultTitle: "생성 결과",
      bulkResultCreated: "생성됨",
      bulkResultSkipped: "건너뜀",
      bulkResultReason: {
        duplicate_symbol_version_exists: "동일 종목의 strategy_version이 이미 존재함",
      } as Record<string, string>,
      autoTradeBulkDisabledHint: "자동매매는 이 화면에서 켤 수 없습니다. 전략 관리 화면에서 개별적으로 설정하세요.",
    },
    signalOutcome: {
      panelTitle: "신호 결과",
      showOutcome: "결과 보기",
      hideOutcome: "닫기",
      entryPrice: "진입가",
      mfe: "최대유리",
      mae: "최대불리",
      colHorizonMin: "분",
      colDirectional: "방향수익",
      colWin: "승패",
      win: "승",
      loss: "패",
      noData: "market_data 없음",
      na: "N/A",
      refresh: "새로고침",
      summaryTitle: "신호 성과 요약",
      summaryDescription: "최근 신호 발생 이후 실제 가격 반응을 집계합니다. 방향수익은 BUY/SELL 방향 기준으로 양수=유리, 음수=불리입니다.",
      analyzedCount: "분석 완료",
      skippedCount: "데이터 부족",
      colCount: "건수",
      colWinRate: "승률",
      colAvgReturn: "평균 방향수익",
      noSummary: "분석된 신호가 없습니다.",
    },
    performance: {
      showPerformance: "성과 보기",
      hidePerformance: "닫기",
      refresh: "새로고침",
      loading: "분석 중...",
      loadError: "성과 데이터 조회 실패",
      totalSignals: "총 신호",
      analyzedSignals: "분석 완료",
      skippedSignals: "데이터 부족",
      horizonTitle: "시간 경과별 성과",
      colHorizon: "경과",
      colCount: "건수",
      colWinRate: "승률",
      colAvgDirectional: "평균 방향수익",
      colMfe: "평균 MFE",
      colMae: "평균 MAE",
      signalTypeTitle: "신호 유형별",
      colSignalType: "신호 유형",
      colSignalCount: "신호 수",
      colAnalyzedCount: "분석 수",
      colWinRate5m: "5분 승률",
      colAvgDir5m: "5분 방향수익",
      symbolTitle: "종목별",
      colSymbol: "종목코드",
      tradingTitle: "실제 체결 성과",
      tradeCount: "주문 수",
      filledCount: "체결 수",
      totalPnl: "실현 손익",
      winTrades: "수익 체결",
      lossTrades: "손실 체결",
      noPnlData: "실현 손익 데이터 부족",
      noSignalData: "분석된 신호가 없습니다.",
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
    aiAnalysis: {
      sectionTitle: "AI 분석",
      safetyNote: "AI 분석은 연구·검토 목적으로만 사용됩니다.",
      safetyNote2: "매매 주문을 자동으로 실행하거나 전략을 변경하지 않습니다.",
      providerTitle: "AI Provider 상태",
      statusAvailable: "사용 가능",
      statusMissingConfig: "API 키 미설정",
      statusNotImplemented: "미구현",
      runFormTitle: "분석 실행",
      labelPromptType: "분석 유형",
      labelMode: "모드",
      labelProvider: "Primary Provider",
      labelSecondaryProvider: "Secondary Provider",
      labelEnableCritique: "상호 비판 (Critique)",
      labelEnableSynthesis: "종합 (Synthesis)",
      btnRun: "분석 실행",
      btnRunning: "실행 중...",
      btnRefresh: "새로고침",
      btnShowRuns: "분석 기록",
      btnHideRuns: "닫기",
      warningMissingConfig: "선택한 provider의 API 키가 설정되지 않았습니다. .env를 확인하세요.",
      runListTitle: "분석 기록",
      runListEmpty: "분석 기록이 없습니다.",
      runListLoading: "불러오는 중...",
      colRunId: "ID",
      colMode: "모드",
      colStatus: "상태",
      colProvider: "Provider",
      colPromptType: "유형",
      colCreatedAt: "생성시각",
      colActions: "상세",
      btnDetail: "보기",
      btnHideDetail: "닫기",
      detailTitle: "분석 결과",
      detailStatus: "상태",
      detailError: "오류",
      detailInputHash: "Input Hash",
      detailResponses: "응답",
      roleLabel: "역할",
      providerLabel: "Provider",
      modelLabel: "모델",
      tokensLabel: "토큰",
      latencyLabel: "지연",
      finishLabel: "종료 이유",
      contentLabel: "내용",
      errorLabel: "오류",
      warnLengthTruncated: "응답이 토큰 제한으로 잘렸습니다. max token 설정을 늘리거나 prompt를 줄이세요.",
      loadError: "분석 기록 조회 실패",
      createError: "분석 실행 실패",
      runningLongNotice: "분석에는 1~2분이 걸릴 수 있습니다. 잠시 기다려 주세요.",
      elapsedSeconds: (n: number) => `${n}초 경과`,
      refreshRuns: "기록 새로고침",
      refreshFailed: "새로고침 실패",
      requestMayStillBeRunning: "분석이 서버에서 계속 진행 중일 수 있습니다. 기록을 새로고침해 확인하세요.",
      providerMissingConfig: (provider: string) => `${provider} API 키가 설정되지 않았습니다. .env를 확인하세요.`,
      lengthWarningImpact: (role: string) => `${role} 응답이 토큰 제한으로 잘렸습니다. critique/synthesis 품질이 낮아질 수 있습니다.`,
    },
    strategyParams: {
      labelStrategyType: "전략 타입",
      labelSymbolCode: "종목 코드",
      labelShortWindow: "단기 이동평균 기간",
      labelLongWindow: "장기 이동평균 기간",
      labelQuantity: "주문 수량",
      labelQuantityMode: "수량 방식",
      quantityModeFixed: "고정 수량",
      quantityModeCashAmount: "1회 투입 금액",
      quantityModeCashPct: "가용현금 %",
      labelCashAmount: "1회 투입 금액 (원/USD)",
      labelCashPct: "가용현금 비율 (%)",
      labelTimeframe: "타임프레임",
      labelAccountId: "계정 ID",
      labelEnabled: "활성화",
      labelExitOnClose: "종가 청산 (장 마감 동시호가)",
      hintExitOnClose:
        "켜면 정규장 마감 동시호가(15:20~15:30)에 당일 포지션을 종가로 청산하는 매도 신호를 냅니다. 인트라데이 전략의 오버나잇 보유 방지용.",
      labelVolumeWindow: "거래량 SMA 기간",
      labelVolumeMultiplier: "거래량 배수",
      strategyTypeMovingAverage: "이동평균 교차",
      strategyTypeVolumeConfirmed: "거래량 확인 MA 교차",
      strategyTypeFlowConfirmed: "수급 확인 거래량 MA 교차",
      errorLongWindowGtShort: "장기 기간은 단기 기간보다 커야 합니다.",
      errorVolumeWindowGt0: "거래량 기간은 1 이상이어야 합니다.",
      errorVolumeMultiplierGt0: "거래량 배수는 0보다 커야 합니다.",
      hintAutoTrade:
        "auto_trade_enabled가 OFF이면 신호(Signal)만 생성되어 기록되고, 실제 KIS 주문은 실행되지 않습니다. ON으로 설정하면 RiskManager 검증을 통과한 신호에 한해 자동으로 주문이 전송됩니다.",
      labelFlowLookbackDays: "수급 조회 기간 (일)",
      labelMaxFlowAgeDays: "수급 최대 허용 경과일",
      labelFlowMode: "수급 필터 모드",
      labelRequireFlowData: "수급 데이터 필수 여부",
      flowModeForeignOrInstitution: "외국인 또는 기관 순매수",
      flowModeForeignAndInstitution: "외국인 및 기관 순매수",
      flowModeSmartMoneyVsRetail: "스마트머니 vs 개인 (연구용 휴리스틱)",
      hintFlowData:
        "수급 데이터는 일별 확정 데이터이며 실시간 매수세/매도세가 아닙니다. 당일 수급은 장마감 후 확정되므로 전일 이하 데이터만 사용됩니다.",
      errorFlowLookbackDaysGt0: "수급 조회 기간은 1일 이상이어야 합니다.",
      errorMaxFlowAgeDaysGt0: "수급 최대 허용 경과일은 1일 이상이어야 합니다.",
      strategyTypeRsiReversion: "RSI 평균회귀",
      strategyTypeMacdTrend: "MACD 추세추종",
      strategyTypeBreakoutHigh: "전고점 돌파",
      strategyTypePullbackTrend: "눌림목 매수",
      labelUniverse: "유니버스 (종목 자동 선택)",
      labelUniverseMarket: "유니버스 시장 필터",
      universeMarketAll: "전체 (KR+US)",
      universeNone: "없음 (단일 종목)",
      universeScannerCandidates: "스캐너 후보",
      universeWatchlist: "관심종목",
      hintUniverse:
        "유니버스를 선택하면 종목을 하나씩 지정하지 않아도 스캐너 후보/관심종목 전체에 전략을 돌려 신호를 기록합니다(신호 생성 전용, 자동매매 불가).",
      labelRsiPeriod: "RSI 기간",
      labelOversold: "과매도 기준",
      labelOverbought: "과매수 기준",
      labelExitMode: "청산 모드",
      exitModeOverbought: "과열 시 (overbought)",
      exitModeMidline: "중심선 회귀 (midline 50)",
      labelFastPeriod: "단기 EMA 기간",
      labelSlowPeriod: "장기 EMA 기간",
      labelSignalPeriod: "시그널선 기간",
      labelRequireAboveZero: "0선 위에서만 매수",
      labelBreakoutLookback: "돌파 비교 구간 (봉)",
      labelExitLookback: "이탈 비교 구간 (봉)",
      labelSurgeLookback: "모멘텀 측정 구간 (봉)",
      labelSurgeThresholdPct: "급등 진입 기준 (%)",
      labelExitDropPct: "모멘텀 소멸 청산 (%)",
      labelVolumeConfirm: "거래량 확인 사용",
      labelMarket: "시장",
      marketKr: "국내 (KR)",
      marketUs: "미국 (US)",
      labelExchange: "거래소 (미국)",
    },
  },
  en: {
    nav: {
      dashboard: "Dashboard",
      strategies: "Strategies",
      watchlists: "Watchlists",
      research: "Research Lab",
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
      manyActiveStrategiesWarning: (n: number) =>
        `There are ${n} active/testing strategy versions. As the number of symbols grows, scheduler load and KIS API call volume increase - please review.`,
      autoTradeWarning: (n: number) => `${n} strategies have auto_trade_enabled.`,
      autoTradeStrongWarning: (n: number) =>
        `${n} strategies have auto_trade_enabled. Multiple symbols may be auto-traded at the same time - please review carefully.`,
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
        order_sync: "Order/Fill Sync",
        trading_state_sync: "Trading State Sync",
      } as Record<string, string>,
      summaryKeyLabels: {
        versions_run: "Versions Run",
        versions_succeeded: "Versions Succeeded",
        versions_failed: "Versions Failed",
        failed_symbols: "Failed Symbols",
        signals_created: "Signals Created",
        trades_attempted: "Trades Attempted",
        checked: "Checked",
        updated: "Updated",
        matched: "Matched",
        unmatched: "Unmatched",
        unmatched_order_ids: "Unmatched Order IDs",
        stale_cancelled: "Stale Auto-Cancelled",
        stale_pending_requires_review: "Live Review Required",
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
        connection_timeout: {
          title: "Connection Timeout",
          description: "Timed out waiting for a response from the KIS API server. Check your network or KIS server status.",
        },
        server_disconnect: {
          title: "Server Disconnected",
          description: "The KIS API server closed the connection without sending a response. Will retry automatically.",
        },
        network_error: {
          title: "Network Error",
          description: "A network error occurred while communicating with the KIS API server.",
        },
      } as Record<string, { title: string; description: string }>,
      skippedReasonLabels: {
        no_pending_orders: "Skipped: no pending orders",
        no_active_orders: "All stale orders resolved — no active orders today",
      } as Record<string, string>,
      showDetails: "Show details",
      hideDetails: "Hide",
      executionsTitle: "KIS Execution History",
      executionOrderId: "Order ID",
      executionFilledQuantity: "Filled Qty",
      executionFilledPrice: "Filled Price",
    },
    schedulerSettings: {
      title: "Scheduler Interval Settings",
      description: "Configure how often the strategy runner and order sync jobs run.",
      strategyInterval: "Strategy Runner Interval",
      orderSyncInterval: "Order Sync Interval",
      unitSeconds: "sec",
      minIntervalHint: "60 seconds or more is recommended due to KIS paper trading API rate limits",
      save: "Save",
      saving: "Saving...",
      saveSuccess: "Saved.",
      saveFailed: "Save failed",
      invalidInterval: (min: number) => `Must be ${min} seconds or more.`,
      updatedAt: "Last Updated",
    },
    autonomousJobs: {
      title: "Autonomous Jobs Control",
      description: "Turn autonomous jobs (post-close AI analysis, proposals, etc.) on/off or run them now from the web. Settings persist in the DB so they survive restarts and work even when you can't edit .env. All default to OFF, and enabling them does not place any real orders.",
      colJob: "Job",
      colSchedule: "Schedule",
      colStatus: "Status",
      colActions: "Actions",
      on: "ON",
      off: "OFF",
      turnOn: "Turn on",
      turnOff: "Turn off",
      runNow: "Run now",
      runTriggered: "Run started.",
      lastRun: "Last run",
      runningNow: "running",
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
      colMarket: "Market",
      colType: "Type",
      colSignalPrice: "Signal Price",
      colShortMa: "Short MA",
      colLongMa: "Long MA",
      colReason: "Reason",
      colGeneratedAt: "Generated At",
      filterSymbol: "Symbol filter",
      filterType: "Signal type",
      filterDateFrom: "From",
      filterDateTo: "To",
      filterAll: "All",
      filterBuy: "Buy",
      filterSell: "Sell",
      pagePrev: "Prev",
      pageNext: "Next",
      pageInfo: (page: number, total: number) => `Page ${page} · ${total} items`,
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
      positionCount: "Open Positions",
      totalQuantity: "Total Quantity (Held)",
      totalCostAmount: "Cost Basis (Held)",
      totalEvalAmount: "Market Value (Held)",
      totalUnrealizedPnl: "Unrealized PnL",
      totalUnrealizedPnlPct: "Unrealized PnL %",
      totalRealizedPnl: "Realized PnL (Cumulative)",
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
    watchlists: {
      title: "Watchlists",
      description: "Group multiple symbols and create strategy versions for all of them at once.",
      empty: "No watchlists created yet.",
      colId: "ID",
      colName: "Name",
      colDescription: "Description",
      colEnabled: "Enabled",
      colSymbolCount: "Symbols",
      enabledYes: "Enabled",
      enabledNo: "Disabled",
      createTitle: "Create Watchlist",
      name: "Name",
      namePlaceholder: "e.g. KOSPI Large Caps",
      create: "Create",
      createFailed: "Failed to create",
      selectWatchlistPrompt: "Select a watchlist.",
      symbolsTitle: "Symbols",
      symbolsEmpty: "No symbols registered.",
      colSymbolCode: "Symbol Code",
      colSymbolName: "Symbol Name",
      colMarket: "Market",
      colNote: "Note",
      colActions: "Actions",
      addSymbolTitle: "Add Symbol",
      symbolCode: "Symbol Code",
      symbolCodePlaceholder: "e.g. 005930 / AAPL",
      symbolName: "Symbol Name",
      market: "Market",
      exchange: "Exchange",
      note: "Note",
      addSymbol: "Add",
      addSymbolFailed: "Failed to add",
      duplicateSymbol: "This symbol code is already registered.",
      enable: "Enable",
      disable: "Disable",
      delete: "Delete",
      deleteFailed: "Failed to delete",
      bulkCreateTitle: "Bulk Create Strategy Versions",
      bulkCreateDescription:
        "Creates one strategy_version per enabled symbol for the selected strategy. auto_trade_enabled is always created as false; enable auto trading individually afterwards on the strategy version screen.",
      selectStrategy: "Strategy",
      selectStrategyPlaceholder: "Select a strategy",
      bulkCreate: "Create Strategy Versions",
      bulkCreateFailed: "Failed to create",
      bulkCreateAutoTradeBlocked: "Bulk creation does not allow auto_trade_enabled=true.",
      bulkResultTitle: "Result",
      bulkResultCreated: "Created",
      bulkResultSkipped: "Skipped",
      bulkResultReason: {
        duplicate_symbol_version_exists: "A strategy_version for this symbol already exists",
      } as Record<string, string>,
      autoTradeBulkDisabledHint: "Auto trading cannot be enabled here. Set it individually on the Strategies page.",
    },
    signalOutcome: {
      panelTitle: "Outcome",
      showOutcome: "View Outcome",
      hideOutcome: "Hide",
      entryPrice: "Entry",
      mfe: "MFE",
      mae: "MAE",
      colHorizonMin: "min",
      colDirectional: "Dir. Return",
      colWin: "W/L",
      win: "W",
      loss: "L",
      noData: "No market_data",
      na: "N/A",
      refresh: "Refresh",
      summaryTitle: "Signal Outcome Summary",
      summaryDescription: "Aggregates actual price reactions after recent signals. Directional return is positive when price moves in the signal direction.",
      analyzedCount: "Analyzed",
      skippedCount: "No Data",
      colCount: "Count",
      colWinRate: "Win Rate",
      colAvgReturn: "Avg Dir. Return",
      noSummary: "No analyzed signals yet.",
    },
    performance: {
      showPerformance: "Performance",
      hidePerformance: "Close",
      refresh: "Refresh",
      loading: "Analyzing...",
      loadError: "Failed to load performance data",
      totalSignals: "Total Signals",
      analyzedSignals: "Analyzed",
      skippedSignals: "No Data",
      horizonTitle: "Performance by Horizon",
      colHorizon: "Horizon",
      colCount: "Count",
      colWinRate: "Win Rate",
      colAvgDirectional: "Avg Dir. Return",
      colMfe: "Avg MFE",
      colMae: "Avg MAE",
      signalTypeTitle: "By Signal Type",
      colSignalType: "Type",
      colSignalCount: "Signals",
      colAnalyzedCount: "Analyzed",
      colWinRate5m: "5m Win Rate",
      colAvgDir5m: "5m Dir. Return",
      symbolTitle: "By Symbol",
      colSymbol: "Symbol",
      tradingTitle: "Actual Trading",
      tradeCount: "Orders",
      filledCount: "Filled",
      totalPnl: "Realized PnL",
      winTrades: "Win Trades",
      lossTrades: "Loss Trades",
      noPnlData: "Insufficient PnL data",
      noSignalData: "No analyzed signals yet.",
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
    aiAnalysis: {
      sectionTitle: "AI Analysis",
      safetyNote: "AI analysis is for research and review only.",
      safetyNote2: "It does not place trades or modify strategies automatically.",
      providerTitle: "AI Provider Status",
      statusAvailable: "Available",
      statusMissingConfig: "API key not set",
      statusNotImplemented: "Not implemented",
      runFormTitle: "Run Analysis",
      labelPromptType: "Analysis Type",
      labelMode: "Mode",
      labelProvider: "Primary Provider",
      labelSecondaryProvider: "Secondary Provider",
      labelEnableCritique: "Mutual Critique",
      labelEnableSynthesis: "Synthesis",
      btnRun: "Run Analysis",
      btnRunning: "Running...",
      btnRefresh: "Refresh",
      btnShowRuns: "Analysis History",
      btnHideRuns: "Close",
      warningMissingConfig: "Selected provider API key is not configured. Check your .env file.",
      runListTitle: "Analysis History",
      runListEmpty: "No analysis runs yet.",
      runListLoading: "Loading...",
      colRunId: "ID",
      colMode: "Mode",
      colStatus: "Status",
      colProvider: "Provider",
      colPromptType: "Type",
      colCreatedAt: "Created",
      colActions: "Detail",
      btnDetail: "View",
      btnHideDetail: "Close",
      detailTitle: "Analysis Result",
      detailStatus: "Status",
      detailError: "Error",
      detailInputHash: "Input Hash",
      detailResponses: "Responses",
      roleLabel: "Role",
      providerLabel: "Provider",
      modelLabel: "Model",
      tokensLabel: "Tokens",
      latencyLabel: "Latency",
      finishLabel: "Finish Reason",
      contentLabel: "Content",
      errorLabel: "Error",
      warnLengthTruncated: "Response was truncated by token limit. Increase max_tokens or reduce prompt length.",
      loadError: "Failed to load analysis runs",
      createError: "Failed to run analysis",
      runningLongNotice: "Analysis may take 1–2 minutes. Please wait.",
      elapsedSeconds: (n: number) => `${n}s elapsed`,
      refreshRuns: "Refresh run list",
      refreshFailed: "Refresh failed",
      requestMayStillBeRunning: "The analysis may still be running on the server. Refresh the run list to check.",
      providerMissingConfig: (provider: string) => `${provider} API key is not configured. Check your .env file.`,
      lengthWarningImpact: (role: string) => `${role} response was cut off by the token limit. This may reduce critique/synthesis quality.`,
    },
    strategyParams: {
      labelStrategyType: "Strategy Type",
      labelSymbolCode: "Symbol Code",
      labelShortWindow: "Short Window",
      labelLongWindow: "Long Window",
      labelQuantity: "Quantity",
      labelQuantityMode: "Sizing mode",
      quantityModeFixed: "Fixed shares",
      quantityModeCashAmount: "Cash per trade",
      quantityModeCashPct: "% of cash",
      labelCashAmount: "Cash per trade (KRW/USD)",
      labelCashPct: "% of available cash",
      labelTimeframe: "Timeframe",
      labelAccountId: "Account ID",
      labelEnabled: "Enabled",
      labelExitOnClose: "Exit on close (closing auction)",
      hintExitOnClose:
        "When on, emits a sell signal to liquidate the day's position at the closing auction (15:20–15:30 KST). Prevents intraday strategies from holding overnight.",
      labelVolumeWindow: "Volume SMA Period",
      labelVolumeMultiplier: "Volume Multiplier",
      strategyTypeMovingAverage: "Moving Average Cross",
      strategyTypeVolumeConfirmed: "Volume Confirmed MA Cross",
      strategyTypeFlowConfirmed: "Flow Confirmed Volume MA Cross",
      errorLongWindowGtShort: "Long window must be greater than short window.",
      errorVolumeWindowGt0: "Volume window must be at least 1.",
      errorVolumeMultiplierGt0: "Volume multiplier must be greater than 0.",
      hintAutoTrade:
        "When auto_trade_enabled is OFF, only signals are generated and recorded; no KIS orders are placed. When ON, orders are sent automatically for signals that pass RiskManager validation.",
      labelFlowLookbackDays: "Flow Lookback Days",
      labelMaxFlowAgeDays: "Max Flow Age Days",
      labelFlowMode: "Flow Filter Mode",
      labelRequireFlowData: "Require Flow Data",
      flowModeForeignOrInstitution: "Foreign or Institution Net Buy",
      flowModeForeignAndInstitution: "Foreign and Institution Net Buy",
      flowModeSmartMoneyVsRetail: "Smart Money vs Retail (Research Heuristic)",
      hintFlowData:
        "Flow data is daily confirmed data, not real-time buying/selling pressure. Only data from the day before the candle date is used to prevent look-ahead bias.",
      errorFlowLookbackDaysGt0: "Flow lookback days must be at least 1.",
      errorMaxFlowAgeDaysGt0: "Max flow age days must be at least 1.",
      strategyTypeRsiReversion: "RSI Reversion",
      strategyTypeMacdTrend: "MACD Trend",
      strategyTypeBreakoutHigh: "Breakout High",
      strategyTypePullbackTrend: "Pullback Trend",
      labelUniverse: "Universe (auto symbol selection)",
      labelUniverseMarket: "Universe market filter",
      universeMarketAll: "All (KR+US)",
      universeNone: "None (single symbol)",
      universeScannerCandidates: "Scanner Candidates",
      universeWatchlist: "Watchlist",
      hintUniverse:
        "Selecting a universe runs the strategy across all scanner candidates / watchlist symbols and records signals, without specifying symbols one by one (signal-only; auto-trade not allowed).",
      labelRsiPeriod: "RSI Period",
      labelOversold: "Oversold",
      labelOverbought: "Overbought",
      labelExitMode: "Exit Mode",
      exitModeOverbought: "On Overbought",
      exitModeMidline: "Midline Reversion (50)",
      labelFastPeriod: "Fast EMA Period",
      labelSlowPeriod: "Slow EMA Period",
      labelSignalPeriod: "Signal Period",
      labelRequireAboveZero: "Buy only above zero line",
      labelBreakoutLookback: "Breakout Lookback (bars)",
      labelExitLookback: "Exit Lookback (bars)",
      labelSurgeLookback: "Momentum Lookback (bars)",
      labelSurgeThresholdPct: "Surge Entry Threshold (%)",
      labelExitDropPct: "Momentum Fade Exit (%)",
      labelVolumeConfirm: "Use Volume Confirmation",
      labelMarket: "Market",
      marketKr: "Korea (KR)",
      marketUs: "US",
      labelExchange: "Exchange (US)",
    },
  },
};
