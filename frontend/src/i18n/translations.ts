export type Language = "ko" | "en";

export interface Translations {
  nav: {
    dashboard: string;
    strategies: string;
    watchlists: string;
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
    colNote: string;
    colActions: string;
    addSymbolTitle: string;
    symbolCode: string;
    symbolCodePlaceholder: string;
    symbolName: string;
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
      watchlists: "관심종목",
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
        strategy_runner: "전략 실행 작업",
        order_sync: "주문 체결 동기화 작업",
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
      colNote: "메모",
      colActions: "작업",
      addSymbolTitle: "종목 추가",
      symbolCode: "종목코드",
      symbolCodePlaceholder: "예: 005930",
      symbolName: "종목명",
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
      watchlists: "Watchlists",
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
        order_sync: "Order Sync",
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
      colNote: "Note",
      colActions: "Actions",
      addSymbolTitle: "Add Symbol",
      symbolCode: "Symbol Code",
      symbolCodePlaceholder: "e.g. 005930",
      symbolName: "Symbol Name",
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
