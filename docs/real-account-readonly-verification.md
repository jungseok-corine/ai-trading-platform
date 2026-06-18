# C-2.13: 실전 계좌 Read-Only 검증 가이드

## 개요

실전 KIS 계좌를 read-only 모드로 연결해 조회 기능만 검증한다.
**어떤 경로로도 주문 API(place_order)를 호출하지 않는다.**

## 필요한 환경변수

```
KIS_REAL_APP_KEY=<실전 앱키>
KIS_REAL_APP_SECRET=<실전 앱시크릿>
KIS_REAL_ACCOUNT_NO=<실전 계좌번호, 형식: 12345678-01>
# 아래는 기본값이 false — 변경하지 말 것
# KIS_REAL_TRADING_ENABLED=false
```

## 허용 API (read-only 모드)

| 기능 | TR_ID | 허용 |
|------|-------|------|
| 실전 잔고조회 | TTTC8434R | ✅ |
| 실전 주문체결조회 | TTTC0081R | ✅ |
| 현재가 조회 | FHKST01010100 | ✅ |
| 분봉 조회 | FHKST03010200 | ✅ |
| 토큰 발급 | oauth2/tokenP | ✅ |

## 금지 API (read-only 모드에서 절대 호출 불가)

| 기능 | TR_ID | 결과 |
|------|-------|------|
| 실전 현금 매수 | TTTC0012U | `RealTradingDisabledError` 즉시 발생 |
| 실전 현금 매도 | TTTC0011U | `RealTradingDisabledError` 즉시 발생 |
| StrategyRunner 자동 주문 | — | `real_trading_disabled` 결과로 차단 |
| TradeService 수동 주문 | — | `real_trading_disabled` 결과로 차단 |
| AI 분석 기반 주문 | — | AI는 resume/주문 불가 (C-2.12) |

## Smoke Test 실행 방법

### 1. 설정 확인만 (실제 KIS API 호출 없음)

```bash
cd backend
python scripts/kis_real_readonly_smoke_test.py
```

출력 예:
```
  provider            : kis-real
  mode                : real-readonly
  app_key             : ABCD***
  account_no          : 5019***-**
  config_ready        : True
  real_trading_enabled: False

  [DRY RUN] --confirm-readonly 플래그 없음.
  실제 KIS API 호출은 하지 않았습니다.

  result              : DRY_RUN_OK
```

### 2. 실제 조회 API 호출 (주문 API 미호출 보장)

```bash
cd backend
python scripts/kis_real_readonly_smoke_test.py --confirm-readonly
```

출력 예:
```
  token               : ok (masked: ABCDEFGH***)
  balance_query       : ok
  daily_executions    : ok
  positions_count     : 3
  executions_count    : 0
  order_api_called    : False  ← 항상 false
  real_trading_enabled: False  ← 항상 false

  result              : SAFE_READONLY_VERIFIED
```

## 방어 레이어 구조

```
실전 주문 시도
     │
     ▼
[레이어 1] TradeService.execute_signal()
           getattr(broker, 'real_trading_enabled', True) == False
           → rule_name='real_trading_disabled' 반환, place_order 미호출
     │
     ▼ (레이어 1 통과 시에만 도달)
[레이어 2] TradingGuardService.is_paused()
           → 'trading_paused' 반환
     │
     ▼ (레이어 2 통과 시에만 도달)
[레이어 3] RiskService (EmergencyStopRule, emergency_stop=True)
           → 거부
     │
     ▼ (레이어 3 통과 시에만 도달)
[레이어 4] KISRealBrokerClient.place_order()
           real_trading_enabled=False → RealTradingDisabledError
```

## C-2.14: 실전 계좌 DB 등록 방법

### 등록 스크립트 실행

```bash
cd backend

# 기본 등록 (DB 등록 + 안전 상태 초기화, KIS API 미호출)
.venv/bin/python scripts/register_live_account_readonly.py --alias "실전계좌"

# 등록 후 read-only KIS 조회 검증
.venv/bin/python scripts/register_live_account_readonly.py --alias "실전계좌" --verify-readonly

# 계좌번호 직접 지정 시
.venv/bin/python scripts/register_live_account_readonly.py --broker-account-no 12345678-01
```

### 등록 후 기본 안전 상태

| 항목 | 값 | 의미 |
|------|-----|------|
| `account_type` | `LIVE` | 실전 계좌로 분류 |
| `TradingGuardState.is_paused` | `True` | 신규 주문 차단 |
| `TradingGuardState.pause_source` | `MANUAL` | 수동 등록 |
| `RiskConfig.emergency_stop` | `True` | EmergencyStopRule 즉시 거부 |
| `KIS_REAL_TRADING_ENABLED` | `false` | broker.place_order 차단 |

### emergency_stop=True 의미

`RiskConfig.emergency_stop=True`이면 `EmergencyStopRule`이 모든 주문을 거부한다.
Trading guard resume 후에도 emergency_stop이 True이면 주문 불가.
해제는 `POST /api/v1/risk-config/{account_id}/emergency-stop {"enabled": false}`.

### trading_guard paused 의미

`TradingGuardState.is_paused=True`이면 `TradeService`와 `StrategyRunner` 모두 주문 차단.
해제는 `POST /api/v1/accounts/{account_id}/trading-guard/resume`.
**AI 분석 결과가 자동으로 resume을 호출해서는 안 된다.**

### 절대 커밋하면 안 되는 파일

- `.env` (KIS_REAL_APP_KEY, KIS_REAL_APP_SECRET, KIS_REAL_ACCOUNT_NO 포함)
- `.cache/kis_real_token.json` (실전 access token)
- `.cache/kis_token.json` (모의 access token)
- 계좌번호/app secret이 포함된 모든 파일

위 파일들은 `.gitignore`로 추적 제외되어 있다.

### 멱등성 보장

같은 계좌번호로 스크립트를 여러 번 실행해도 안전하다:
- Account 중복 생성 없음
- TradingGuardState가 resume 상태였어도 pause로 되돌림
- RiskConfig의 emergency_stop=False였어도 True로 되돌림

## 실전 주문 전환 전 체크리스트

실전 자동매매를 시작하려면 **모든 항목을 검토한 후 사람이 명시적으로** 진행해야 한다.

- [ ] `KIS_REAL_TRADING_ENABLED=false` 상태에서 smoke test 통과 확인
- [ ] 실전 잔고조회(TTTC8434R) 정상 응답 확인
- [ ] 실전 체결조회(TTTC0081R) 정상 응답 확인
- [ ] TradingGuardState가 pause 상태인지 확인
- [ ] RiskConfig.emergency_stop=True인지 확인 (기본 안전 상태)
- [ ] RiskConfig 파라미터 검토 (max_position_size, daily_loss_limit 등)
- [ ] 소액 수동 주문 1건으로 order-cash API 직접 테스트
- [ ] TradeService 경로를 통한 수동 주문 1건 검증
- [ ] 전체 테스트 suite 통과 확인
- [ ] TradingGuard 수동 resume (사람이 직접 API 호출)
- [ ] KIS_REAL_TRADING_ENABLED=true 설정 (사람이 명시적으로)

## 안전 원칙 (불변)

- AI 분석 결과가 자동으로 주문/전략 변경/거래 재개에 영향을 줘서는 안 된다.
- resume은 사람이 `POST /api/v1/accounts/{account_id}/trading-guard/resume`으로만 가능하다.
- 실전 자동매매 활성화(`KIS_REAL_TRADING_ENABLED=true`) 이후에도 trading guard pause 체계는 계속 동작한다.
- paper mode는 이 모든 실전 guard와 무관하게 기존 흐름을 유지한다.
