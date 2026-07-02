# STRATEGY-ARCHIVE-PLAN-1: Safe Archive Application Design

> **작성일**: 2026-07-02  
> **최종 보정**: 2026-07-02 (PLAN-1B — open position 있는 버전 분리)  
> **작업 유형**: read-only 조사 + 문서 작성 (DB write 없음, 코드 변경 없음, commit 없음)  
> **선행 문서**: `docs/strategy/strategy-disposition-plan.md`

---

## Archive Safety Rule

> **A strategy version must not be archived while it has an open position,**  
> **unless a separate position disposition plan explicitly accepts that state.**

**이유**:
- archive는 삭제가 아니라 운영 제외(soft exclude)다.
- 열린 포지션이 있는 버전을 archived로 보내면 runner가 해당 버전을 더 이상 처리하지 않는다.
- 그 결과 열린 포지션은 영구적으로 잔존하며, 청산/정합성/손익 해석이 어려워진다.
- open position/PnL/reconciliation/AI 분석에 노이즈가 남는다.
- 따라서 **1차 archive 적용에서는 open position = 0인 버전만 archived 처리한다.**

---

## Part 1. 현재 상태 재확인

### Git

```
HEAD:         bc62ad5  (docs: propose strategy disposition plan)
working tree: clean
branch:       main == origin/main
```

### DB — strategy_versions 분포

| 항목 | 값 |
|------|-----|
| total | 25 |
| status=testing | 20 |
| status=draft | 5 |
| status=active | 0 |
| status=archived | 0 |
| auto_trade_enabled=true | 0 |
| universe_auto_trade=true | 0 |
| enabled=true (parameters JSONB) | 23 |
| enabled=false/null | 2 |
| live trading (`KIS_REAL_TRADING_ENABLED`) | off |
| 전체 open positions (exit_time IS NULL) | 29 |

### ARCHIVE_CANDIDATE 15개 현재 상태

> 모두 `status=testing, enabled=true, auto_trade_enabled=false`

| id | strategy_id | strategy_name | strategy_type | status | enabled | auto_trade | univ_auto | signal_7d | signal_all | trades | open_trades | open_category |
|----|-------------|---------------|---------------|--------|---------|------------|-----------|-----------|------------|--------|-------------|---------------|
| 297 | 275 | [유니버스] RSI 평균회귀 | rsi_reversion | testing | true | false | false | 8,622 | 21,833 | 5 | **5** | DEFER_OPEN_POSITION |
| 298 | 276 | [유니버스] MACD 추세추종 | macd_trend | testing | true | false | false | 0 | 0 | 0 | 0 | ARCHIVE_NOW |
| 299 | 277 | [유니버스] 전고점 돌파 | breakout_high | testing | true | false | null | 8,507 | 11,724 | 0 | 0 | ARCHIVE_NOW |
| 302 | 280 | [유니버스] MACD 추세추종 | macd_trend | testing | true | false | false | 0 | 0 | 0 | 0 | ARCHIVE_NOW |
| 303 | 281 | [유니버스] 전고점 돌파 | breakout_high | testing | true | false | false | 800 | 2,448 | 0 | 0 | ARCHIVE_NOW |
| 306 | 275 | [유니버스] RSI 평균회귀 | rsi_reversion | testing | true | false | false | 8,626 | 10,233 | 4 | **4** | DEFER_OPEN_POSITION |
| 308 | 284 | [US] 전고점 돌파 | breakout_high | testing | true | false | null | 3,019 | 4,558 | 0 | 0 | ARCHIVE_NOW |
| 309 | 285 | [US] RSI 평균회귀 | rsi_reversion | testing | true | false | null | 4,505 | 5,991 | 0 | 0 | ARCHIVE_NOW |
| 310 | 277 | [유니버스] 전고점 돌파 | breakout_high | testing | true | false | false | 9,840 | 12,912 | 0 | 0 | ARCHIVE_NOW |
| 312 | 275 | [유니버스] RSI 평균회귀 | rsi_reversion | testing | true | false | false | 11,534 | 15,191 | 4 | **4** | DEFER_OPEN_POSITION |
| 313 | 285 | [US] RSI 평균회귀 | rsi_reversion | testing | true | false | false | 2,654 | 3,347 | 0 | 0 | ARCHIVE_NOW |
| 314 | 281 | [유니버스] 전고점 돌파 | breakout_high | testing | true | false | false | 1,423 | 3,973 | 1 | 0 | ARCHIVE_NOW |
| 315 | 279 | [유니버스] RSI 평균회귀 | rsi_reversion | testing | true | false | false | 1,756 | 4,766 | 2 | 0 | ARCHIVE_NOW |
| 316 | 275 | [유니버스] RSI 평균회귀 | rsi_reversion | testing | true | false | false | 9,019 | 11,807 | 2 | **1** | DEFER_OPEN_POSITION |
| 318 | 281 | [유니버스] 전고점 돌파 | breakout_high | testing | true | false | false | 1,428 | 3,877 | 0 | 0 | ARCHIVE_NOW |

**signal_7d 합계 (ARCHIVE_CANDIDATE 전체)**: ~70,733 신호/주  
**ARCHIVE_NOW (11개)**: open_trades=0 → 1차 적용 대상  
**DEFER_OPEN_POSITION (4개)**: v297, v306, v312, v316 → 1차 적용 제외, 별도 처리 필요

### DEFER_OPEN_POSITION — open position 상세

> 모두 `market=KR, auto_trade_enabled=false`  
> paper 포지션 (모의투자). 실거래 없음.

| version_id | symbol_code | side | qty | entry_price | entry_time (UTC) | order_status | 비고 |
|------------|-------------|------|-----|-------------|------------------|--------------|------|
| 297 | 015760 | buy | 1 | 37,250 | 2026-06-23 02:37 | **filled** | 한국전력 |
| 297 | 373220 | buy | 1 | 374,500 | 2026-06-23 02:37 | **filled** | LG에너지솔루션 |
| 297 | 005380 | buy | 1 | 531,000 | 2026-06-23 02:38 | **filled** | 현대차 |
| 297 | 066570 | buy | 1 | 210,000 | 2026-06-23 02:38 | **filled** | LG전자 |
| 297 | 145020 | buy | 1 | 251,500 | 2026-06-23 02:39 | **filled** | 휴젤 |
| 306 | 015760 | buy | 1 | 37,250 | 2026-06-23 02:37 | **filled** | 한국전력 |
| 306 | 373220 | buy | 1 | 374,000 | 2026-06-23 02:37 | **filled** | LG에너지솔루션 |
| 306 | 066570 | buy | 1 | 210,000 | 2026-06-23 02:39 | **filled** | LG전자 |
| 306 | 145020 | buy | 1 | 251,500 | 2026-06-23 02:39 | **filled** | 휴젤 |
| 312 | 051900 | buy | 1 | 222,000 | 2026-06-24 02:48 | **filled** | LG H&H |
| 312 | 086790 | buy | 1 | 114,100 | 2026-06-24 02:48 | **filled** | 하나금융지주 |
| 312 | 010950 | buy | 1 | 102,000 | 2026-06-24 03:09 | **filled** | S-Oil |
| 312 | 011070 | buy | 1 | 943,000 | 2026-06-24 03:09 | **filled** | 엘앤에프 |
| 316 | 017670 | **sell** | 1 | 92,700 | 2026-06-24 23:30 | **cancelled** | SKT — 취소 주문 잔존 |

**v297/v306/v312**: `order_status=filled` → 실제 paper BUY 포지션이 잔존.  
**v316**: `order_status=cancelled` → 취소된 SELL 주문이 exit_time=NULL로 잔존. 실제 보유 포지션이 아닌 취소 주문 아티팩트.

> open position 원인 추정: auto_trade가 일시 활성화됐을 당시 paper 주문이 체결됐고, 이후 auto_trade=false로 전환됐으나 해당 포지션은 청산되지 않은 채 잔존.

### KEEP_SIGNAL_ONLY 3개

| id | strategy_id | strategy_type | status | enabled | auto_trade | signal_7d |
|----|-------------|---------------|--------|---------|------------|-----------|
| 300 | 278 | pullback_trend | testing | true | false | 0 |
| 304 | 282 | pullback_trend | testing | true | false | 0 |
| 317 | 277 | breakout_high | testing | true | false | 9,855 |

> v300·v304: 7일간 신호 0 (pullback 조건이 현재 시장에서 미발생).  
> v317: 신호 활발 — breakout_high 연구용 유지.

### DEFER_REVIEW 1개

| id | strategy_type | status | enabled | signal_7d |
|----|---------------|--------|---------|-----------|
| 307 | momentum_surge | testing | true | 113 |

### SMOKE_TEST 1개

| id | strategy_name | strategy_type | status | enabled | auto_trade | signal_7d | open |
|----|---------------|---------------|--------|---------|------------|-----------|------|
| 329 | limited-paper-005930-moving-average-cross | moving_average_cross | testing | true | false | 27 | 2 |

---

## Part 2. 코드 read-only 조사 결과

### 2-1. `StrategyVersionStatus` enum

**Python** (`app/domain/models/enums.py`):
```python
class StrategyVersionStatus(str, enum.Enum):
    DRAFT    = "draft"
    TESTING  = "testing"
    ACTIVE   = "active"
    RETIRED  = "retired"
    ARCHIVED = "archived"
```

**PostgreSQL** (`strategy_version_status` enum):
```
draft | testing | active | retired | archived
```

**`archived`는 Python과 PostgreSQL 양쪽에 완전히 정의되어 있다.**  
현재 DB에 archived 행은 0개이지만, 타입 자체는 완전 지원 상태.

---

### 2-2. `list_active()` — runner가 보는 버전 범위

```python
# app/domain/repositories/strategy.py
async def list_active(self) -> list[StrategyVersion]:
    """status가 active 또는 testing인 전략 버전을 조회한다."""
    result = await self.session.execute(
        select(StrategyVersion).where(
            StrategyVersion.status.in_(
                [StrategyVersionStatus.ACTIVE, StrategyVersionStatus.TESTING]
            )
        )
    )
    return list(result.scalars().all())
```

**`archived` 버전은 `list_active()`에서 반환되지 않는다.**  
이 메서드를 사용하는 서비스:

| 서비스 | 사용 위치 |
|--------|-----------|
| `StrategyRunnerService.run_once()` | runner tick 실행 대상 |
| `StrategyReviewService.review()` | 전략 점검 잡 대상 |
| `DailyAnalysisService.run()` | 일일 AI 분석 대상 |

→ **`archived` 상태이면 이 세 서비스 모두에서 자동 제외된다.**

---

### 2-3. `enabled` 파라미터 처리

`enabled`는 `strategy_versions.parameters` JSONB 필드 안에 있다 (별도 컬럼 아님).

```python
# app/services/strategy_runner_service.py, line 115
async def _run_version(self, version, ...):
    params = version.parameters or {}
    if not params.get("enabled", True):
        return []  # skip — signal/trade 모두 없음
```

`enabled=false`이면 runner는 신호를 생성하지 않는다. 그러나:
- **`enabled=false`는 `list_active()` 필터에 영향을 주지 않는다.**
- `StrategyReviewService`와 `DailyAnalysisService`는 `enabled=false`인 버전도 여전히 대상으로 삼을 수 있다.
- 따라서 Option A(enabled=false)는 완전한 제외 방법이 아니다.

---

### 2-4. `auto_trade_enabled` vs `enabled` 차이

| 플래그 | 저장 위치 | 효과 |
|--------|-----------|------|
| `enabled` | `parameters` JSONB | false → runner `_run_version()`에서 즉시 skip (signal도 없음) |
| `auto_trade_enabled` | `parameters` JSONB | false → signal_log만 생성, trade/order 없음 |
| `universe_auto_trade` | `parameters` JSONB | false → universe 모드 자동매매 없음 |

현재 ARCHIVE_CANDIDATE 15개: 모두 `enabled=true, auto_trade_enabled=false`.  
→ 지금 이 버전들은 신호는 만들고 있으나 주문은 없는 signal-only 상태.  
→ 아카이브 목적은 신호 생성 자체도 중단하는 것.

---

### 2-5. `archive_version()` 서비스

```python
# app/services/strategy_service.py
async def archive_version(self, strategy_id: int, version_id: int) -> StrategyVersion:
    """버전을 ARCHIVED 상태로 전환한다 (soft delete).
    어떤 상태/참조 여부와 무관하게 안전하게 보관 처리할 수 있다.
    """
    version = await self._get_owned_version(strategy_id, version_id)
    await self._version_repo.update(version, status=StrategyVersionStatus.ARCHIVED)
    await self._session.commit()
    return version
```

**API 엔드포인트**: `POST /api/v1/strategies/{strategy_id}/versions/{version_id}/archive`

> 주의: `archive_version()` 코드는 "어떤 상태/참조 여부와 무관하게 안전"이라고 설명하나, 이는 DB 레벨의 참조 무결성을 말하는 것이다. open position 관점의 운영 안전성은 별도 판단이 필요하다 → Archive Safety Rule 참조.

---

### 2-6. archived 버전의 조회 가능 여부

```python
# app/domain/repositories/strategy.py
async def list_by_strategy(
    self, strategy_id: int, include_archived: bool = False
) -> list[StrategyVersion]:
    stmt = select(StrategyVersion).where(StrategyVersion.strategy_id == strategy_id)
    if not include_archived:
        stmt = stmt.where(StrategyVersion.status != StrategyVersionStatus.ARCHIVED)
```

- **기본 목록**: archived 제외 (UI에서 노이즈 없음)
- **`include_archived=true` 파라미터**: archived 포함 (필요 시 조회 가능)
- **히스토리 보존**: signal_logs FK `ON DELETE SET NULL`, trades FK `ON DELETE SET NULL` → archived 후에도 기존 데이터 유지

---

## Part 3. 적용 방식 비교

### Option A. `enabled=false` (parameters JSONB 변경)

**방식**: `parameters.enabled = false`로 설정. `status`는 `testing` 유지.

**효과:**
- Runner `_run_version()`: `enabled=false` 체크 → return [] → 신호 생성 중단 ✓
- `list_active()`: 여전히 반환 (status=testing이므로)
- `StrategyReviewService.review()`: list_active() 사용 → **여전히 대상에 포함** ⚠
- `DailyAnalysisService.run()`: list_active() 사용 → **여전히 대상에 포함** ⚠

**단점**: status=testing이 유지되므로 review/daily_analysis 노이즈 계속 가능. 의미 불명확.

---

### Option B. `status=archived` (단독)

**방식**: `status` 컬럼을 `testing → archived`로 변경.

**효과:**
- `list_active()` 반환 대상 제외 → runner, review, daily_analysis 모두 처리 안 함 ✓
- 기존 signal_logs/trades 데이터 보존 ✓
- 기본 목록 API에서 숨겨짐 (include_archived=false 기본값) ✓
- `archive_version()` 서비스 + API 엔드포인트 이미 완전 구현 ✓

**제약**: open position이 있는 버전에는 Archive Safety Rule에 따라 1차 적용 불가.

---

### Option C. `enabled=false` + `status=archived`

Option B만으로 충분. 1차 적용으로는 과함.

---

### 권장: **Option B — `status=archived` 단독 (open=0 버전에만)**

1. `archived` 값이 PostgreSQL enum과 Python enum 양쪽에 완전 정의되어 있다.
2. `list_active()`가 archived를 제외 → runner/review/daily_analysis 모두 자동 제외.
3. `archive_version()` 서비스와 API 엔드포인트 이미 구현·테스트됨.
4. `enabled=false` (Option A)는 runner만 막고 review/daily_analysis는 막지 못함.
5. **단, open position이 있는 버전 (v297, v306, v312, v316)은 Archive Safety Rule에 따라 1차 적용에서 제외.**

---

## Part 4. 아카이브 적용 대상 재분류

### 4-1. ARCHIVE_NOW (11개) — 1차 적용 대상

> 조건: ARCHIVE_CANDIDATE + open_position = 0  
> 방법: `POST /api/v1/strategies/{strategy_id}/versions/{version_id}/archive`

| id | strategy_id | strategy_type | current_status | open | proposed_action | reason |
|----|-------------|---------------|----------------|------|-----------------|--------|
| 298 | 276 | macd_trend | testing | 0 | **archive** | 7일간 신호 0, 실질 비활성 |
| 299 | 277 | breakout_high | testing | 0 | **archive** | v310·v317 더 최신. 주 8.5k 노이즈 |
| 302 | 280 | macd_trend | testing | 0 | **archive** | 7일간 신호 0, macd 군 중 불필요 |
| 303 | 281 | breakout_high | testing | 0 | **archive** | v314·v317·v318 대비 낮은 성과 |
| 308 | 284 | breakout_high | testing | 0 | **archive** | US 전고점. 연구 목적 달성. 주 3k 노이즈 |
| 309 | 285 | rsi_reversion | testing | 0 | **archive** | US RSI v285 v1. v313이 최신 |
| 310 | 277 | breakout_high | testing | 0 | **archive** | v277 v2. v317이 더 최신(v3). 주 9.8k 최다 |
| 313 | 285 | rsi_reversion | testing | 0 | **archive** | US RSI v285 v2. 주 2.6k |
| 314 | 281 | breakout_high | testing | 0 | **archive** | v281 v2. v318이 더 최신 |
| 315 | 279 | rsi_reversion | testing | 0 | **archive** | v279 v4. 886 risk_events/주. 중복 |
| 318 | 281 | breakout_high | testing | 0 | **archive** | v281 v3. 866 risk_events/주. v317이 더 최신 |

**ARCHIVE_NOW API 호출 목록 (strategy_id, version_id)**:
```
(276, 298), (277, 299), (280, 302), (281, 303), (284, 308),
(285, 309), (277, 310), (285, 313), (281, 314), (279, 315), (281, 318)
```
총 **11회** 호출.

---

### 4-2. DEFER_OPEN_POSITION (4개) — 1차 적용 제외

> 조건: ARCHIVE_CANDIDATE이지만 open_position > 0  
> 현재 상태 유지. 별도 POSITION-DISPOSITION-1 작업 후 결정.

| id | strategy_id | strategy_type | open | open_detail | proposed_action | reason |
|----|-------------|---------------|------|-------------|-----------------|--------|
| 297 | 275 | rsi_reversion | 5 | 5× BUY, filled (015760/373220/005380/066570/145020) | **defer** | filled paper 포지션 5개 잔존. 처분 방침 결정 후 archive |
| 306 | 275 | rsi_reversion | 4 | 4× BUY, filled (015760/373220/066570/145020) | **defer** | filled paper 포지션 4개 잔존 |
| 312 | 275 | rsi_reversion | 4 | 4× BUY, filled (051900/086790/010950/011070) | **defer** | filled paper 포지션 4개 잔존 |
| 316 | 275 | rsi_reversion | 1 | 1× SELL, cancelled (017670) | **defer** | cancelled SELL 잔존. DB 정합성 정리 후 archive |

> **v316 특이사항**: open position이 `order_status=cancelled`인 SELL 주문이다. 실제 보유 포지션이 아닌 취소된 주문 아티팩트. DB 정합성 관점에서 별도 검토 필요.

---

### 4-3. KEEP_SIGNAL_ONLY (3개)

| id | strategy_type | proposed_action | reason |
|----|---------------|-----------------|--------|
| 300 | pullback_trend | **keep** (변경 없음) | pullback 연구 유지. 신호 0 = 조건 미충족으로 정상 |
| 304 | pullback_trend | **keep** (변경 없음) | 상동. 다른 파라미터 버전으로 비교 포인트 |
| 317 | breakout_high | **keep** (변경 없음) | 주 9.8k 신호 활발. breakout_high v277 v3. 연구 지속 |

---

### 4-4. DEFER_REVIEW (1개)

| id | strategy_type | proposed_action | reason |
|----|---------------|-----------------|--------|
| 307 | momentum_surge | **defer** (변경 없음) | US 급등 모멘텀. US 데이터 충분 후 별도 결정 |

---

### 4-5. SMOKE_TEST (1개)

| id | strategy_type | proposed_action | reason |
|----|---------------|-----------------|--------|
| 329 | moving_average_cross | **keep** + monitor | engine 검증용. auto_trade=false 유지. open position 2개는 POSITION-DISPOSITION-1 범위 밖 |

---

## Part 5. 적용 후 기대 효과

### 신호 노이즈 감소 (ARCHIVE_NOW 11개 기준)

| 항목 | 현재 (주간) | ARCHIVE_NOW 후 |
|------|------------|----------------|
| ARCHIVE_NOW 11개 signal_7d 합계 | ~33,691 | 0 |
| DEFER_OPEN_POSITION 4개 signal_7d | ~37,042 (v297 8622 + v306 8626 + v312 11534 + v316 9019 → 일부 겹침) | 유지 (처분 전까지) |
| KEEP + DEFER_REVIEW + SMOKE | ~10,095 | 유지 |
| 전체 testing 버전 수 | 20 | 9 (4 DEFER_OPEN + 3 KEEP + 1 DEFER_REVIEW + 1 SMOKE) |
| runner 처리 대상 버전 수 | 20 | 9 |

> **ARCHIVE_NOW 단독 효과**: 주간 신호 약 33,691 제거, testing 버전 11개 → archived.  
> DEFER_OPEN_POSITION 4개가 처분되면 추가로 ~37,042 신호/주 제거 가능.

### 불변식 유지

- auto_trade_enabled=true: 여전히 0
- universe_auto_trade=true: 여전히 0
- live trading: 여전히 off
- broker.place_order: 호출 없음

---

## Part 6. 적용 작업 설계 (STRATEGY-ARCHIVE-APPLY-1)

### 6-1. preflight 체크리스트

APPLY-1 시작 전 모두 확인해야 함:

```sql
-- 1. auto_trade_enabled=true = 0
SELECT count(*) FROM strategy_versions WHERE (parameters->>'auto_trade_enabled')::boolean = true;
-- 기대: 0

-- 2. universe_auto_trade=true = 0
SELECT count(*) FROM strategy_versions WHERE (parameters->>'universe_auto_trade')::boolean = true;
-- 기대: 0

-- 3. ARCHIVE_NOW 대상 (11개) open position = 0
SELECT strategy_version_id, count(*) as open_count
FROM trades
WHERE strategy_version_id IN (298,299,302,303,308,309,310,313,314,315,318)
  AND exit_time IS NULL
GROUP BY strategy_version_id;
-- 기대: 0 rows (open position 없음)
-- 만약 1건이라도 있으면 중단

-- 4. ARCHIVE_NOW 대상 현재 상태 확인
SELECT id, status, (parameters->>'enabled') as enabled
FROM strategy_versions
WHERE id IN (298,299,302,303,308,309,310,313,314,315,318);
-- 기대: 모두 status=testing, enabled=true

-- 5. DEFER_OPEN_POSITION 대상이 archive 목록에 포함되지 않았는지 확인
-- (id 297, 306, 312, 316은 이번 적용에서 건드리지 않음)

-- 6. 전체 open position 스냅샷
SELECT strategy_version_id, count(*) FROM trades WHERE exit_time IS NULL
GROUP BY strategy_version_id ORDER BY strategy_version_id;
-- APPLY-1 전 스냅샷 저장 (post-check에서 불변 여부 확인용)
```

**preflight 중단 조건:**
- ARCHIVE_NOW 11개 중 어느 하나에 open position 존재 → **즉시 중단**
- auto_trade_enabled=true 존재 → **즉시 중단**
- reconciliation mismatch 발견 → **즉시 중단**
- 대상 버전이 예상 status가 아닌 경우 → **즉시 중단**

---

### 6-2. DB write 범위 (ARCHIVE_NOW 11개만)

**변경 대상**: `strategy_versions.status` 컬럼, 11개 행만  
**변경 값**: `testing → archived`  
**방법**: 기존 API 엔드포인트 11회 호출

```
API 호출 목록 (strategy_id, version_id):
(276, 298), (277, 299), (280, 302), (281, 303), (284, 308),
(285, 309), (277, 310), (285, 313), (281, 314), (279, 315), (281, 318)
```

**반드시 보존 (건드리지 않음)**:
- `auto_trade_enabled` (이미 false, JSONB 수정 없음)
- `universe_auto_trade` (이미 false/null, JSONB 수정 없음)
- `enabled` (JSONB 수정 없음 — status만 변경)
- `signal_logs`, `trades`, `risk_events` 히스토리 데이터
- DEFER_OPEN_POSITION 버전 (297, 306, 312, 316) — **절대 건드리지 않음**
- KEEP_SIGNAL_ONLY 버전 (300, 304, 317) — 건드리지 않음
- DEFER_REVIEW 버전 (307) — 건드리지 않음
- SMOKE_TEST 버전 (329) — 건드리지 않음

---

### 6-3. post-check

APPLY-1 완료 후 확인:

```sql
-- 1. archived 수 = 11
SELECT status, count(*) FROM strategy_versions GROUP BY status ORDER BY status;
-- 기대: archived=11, testing=9, draft=5

-- 2. testing 버전 = 9 (300, 304, 307, 317, 329 + DEFER_OPEN 297, 306, 312, 316)
SELECT id FROM strategy_versions WHERE status='testing' ORDER BY id;
-- 기대: 297, 300, 304, 306, 307, 312, 316, 317, 329

-- 3. auto_trade_enabled=true = 여전히 0
SELECT count(*) FROM strategy_versions WHERE (parameters->>'auto_trade_enabled')::boolean=true;

-- 4. ARCHIVE_NOW 대상 open position = 0 (변화 없어야 함)
SELECT count(*) FROM trades
WHERE strategy_version_id IN (298,299,302,303,308,309,310,313,314,315,318)
  AND exit_time IS NULL;
-- 기대: 0

-- 5. DEFER_OPEN_POSITION open position 불변 확인
SELECT strategy_version_id, count(*) FROM trades
WHERE strategy_version_id IN (297,306,312,316) AND exit_time IS NULL
GROUP BY strategy_version_id;
-- 기대: preflight 스냅샷과 동일 (297→5, 306→4, 312→4, 316→1)

-- 6. 전체 open position 불변 확인
SELECT count(*) FROM trades WHERE exit_time IS NULL;
-- 기대: preflight 스냅샷 값 (APPLY 전후 동일)

-- 7. runner 처리 대상 (list_active 시뮬레이션) = 9개
SELECT id, parameters->>'strategy_type' as st, status FROM strategy_versions
WHERE status IN ('active','testing') ORDER BY id;
-- 기대: 297, 300, 304, 306, 307, 312, 316, 317, 329

-- 8. archived 대상이 list_active에 없는지 확인
SELECT id FROM strategy_versions
WHERE id IN (298,299,302,303,308,309,310,313,314,315,318)
  AND status IN ('active','testing');
-- 기대: 0 rows

-- 9. 히스토리 보존 확인
SELECT count(*) FROM signal_logs WHERE strategy_version_id IN (298,299,302,303,308,309,310,313,314,315,318);
-- 기대: APPLY 전 값과 동일 (삭제 없음)
```

---

### 6-4. rollback 계획

아카이브 후 문제 발견 시:

```
방법: DB 직접 UPDATE (사람이 직접) — 별도 사용자 승인
  UPDATE strategy_versions SET status='testing' WHERE id IN (...);

Archive Safety Rule 준수:
  rollback 가능성이 낮은 이유 — archive는 soft exclude, 데이터 보존, list_active 제외만.
  실수 발견 시 즉시 복원 가능.
```

---

## Part 7. 후속 작업: POSITION-DISPOSITION-1

**목표**: DEFER_OPEN_POSITION 4개(v297, v306, v312, v316)의 open position을 처리한다.

**범위**:
1. 각 open position의 현재 paper 보유 상황 파악
2. 실제 broker(모의투자 계좌) holdings와 DB open positions 정합성 확인
3. 처리 방침 결정: 수동 청산 / DB reconcile / 그냥 보존 중 선택
4. v316의 `order_status=cancelled` SELL 아티팩트 처리 방침 별도 검토

**처리 방침 옵션**:
- **Option A (수동 청산)**: 모의투자 계좌에서 수동으로 매도 → exit_time 기록 → open=0 → archive 가능
- **Option B (DB reconcile)**: exit_time 직접 기록하고 미청산 처리 → DB write 필요 → 별도 승인
- **Option C (보존 후 archive)**: open 상태 인정하고 archive — 단, reconciliation 리포트/AI 분석 노이즈 수용

**주의**:
- DB write/order 호출은 별도 사용자 승인 전 금지
- POSITION-DISPOSITION-1에서 방침 결정 후에만 v297/v306/v312/v316 archive 진행

---

## Part 8. 최종 보고

### Files Changed

- `docs/strategy/strategy-archive-application-plan.md` (PLAN-1B 보정)

### Summary

PLAN-1B에서 ARCHIVE_CANDIDATE 15개를 open position 유무 기준으로 재분류했다.

- **ARCHIVE_NOW** (11개): open=0 → 1차 적용 대상
- **DEFER_OPEN_POSITION** (4개): v297/v306/v312/v316 → open position 처분 방침 결정 후 archive

핵심 발견:
- v297/v306/v312: `order_status=filled` BUY 포지션 잔존 (paper 모의투자)
- v316: `order_status=cancelled` SELL 아티팩트 잔존 (실제 보유 포지션 아님)
- Archive Safety Rule 추가: open position 있는 버전은 1차 archive 적용에서 제외

### Current State (재확인)

```
strategy_versions: 25
testing:           20
draft:             5
active:            0
archived:          0
auto_trade_enabled=true: 0
universe_auto_trade=true: 0
total open positions: 29
  - DEFER_OPEN_POSITION: 297×5 + 306×4 + 312×4 + 316×1 = 14
  - KEEP/SMOKE/DRAFT: 나머지 15
live trading: off
```

### Open Position Findings

| 항목 | 내용 |
|------|------|
| open position이 있는 archive candidate | v297(5), v306(4), v312(4), v316(1) — 합계 14개 |
| v297/v306/v312 order_status | **filled** — 실제 paper BUY 포지션 |
| v316 order_status | **cancelled** — SELL 취소 주문 아티팩트 |
| broker/DB 관계 | paper(모의) 계좌. 실거래 없음. broker holding과 DB 정합성은 POSITION-DISPOSITION-1에서 확인 |
| archive 즉시 영향 | runner가 해당 버전을 처리하지 않아 포지션 청산 불가 → 영구 잔존 |
| 1차 archive 제외 이유 | Archive Safety Rule: open position 있는 버전은 처분 방침 없이 archive 금지 |

### Updated Archive Policy

| 분류 | 적용 | 대상 |
|------|------|------|
| **ARCHIVE_NOW** | status=archived (1차 적용) | 298, 299, 302, 303, 308, 309, 310, 313, 314, 315, 318 |
| **DEFER_OPEN_POSITION** | 변경 없음 (POSITION-DISPOSITION-1 후 결정) | 297, 306, 312, 316 |
| **KEEP_SIGNAL_ONLY** | 변경 없음 | 300, 304, 317 |
| **DEFER_REVIEW** | 변경 없음 | 307 |
| **SMOKE_TEST** | 변경 없음 | 329 |

### Apply Plan Changes (STRATEGY-ARCHIVE-APPLY-1 수정)

**archive 적용 대상**: 15개 → **11개** (ARCHIVE_NOW만)  
**제외 대상**: v297, v306, v312, v316 (DEFER_OPEN_POSITION)

**추가된 preflight 체크**:
- ARCHIVE_NOW 11개 중 open position = 0 확인 → 1개라도 있으면 중단
- DEFER_OPEN_POSITION 4개가 archive 목록에 포함되지 않았는지 확인
- preflight 전 전체 open position 스냅샷 저장

**추가된 post-check**:
- DEFER_OPEN_POSITION open position = APPLY 전 스냅샷과 동일
- 전체 open position 수 = APPLY 전과 동일
- ARCHIVE_NOW 버전에 open position = 0

### Recommended Next Step

1. **STRATEGY-ARCHIVE-APPLY-1**: preflight 후 ARCHIVE_NOW 11개 archive 적용
2. **POSITION-DISPOSITION-1**: v297/v306/v312/v316 open position 처분 방침 결정 → 이후 archive

### Safety Confirmation

| 항목 | 결과 |
|------|------|
| code changed | ❌ 없음 |
| DB write performed | ❌ 없음 (plan only) |
| migration created | ❌ 없음 |
| StrategyVersion modified | ❌ 없음 |
| RiskConfig modified | ❌ 없음 |
| open positions modified | ❌ 없음 |
| scheduler/job touched | ❌ 없음 |
| broker/KIS touched | ❌ 없음 |
| Trade/Order path touched | ❌ 없음 |
| run-once called | ❌ 없음 |
| commit/push performed | ❌ 없음 |
| secrets printed | ❌ 없음 |

### Final Judgment

**SAFE**

이번 작업은 read-only 조사 + 문서 보정만 수행했다. DB write, 코드 변경, commit 없음.  
open position 있는 4개 버전을 DEFER_OPEN_POSITION으로 분리해 Archive Safety Rule을 준수했다.
