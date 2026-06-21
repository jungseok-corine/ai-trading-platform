# C-4 설계 — 전략 엔진 확장 (실전 전략 타입)

> 상태: **구현 완료** (전략 4종 + 유니버스 신호 스캔) · 작성 2026-06-21 · 페이즈 C-4
> 남은 것: 토이 전략 아카이브 + 로그 리셋(§5) — 실행 전 테이블 목록 확인 후 진행.
> 목적: 엔진이 **이동평균 교차밖에 못 도는** 현 상태를 깨고, 서로 다른 매매 원리의
> 실전 전략 타입을 추가해 **로그가 차별화되도록** 만든다. 그래야 AI 제안·회고 루프가
> "단기 5 vs 7" 미세 파라미터 싸움을 벗어난다.

## 1. 왜 (문제)

엔진에 등록된 `strategy_type`은 3개인데 **전부 골든크로스 변형**이다.

| 등록 타입 | 진입 원리 |
|-----------|-----------|
| `moving_average_cross` | 단기MA가 장기MA 상향 돌파 |
| `volume_confirmed_ma_cross` | 위 + 거래량 spike 확인 |
| `flow_confirmed_volume_ma_cross` | 위 + 수급(외국인/기관) 확인 |

→ 모든 전략의 진입 신호가 본질적으로 하나라, 쌓이는 `signal_logs`가 동질적이다.
비교·제안·회고의 입력이 빈약해진다. **"실전 전략을 제대로 짠다"의 진짜 병목은 엔진이다.**

좋은 소식: 지표는 이미 다 구현돼 있다 (`app/trading/strategy/indicators.py`):
`calculate_sma`, `calculate_ema`, `calculate_rsi`, `calculate_macd`, `calculate_volume_sma`,
`calculate_volume_ratio`. 돌파는 캔들 고저 min/max로 계산 가능. **새 지표 수학은 거의 불필요.**

## 2. 아키텍처 제약 (설계의 전제)

전략은 **상태 없는 신호 생성기**다.

```
SignalService.generate_and_log_signal()
  → strategy.generate_signal(symbol_code, candles, version_id, context) → Signal | None
  → signal_logs 저장
  → (이후) signal_outcome_service 가 호라이즌별 선행수익률로 품질 평가
```

`generate_signal`에는 **"내 진입가" 같은 포지션 상태가 주입되지 않는다.** 러너가 진입가를
들고 있지 않으므로, 전략 내부에서 "진입가 대비 -3% 손절" 같은 stop/target 상태머신은
표현할 수 없다.

→ **결론: 청산은 stop/target 상태가 아니라 "SELL 신호 조건"으로 표현한다.**
(예: RSI 과매도 진입 → RSI 과열 시 SELL.) 진짜 포지션 기반 손절/목표가는 포지션 상태
추적이 필요한 *별도의 더 큰 작업*이며, **C-4 범위 밖**으로 분리한다 (§6 참조).

이 제약 덕분에 러너/`SignalService`/`signal_outcome`은 **수정이 필요 없다**. 새 전략은
`registry._REGISTRY`에만 등록하면 기존 실행 경로를 그대로 탄다.

## 3. 추가할 전략 타입 4종

전부 **서로 다른 매매 원리** → 차별화된 로그. 전부 기존 지표로 구현 가능.
모두 권장 timeframe은 **일봉**(`timeframe="1d"`)이나 파라미터로 조정 가능.

### 3.1 `rsi_reversion` — RSI 평균회귀 (역추세 / 과매도 반등)
- **BUY**: 직전 RSI ≤ `oversold` 이고 현재 RSI > `oversold` (과매도 구간을 아래→위로 탈출)
- **SELL**: 현재 RSI ≥ `overbought`  *또는*  `exit_mode="midline"`이면 RSI가 50을 상향 회귀
- **params**: `rsi_period=14`, `oversold=30`, `overbought=70`, `exit_mode="overbought"|"midline"`, `quantity=1`
- **지표**: `calculate_rsi`

### 3.2 `macd_trend` — MACD 추세추종 (모멘텀)
- **BUY**: MACD선이 시그널선을 **상향 교차** (옵션 `require_above_zero=True`면 MACD>0일 때만)
- **SELL**: MACD선이 시그널선을 **하향 교차**
- **params**: `fast_period=12`, `slow_period=26`, `signal_period=9`, `require_above_zero=False`, `quantity=1`
- **지표**: `calculate_macd`

### 3.3 `breakout_high` — 전고점 돌파 (추세 추종, Donchian)
- **BUY**: 현재 종가 > 직전 `breakout_lookback`봉의 최고가 (신고가 돌파)
- **SELL**: 현재 종가 < 직전 `exit_lookback`봉의 최저가 (하단 이탈)
- **params**: `breakout_lookback=20`, `exit_lookback=10`, `volume_confirm=False`, `volume_window=20`, `volume_multiplier=1.5`, `quantity=1`
- **지표**: 캔들 high/low min·max (+ 옵션 `calculate_volume_sma`)

### 3.4 `pullback_trend` — 눌림목 매수 (추세 내 되돌림)
- **BUY**: 상승추세(종가 > 장기MA) 中 직전 종가 < 단기MA, 현재 종가 > 단기MA (눌림 후 단기선 재탈환)
- **SELL**: 현재 종가 < 장기MA (추세 이탈)
- **params**: `short_window=10`, `long_window=50`, `quantity=1`
- **지표**: `calculate_sma`

## 4. 구현 작업 목록 (체크리스트)

각 전략 = 한 단위. 모두 동일 패턴:

1. `app/trading/strategy/<name>.py` — `Strategy` 서브클래스, `name`, `from_params`, `generate_signal`
2. `registry.py` `_REGISTRY`에 등록 (러너 수정 없음)
3. `schemas.py` `STRATEGY_TYPES_METADATA`에 `StrategyTypeMeta` 추가 (프론트 전략 생성 폼에 노출)
4. `schemas.py` `StrategyVersionParameters`에 전략별 전용 파라미터 optional-with-default 추가 + 검증
5. 단위 테스트 `backend/tests/.../test_<name>.py` — BUY/SELL/None 경계, 데이터 부족, 파라미터
6. 프론트 빌드 확인 (메타 기반 동적 폼이면 코드 변경 불필요, 빌드만)

검증: 백엔드 전체 테스트 + `ruff check app/` + 프론트 `npm run build` 통과 후 커밋.

## 5. 아카이브 + 로그 리셋 (정리 작업)

새 전략으로 **의미 있는 측정 기준선**을 시작하기 위해:

1. **아카이브**: 기존 5/20 토이 전략의 모든 버전을 `status=ARCHIVED` +
   `auto_trade_enabled=false` 로 전환 (연구 루프가 무시). **이력/FK는 보존** —
   hard delete 금지(참조 무결성 + "덮어쓰기 금지" 철학).
2. **로그 리셋**: 깨끗한 기준선을 위해 비울 후보 테이블 —
   `signal_logs`, signal outcome 집계, 페이퍼 trades, 관련 `experiment` 기록.
   → **실행 직전 정확한 테이블 목록을 사람에게 다시 확인받고** 비운다 (파괴적 작업).

> 안전: 이 정리는 read-only 루프와 무관한 1회성 데이터 운영이며, 실거래/주문과 무관하다.
> `KIS_REAL_TRADING_ENABLED=false` 등 🔒 안전 불변식은 건드리지 않는다.

## 6. 범위 밖 (다음 단계 후보)

- **포지션 기반 청산(stop/target)**: 전략에 진입가/보유 상태를 주입하려면 러너·시그널
  서비스에 포지션 추적을 추가해야 함 → 별도 페이즈.
- **AI가 실전 매매법을 외부(커뮤니티/유명 트레이더)에서 소싱해 전략을 *제안***:
  엔진에 다양한 타입이 생긴 *다음*에 의미가 있다 (AI가 실행 가능한 타입으로만 제안 가능).
  순서: **(C-4) 엔진 타입 확장 → AI가 타입·파라미터 제안 → (선택) 웹 리서치 소싱.**

## 7. 안전 불변식 점검

- 새 전략 기본값: `auto_trade_enabled=False`, `enabled=True`(신호 생성만), 실주문 호출 없음.
- 신규 스케줄러 잡 추가 없음 (기존 `strategy_runner` 잡이 레지스트리를 그대로 사용).
- AI 자동 적용 없음 — 새 타입은 사람이 전략 생성 시 선택, 제안은 여전히 pending/DRAFT.
