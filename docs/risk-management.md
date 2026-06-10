# Risk Management Layer

자동매매 시스템에서 가장 먼저 신뢰할 수 있어야 하는 부분은 전략이나 AI가 아니라 **모든 주문이 거치는 검증 계층**이다. 이 문서는 RiskManager의 위치, 인터페이스, 규칙, 데이터 모델을 정의한다.

---

## 1. 위치와 흐름

RiskManager는 Strategy와 TradingEngine 사이에 위치하며, **모든 주문 신호는 예외 없이 RiskManager를 통과해야 한다.**

```
Strategy.generate_signal()
        │
        ▼
      Signal  (symbol, side, quantity, price, reason ...)
        │
        ▼
  RiskManager.validate(signal, config, context)
        │
   ┌────┴────┐
   ▼         ▼
approved   rejected ──▶ risk_events 기록 (result='rejected') ──▶ 종료 (주문 미실행)
   │
   ▼
TradingEngine.execute_signal(signal)
   │
   ▼
BrokerClient.place_order()
   │
   ▼
trades 기록 + risk_events 기록 (result='approved')
```

- 거부된 신호는 **TradingEngine에 절대 전달되지 않는다.**
- 승인/거부 여부와 관계없이 모든 검증 결과는 `risk_events`에 기록한다 (감사 목적).
- `emergency_stop`이 활성화되어 있으면 다른 룰 평가 없이 즉시 거부한다.

---

## 2. 인터페이스 설계

```python
# trading/risk/context.py
@dataclass
class RiskContext:
    account_id: int
    account_balance: float
    today_realized_pnl: float          # 당일 실현 손익
    today_trade_count: int             # 당일 체결 거래 수
    open_positions_count: int          # 현재 보유 종목 수
    consecutive_losses: int            # 직전 연속 손실 횟수
    current_position_value: dict[str, float]  # symbol_code -> 평가금액

class RiskContextBuilder:
    async def build(self, account_id: int) -> RiskContext:
        """trades, accounts 테이블을 조회해 컨텍스트 생성"""
        ...


# trading/risk/rules.py
@dataclass
class RiskCheckResult:
    approved: bool
    rule_name: str | None = None
    reason: str | None = None

class RiskRule(ABC):
    name: str

    @abstractmethod
    def check(
        self, signal: Signal, config: RiskConfig, context: RiskContext
    ) -> RiskCheckResult: ...


# trading/risk/manager.py
class RiskManager:
    def __init__(self, rules: list[RiskRule]):
        self._rules = rules

    def validate(
        self, signal: Signal, config: RiskConfig, context: RiskContext
    ) -> RiskCheckResult:
        if config.emergency_stop:
            return RiskCheckResult(False, "emergency_stop", "비상 정지 활성화 상태")

        for rule in self._rules:
            result = rule.check(signal, config, context)
            if not result.approved:
                return result

        return RiskCheckResult(approved=True)
```

`RiskManager`는 순수 함수에 가깝게 설계한다 (DB 접근 없음). DB 조회는 `RiskContextBuilder`와 `TradeService`에서 수행하고, `RiskManager`는 이미 만들어진 `RiskContext` + `RiskConfig`를 받아 판정만 한다 → 단위 테스트가 쉬워진다.

---

## 3. 규칙 (Rules) 상세

| 규칙 | 설정 항목 | 검증 내용 | 거부 조건 |
|---|---|---|---|
| **EmergencyStop** | `emergency_stop: bool` | 모든 주문 차단 | `emergency_stop == True` |
| **MaxDailyLoss** | `max_daily_loss_amount: float` | 당일 누적 손실 한도 | `today_realized_pnl <= -max_daily_loss_amount` |
| **MaxPositionSize** | `max_position_size: float` | 단일 종목 주문 금액 한도 | `signal.price * signal.quantity > max_position_size` |
| **MaxOpenPositions** | `max_open_positions: int` | 동시 보유 종목 수 한도 | 매수 신호이고 신규 종목일 때 `open_positions_count >= max_open_positions` |
| **MaxTradesPerDay** | `max_trades_per_day: int` | 당일 거래 횟수 한도 | `today_trade_count >= max_trades_per_day` |
| **ConsecutiveLossLimit** | `consecutive_loss_limit: int` | 연속 손실 시 매매 일시 중단 | `consecutive_losses >= consecutive_loss_limit` |

각 규칙은 독립된 클래스(`MaxDailyLossRule`, `MaxPositionSizeRule`, ...)로 구현하고 `RiskManager`에 리스트로 주입한다. 새 규칙 추가 시 클래스 추가 + 리스트 등록만 하면 되며 기존 로직 수정은 불필요하다.

```python
# trading/risk/rules.py 예시
class MaxDailyLossRule(RiskRule):
    name = "max_daily_loss"

    def check(self, signal, config, context) -> RiskCheckResult:
        if context.today_realized_pnl <= -config.max_daily_loss_amount:
            return RiskCheckResult(
                False, self.name,
                f"당일 손실 한도 초과: {context.today_realized_pnl}",
            )
        return RiskCheckResult(approved=True)
```

---

## 4. 데이터 모델

```sql
-- 계좌별 리스크 설정 (1:1)
risk_configs (
  id, account_id FK UNIQUE,
  max_daily_loss_amount NUMERIC NOT NULL,
  max_position_size NUMERIC NOT NULL,
  max_open_positions INT NOT NULL,
  max_trades_per_day INT NOT NULL,
  consecutive_loss_limit INT NOT NULL,
  emergency_stop BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at TIMESTAMPTZ
)

-- 모든 검증 결과 기록 (승인/거부)
risk_events (
  id, account_id FK, strategy_version_id FK,
  signal_snapshot JSONB,     -- {symbol, side, quantity, price, reason}
  context_snapshot JSONB,    -- 검증 시점 RiskContext
  result ENUM('approved','rejected'),
  rule_name TEXT NULL,       -- 거부 시 어떤 규칙에서 막혔는지
  reason TEXT NULL,
  created_at TIMESTAMPTZ
)
```

`risk_events`는 단순 로그가 아니라 **AI 분석 단계(2차 목표)에서 "왜 매매가 안 일어났는가"를 설명하는 핵심 데이터**가 된다 (예: "리스크 한도 때문에 놓친 기회" 분석).

---

## 5. Emergency Stop

- `risk_configs.emergency_stop`을 `true`로 설정하면 **해당 계좌의 모든 신규 주문이 즉시 차단**된다.
- API: `POST /api/v1/risk/{account_id}/emergency-stop` (on/off 토글)
- MVP에서는 보유 포지션 강제 청산까지는 하지 않음 — "신규 주문 차단"까지가 범위. 강제 청산 로직은 3차 목표(실거래 준비)에서 별도 설계.
- 토글 동작 자체도 `risk_events` 또는 추후 `decision_logs`에 기록해 "언제, 왜 멈췄는지" 추적 가능해야 한다.

---

## 6. RiskConfig 기본값 (MVP 권장)

모의투자 환경이지만 실거래 전환 시 동일 로직이 쓰이므로, MVP부터 보수적인 기본값을 설정해 습관화한다.

| 항목 | 권장 기본값 (예시) |
|---|---|
| `max_daily_loss_amount` | 계좌 잔고의 2~3% |
| `max_position_size` | 계좌 잔고의 10~20% |
| `max_open_positions` | 3~5 |
| `max_trades_per_day` | 10 |
| `consecutive_loss_limit` | 3 |
| `emergency_stop` | `false` (수동 토글) |

값은 `risk_configs` 테이블에 저장하고 API로 조회/수정 가능하게 한다 (하드코딩 금지).

---

## 7. Live 전환 시 확장 포인트

- 추가 규칙 후보: 장중 변동성 급등 시 포지션 자동 축소, 특정 종목/섹터 노출 한도, 시장 전체 급락 시 자동 일시정지
- `RiskRule` 인터페이스는 변경 없이 새 규칙 클래스만 추가
- Live 계좌는 `risk_configs`에 별도 row(account_id 다름)로 더 보수적인 값 설정 — 코드 변경 없이 설정값만으로 Paper보다 강한 제약 적용 가능
