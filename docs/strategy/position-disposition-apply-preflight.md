# POSITION-DISPOSITION-APPLY-PREFLIGHT-1
# trades.exit_time 백필 — 프리플라이트 체크 + 정합성 맵

작성일: 2026-07-02  
상태: **APPLIED (2026-07-02) — §11 집행 결과 참조**  
목적: 29개 open trade의 exit_time 백필을 위한 사전 검증 및 정밀 매핑

---

## 0. 작업 범위 및 금지 사항

**이 문서는 사전 검증 문서다. 실제 UPDATE는 별도 승인 후 집행한다.**

| 항목 | 이 단계 |
|------|--------|
| DB SELECT (조회) | ✅ 수행 |
| DB UPDATE/INSERT/DELETE | ❌ 금지 |
| 코드 변경 | ❌ 금지 |
| 커밋 / push | ❌ 금지 (이 문서 자체는 별도 커밋) |
| 청산 주문 | ❌ 금지 |
| AI API 호출 | ❌ 금지 |

---

## 1. 프리플라이트 체크 결과

### 1-1. 글로벌 안전 상태

```
account_id=230  emergency_stop=false  (모의계좌, 정상)
account_id=498  emergency_stop=true   (실계좌, 실거래 비활성 ✅)
TradingGuardState = paused (글로벌 매매 일시정지 ✅)
KIS_REAL_TRADING_ENABLED = false ✅
```

### 1-2. 브로커 정합성

```
GET /api/v1/account/230/reconciliation-report
→ broker_holdings_count    = 0
→ db_open_positions_count  = 0
```

**결론**: 브로커도, positions 테이블도 잔고 없음. 29개 open trade는 전량 DB 장부 누락 아티팩트.

### 1-3. 프리플라이트 통과 조건

| 조건 | 결과 |
|------|------|
| 실계좌 emergency_stop=true | ✅ |
| 모의계좌 broker_holdings=0 | ✅ |
| positions.qty=0 (대상 심볼 전체) | ✅ |
| 대상 trade 전량 exit_time IS NULL | ✅ (29개) |
| 청산 주문 필요 없음 | ✅ |

---

## 2. 조사 방법론 및 신뢰도 기준

### 닫힘 이벤트 3가지 유형

| 유형 | 설명 | 신뢰도 |
|------|------|--------|
| `sell_fill` | position_events에 `sell_fill` 이벤트 + 대응 SELL trade가 filled | **HIGH** |
| `sync` | position_events에 `sync` 이벤트로 before_quantity>0 → after_quantity=0 | **MEDIUM** |
| `self_cancelled` | trade 자체가 CANCELLED (SELL 주문이 취소됨, exit 개념) | **HIGH** |

### MEDIUM 신뢰도 이유

- `sync` 이벤트는 브로커 잔고를 DB에 반영하는 것으로, **닫힘의 원인이 아닌 결과**를 기록한다.
- 어느 시점에 포지션이 실제로 청산됐는지 확실하지 않고, sync 시점만 알 수 있다.
- sync 타임스탬프 = **"최소한 이 시점에는 닫혀 있었다"** 의미.
- 사용 값: `2026-07-01 01:56:00.592` (마지막 sync 이벤트 타임스탬프, 복수 심볼 공통)

---

## 3. 심볼별 닫힘 이벤트 맵

| symbol | closure_type | proposed_exit_time | source_trade_id | confidence |
|--------|-------------|-------------------|----------------|------------|
| 005380 | sync | 2026-07-01 01:56:00.592 | — | MEDIUM |
| 005930 | sell_fill | 2026-07-01 05:39:27.000 | trade 299 | HIGH |
| 010140 | sell_fill | 2026-06-24 23:30:56.000 | trade 294 | HIGH |
| 010950 | sell_fill | 2026-06-24 23:30:48.000 | trade 292 | HIGH |
| 011070 | sync | 2026-07-01 01:56:00.592 | — | MEDIUM |
| 015760 | sell_fill | 2026-06-24 02:47:53.000 | trade 279 | HIGH |
| 017670 (BUY v311) | sync | 2026-07-01 01:56:00.592 | — | MEDIUM |
| 017670 (SELL v316) | self_cancelled | 2026-06-24 23:30:59.611 | trade 295 entry_time | HIGH |
| 032830 | sell_fill | 2026-06-24 23:30:51.000 | trade 293 | HIGH |
| 051900 | sell_fill | 2026-06-24 02:59:43.000 | trade 283 | HIGH |
| 066570 | sell_fill | 2026-06-24 02:47:55.000 | trade 280 | HIGH |
| 086790 | sell_fill | 2026-06-24 03:03:02.000 | trade 284 | HIGH |
| 096770 | sync | 2026-07-01 01:56:00.592 | — | MEDIUM |
| 145020 | sync | 2026-07-01 01:56:00.592 | — | MEDIUM |
| 214150 | sell_fill | 2026-06-24 23:31:17.000 | trade 296 | HIGH |
| 373220 | sync | 2026-07-01 01:56:00.592 | — | MEDIUM |

신뢰도 분포: HIGH 10, MEDIUM 6, LOW 0

---

## 4. 29개 trade 정합성 맵 (전체)

형식: `trade_id | version_id | symbol | side | order_status | entry_time | proposed_exit_time | confidence | 근거`

### v297 (5개 open BUY, TESTING)

| trade_id | symbol | entry_time | proposed_exit_time | confidence | 근거 |
|----------|--------|------------|-------------------|------------|------|
| 272 | 005380 | 2026-06-23 02:38:57 | 2026-07-01 01:56:00.592 | MEDIUM | sync → qty=0 |
| 264 | 015760 | 2026-06-23 02:37:02 | 2026-06-24 02:47:53.000 | HIGH | trade 279 SELL filled |
| 273 | 066570 | 2026-06-23 02:38:59 | 2026-06-24 02:47:55.000 | HIGH | trade 280 SELL filled |
| 274 | 145020 | 2026-06-23 02:39:05 | 2026-07-01 01:56:00.592 | MEDIUM | sync → qty=0 |
| 265 | 373220 | 2026-06-23 02:37:07 | 2026-07-01 01:56:00.592 | MEDIUM | sync → qty=0 |

### v301 (5개 open BUY, DRAFT)

| trade_id | symbol | entry_time | proposed_exit_time | confidence | 근거 |
|----------|--------|------------|-------------------|------------|------|
| 271 | 005380 | 2026-06-23 02:38:54 | 2026-07-01 01:56:00.592 | MEDIUM | sync → qty=0 |
| 263 | 015760 | 2026-06-23 02:36:55 | 2026-06-24 02:47:53.000 | HIGH | trade 279 SELL filled |
| 270 | 066570 | 2026-06-23 02:38:51 | 2026-06-24 02:47:55.000 | HIGH | trade 280 SELL filled |
| 269 | 145020 | 2026-06-23 02:38:43 | 2026-07-01 01:56:00.592 | MEDIUM | sync → qty=0 |
| 262 | 373220 | 2026-06-23 02:36:52 | 2026-07-01 01:56:00.592 | MEDIUM | sync → qty=0 |

### v305 (3개 open BUY, DRAFT)

| trade_id | symbol | entry_time | proposed_exit_time | confidence | 근거 |
|----------|--------|------------|-------------------|------------|------|
| 277 | 005380 | 2026-06-23 02:39:55 | 2026-07-01 01:56:00.592 | MEDIUM | sync → qty=0 |
| 278 | 145020 | 2026-06-23 02:40:10 | 2026-07-01 01:56:00.592 | MEDIUM | sync → qty=0 |
| 268 | 373220 | 2026-06-23 02:37:24 | 2026-07-01 01:56:00.592 | MEDIUM | sync → qty=0 |

### v306 (4개 open BUY, TESTING)

| trade_id | symbol | entry_time | proposed_exit_time | confidence | 근거 |
|----------|--------|------------|-------------------|------------|------|
| 266 | 015760 | 2026-06-23 02:37:12 | 2026-06-24 02:47:53.000 | HIGH | trade 279 SELL filled |
| 275 | 066570 | 2026-06-23 02:39:30 | 2026-06-24 02:47:55.000 | HIGH | trade 280 SELL filled |
| 276 | 145020 | 2026-06-23 02:39:39 | 2026-07-01 01:56:00.592 | MEDIUM | sync → qty=0 |
| 267 | 373220 | 2026-06-23 02:37:19 | 2026-07-01 01:56:00.592 | MEDIUM | sync → qty=0 |

### v311 (5개 open BUY, DRAFT)

| trade_id | symbol | entry_time | proposed_exit_time | confidence | 근거 |
|----------|--------|------------|-------------------|------------|------|
| 286 | 010140 | 2026-06-24 03:09:12 | 2026-06-24 23:30:56.000 | HIGH | trade 294 SELL filled |
| 287 | 017670 | 2026-06-24 03:09:16 | 2026-07-01 01:56:00.592 | MEDIUM | sync → qty=0 |
| 288 | 032830 | 2026-06-24 03:09:20 | 2026-06-24 23:30:51.000 | HIGH | trade 293 SELL filled |
| 289 | 096770 | 2026-06-24 03:09:23 | 2026-07-01 01:56:00.592 | MEDIUM | sync → qty=0 |
| 285 | 214150 | 2026-06-24 03:03:08 | 2026-06-24 23:31:17.000 | HIGH | trade 296 SELL filled |

### v312 (4개 open BUY, TESTING)

| trade_id | symbol | entry_time | proposed_exit_time | confidence | 근거 |
|----------|--------|------------|-------------------|------------|------|
| 290 | 010950 | 2026-06-24 03:09:31 | 2026-06-24 23:30:48.000 | HIGH | trade 292 SELL filled |
| 291 | 011070 | 2026-06-24 03:09:34 | 2026-07-01 01:56:00.592 | MEDIUM | sync → qty=0 |
| 281 | 051900 | 2026-06-24 02:48:13 | 2026-06-24 02:59:43.000 | HIGH | trade 283 SELL filled |
| 282 | 086790 | 2026-06-24 02:48:21 | 2026-06-24 03:03:02.000 | HIGH | trade 284 SELL filled |

### v316 (1개 open SELL-CANCELLED, TESTING)

| trade_id | symbol | side | order_status | entry_time | proposed_exit_time | confidence | 근거 |
|----------|--------|------|-------------|------------|-------------------|------------|------|
| 295 | 017670 | sell | cancelled | 2026-06-24 23:30:59.611 | 2026-06-24 23:30:59.611 | HIGH | 자기자신 entry_time (취소 완료 시점) |

**v316 특이사항**: 이 버전에는 BUY trade가 없다. 취소된 SELL 주문만 있어 Archive Safety Rule을 기술적으로 위반하지 않는다. exit_time = entry_time으로 기록 (취소 완료 = 종료).

### v329 (2개 open BUY, ACTIVE)

| trade_id | symbol | entry_time | proposed_exit_time | confidence | 근거 |
|----------|--------|------------|-------------------|------------|------|
| 297 | 005930 | 2026-07-01 04:27:25 | 2026-07-01 05:39:27.000 | HIGH | trade 299 SELL filled (qty=2) |
| 298 | 005930 | 2026-07-01 05:11:52 | 2026-07-01 05:39:27.000 | HIGH | trade 299 SELL filled (qty=2) |

**v329 상세**: SELL trade 299 (exit_time=2026-07-01 05:39:27, qty=2, filled)가 두 BUY를 모두 커버한다. BUY trade 297+298의 합산 qty=2 = SELL qty=2. 정합.

---

## 5. 버전별 UPDATE 요약

| version_id | status | open trade 수 | 심볼 | HIGH | MEDIUM | 비고 |
|-----------|--------|--------------|------|------|--------|------|
| 297 | TESTING | 5 | 005380,015760,066570,145020,373220 | 2 | 3 | DEFER_OPEN_POSITION → 이후 archive |
| 301 | DRAFT | 5 | 005380,015760,066570,145020,373220 | 2 | 3 | 러너 비적격 (DRAFT) |
| 305 | DRAFT | 3 | 005380,145020,373220 | 0 | 3 | 러너 비적격 (DRAFT) |
| 306 | TESTING | 4 | 015760,066570,145020,373220 | 2 | 2 | DEFER_OPEN_POSITION → 이후 archive |
| 311 | DRAFT | 5 | 010140,017670,032830,096770,214150 | 3 | 2 | 러너 비적격 (DRAFT) |
| 312 | TESTING | 4 | 010950,011070,051900,086790 | 3 | 1 | DEFER_OPEN_POSITION → 이후 archive |
| 316 | TESTING | 1 | 017670 (SELL-CANCELLED) | 1 | 0 | BUY 없음, archive 가능 |
| 329 | ACTIVE | 2 | 005930,005930 | 2 | 0 | 현재 ACTIVE 버전 |
| **합계** | | **29** | | **15** | **14** | |

---

## 6. 제안 UPDATE 방법

### 6-1. 방법: 직접 SQL UPDATE (psql)

```sql
-- 반드시 BEGIN; 으로 감싸고 ROLLBACK으로 검증 먼저.
BEGIN;

-- ── v329: 005930 두 건 (HIGH) ──────────────────────────────
UPDATE trades SET exit_time = '2026-07-01 05:39:27' WHERE id IN (297, 298);

-- ── v312: 010950, 051900, 086790 (HIGH) ────────────────────
UPDATE trades SET exit_time = '2026-06-24 23:30:48' WHERE id = 290;  -- 010950
UPDATE trades SET exit_time = '2026-06-24 02:59:43' WHERE id = 281;  -- 051900
UPDATE trades SET exit_time = '2026-06-24 03:03:02' WHERE id = 282;  -- 086790

-- ── v312: 011070 (MEDIUM) ───────────────────────────────────
UPDATE trades SET exit_time = '2026-07-01 01:56:00.592' WHERE id = 291;

-- ── v311: 010140, 032830, 214150 (HIGH) ────────────────────
UPDATE trades SET exit_time = '2026-06-24 23:30:56' WHERE id = 286;  -- 010140
UPDATE trades SET exit_time = '2026-06-24 23:30:51' WHERE id = 288;  -- 032830
UPDATE trades SET exit_time = '2026-06-24 23:31:17' WHERE id = 285;  -- 214150

-- ── v311: 017670, 096770 (MEDIUM) ───────────────────────────
UPDATE trades SET exit_time = '2026-07-01 01:56:00.592' WHERE id IN (287, 289);

-- ── v316: 017670 SELL-CANCELLED (HIGH) ──────────────────────
UPDATE trades SET exit_time = '2026-06-24 23:30:59.611' WHERE id = 295;

-- ── v297: 015760, 066570 (HIGH) ─────────────────────────────
UPDATE trades SET exit_time = '2026-06-24 02:47:53' WHERE id = 264;  -- 015760
UPDATE trades SET exit_time = '2026-06-24 02:47:55' WHERE id = 273;  -- 066570

-- ── v297: 005380, 145020, 373220 (MEDIUM) ───────────────────
UPDATE trades SET exit_time = '2026-07-01 01:56:00.592' WHERE id IN (272, 274, 265);

-- ── v306: 015760, 066570 (HIGH) ─────────────────────────────
UPDATE trades SET exit_time = '2026-06-24 02:47:53' WHERE id = 266;  -- 015760
UPDATE trades SET exit_time = '2026-06-24 02:47:55' WHERE id = 275;  -- 066570

-- ── v306: 145020, 373220 (MEDIUM) ───────────────────────────
UPDATE trades SET exit_time = '2026-07-01 01:56:00.592' WHERE id IN (276, 267);

-- ── v301: 015760, 066570 (HIGH) ─────────────────────────────
UPDATE trades SET exit_time = '2026-06-24 02:47:53' WHERE id = 263;  -- 015760
UPDATE trades SET exit_time = '2026-06-24 02:47:55' WHERE id = 270;  -- 066570

-- ── v301: 005380, 145020, 373220 (MEDIUM) ───────────────────
UPDATE trades SET exit_time = '2026-07-01 01:56:00.592' WHERE id IN (271, 269, 262);

-- ── v305: 005380, 145020, 373220 (MEDIUM) ───────────────────
UPDATE trades SET exit_time = '2026-07-01 01:56:00.592' WHERE id IN (277, 278, 268);

-- 검증
SELECT id, version_id, symbol_code, side, order_status, entry_time, exit_time
FROM trades WHERE exit_time IS NOT NULL AND id IN (
  297,298,290,281,282,291,286,288,285,287,289,295,
  264,273,272,274,265,266,275,276,267,263,270,271,269,262,277,278,268
)
ORDER BY version_id, symbol_code;

-- 결과 확인 후 COMMIT 또는 ROLLBACK
-- COMMIT;
-- ROLLBACK;
```

### 6-2. 집행 전 검증 쿼리

```sql
-- 집행 전: 29개 모두 exit_time IS NULL 확인
SELECT count(*) FROM trades
WHERE id IN (
  297,298,290,281,282,291,286,288,285,287,289,295,
  264,273,272,274,265,266,275,276,267,263,270,271,269,262,277,278,268
)
AND exit_time IS NULL;
-- → 기대값: 29

-- 집행 후: 0개 남아야 함
SELECT count(*) FROM trades
WHERE id IN (
  297,298,290,281,282,291,286,288,285,287,289,295,
  264,273,272,274,265,266,275,276,267,263,270,271,269,262,277,278,268
)
AND exit_time IS NULL;
-- → 기대값: 0
```

---

## 7. 롤백 계획

### 7-1. 롤백 방법

```sql
-- 트랜잭션 안에서 실행했다면: COMMIT 전에 ROLLBACK 한 번으로 충분.
ROLLBACK;

-- 이미 COMMIT한 경우: 모든 대상 trade의 exit_time을 NULL로 복원.
UPDATE trades SET exit_time = NULL
WHERE id IN (
  297,298,290,281,282,291,286,288,285,287,289,295,
  264,273,272,274,265,266,275,276,267,263,270,271,269,262,277,278,268
);
```

### 7-2. 롤백 트리거 조건

| 조건 | 조치 |
|------|------|
| 업데이트 후 count ≠ 29 | ROLLBACK |
| 기대하지 않은 exit_time이 NULL이 아닌 trade에 영향 | ROLLBACK |
| 업데이트 후 positions/broker 상태가 달라짐 | 조사 후 결정 |

### 7-3. 롤백 안전성

- trades.exit_time 백필은 **읽기 전용 레코드 보정**이다.
- positions 테이블, position_events 테이블, risk_configs, strategy_versions를 건드리지 않는다.
- exit_time = NULL 복원으로 완전히 원상태로 되돌릴 수 있다.

---

## 8. 집행 제약 사항

| 항목 | 제약 |
|------|------|
| v329 (ACTIVE) | ACTIVE 버전이므로 극도로 주의. 집행 전 broker reconciliation 재확인 필수. |
| MEDIUM 신뢰도 14건 | 정확한 청산 시점 불명. sync 타임스탬프는 "최소 이 시점 이전에 닫힘" 의미. |
| DRAFT 버전 (301,305,311) | runner 비적격이나 exit_time 누락이 존재. 통계/분석에서 노이즈 제거 목적으로 동일 처리. |

---

## 9. 집행 후 다음 단계

집행 성공 후 다음 작업 순서:

1. **v316 archive**: BUY 없는 버전, exit_time 보정 후 즉시 archive 가능.
2. **v297, v306, v312 archive**: DEFER_OPEN_POSITION 해제 → archive.
3. **v301, v305, v311 archive/retire**: DRAFT 상태, 용도 검토 후 처리.
4. **v329 모니터링**: ACTIVE 버전, 정상 작동 확인.

---

## 10. 승인 체크리스트

집행 전 사람이 확인해야 할 항목:

- [x] 29개 trade_id 목록이 현재 DB 상태와 일치하는지 재확인
- [x] broker_holdings_count = 0 재확인 (집행 직전)
- [x] MEDIUM 신뢰도 14건에 sync 타임스탬프 사용 동의
- [x] v329 exit_time 백필 동의
- [x] 트랜잭션 내 사전/사후 검증 (DO 블록으로 count 불일치 시 자동 EXCEPTION → ROLLBACK)
- [x] COMMIT 전 집행 쿼리 검증값 확인 (29개 → 0개)

---

## 11. 집행 결과 (POSITION-DISPOSITION-APPLY-1 — 2026-07-02)

사용자 승인 후 §6 SQL을 트랜잭션(사전/사후 검증 DO 블록 포함)으로 집행했다.

| 항목 | 결과 |
|------|------|
| 백필된 trade 수 | 29 / 29 |
| 집행 후 open trades (exit_time IS NULL) | **0** |
| positions 테이블 | 무변경 (qty 합계 0 유지) |
| broker holdings | 0 (무변경) |
| 롤백 필요 | 없음 |

### 후속 집행 (같은 날, 사용자 승인)

**STRATEGY-ARCHIVE-APPLY-2**: 잔여 버전 7개 archive API 집행 — 전부 HTTP 200, status=archived.
- TESTING: v297, v306, v312, v316 (strategy 275)
- DRAFT: v301, v305, v311 (strategy 279)
- 집행 후 분포: archived=18, testing=5, draft=2
- 잔존 비보관: v300/v304/v317(KEEP_SIGNAL_ONLY), v307(DEFER_REVIEW), v329(스모크 테스트), v327/v328(신규 DRAFT — 정리 대상 아님)

**AI 분석 루프 활성화**: run-now 검증(4개 잡 전부 success) 후 활성화.
- `strategy_review` ✅ (versions_reviewed=5 — archive 정리로 11→5 감소 확인)
- `scanner_review` ✅ (versions_reviewed=3)
- `daily_analysis` ✅ (dual, analyzed=3, pending 제안 3건 생성: #13 v329, #14 v307, #15 v317)
- `intelligence_evolution` ✅ (last_error=null, 분석 대상 COMPLETED 실험 없어 no-op)
- 4개 잡 모두 `enabled=true`로 전환 (scheduler_job_overrides). 제안은 전부 pending — 승인은 사람.
