# 런북: 월요일(2026-07-06) 장 시작 점검

> 후임 모델용. 09:30 KST 이후 실행. B모드(점검 + 명확한 버그는 수정·커밋) 사용자 사전 위임됨.
> DB: `docker exec backend-db-1 psql -U trading -d trading_platform`

## 1. 후보 공급 재개 (금요일 스캐너 완화 룰버전 14~16의 첫 시험)
```sql
SELECT count(*), max(triggered_at) FROM candidate_events WHERE triggered_at >= '2026-07-06';
```
- 후보 > 0 → 완화 성공. 0이면 research_pipeline 요약의 scanned/matched 조사:
```sql
SELECT left(summary::text,300) FROM scheduler_runs WHERE job_id='research_pipeline' ORDER BY id DESC LIMIT 2;
```

## 2. 일봉 전략 첫 가동 (v334 breakout / v335 rsi)
```sql
SELECT strategy_version_id, count(*), max(generated_at) FROM signal_logs
WHERE strategy_version_id IN (334,335) GROUP BY 1;
```
- 신호 0이어도 **돌파/과매도 조건 미충족이면 정상**. 비정상 판별: 러너 오류
  (`scheduler_runs` strategy_runner failed) 또는 signal_service 신선도 가드 로그.
- 함께 확인: `signal_logs.timeframe='1d'`로 기록되는지, KIS 일봉 조회 오류 없는지.

## 3. v304 최종 판정 (사전 위임된 결정)
- 후보가 흐르는데도(1번 성공) v304 신호가 계속 0이면 → 아카이브:
  `POST /api/v1/strategies/282/versions/304/archive`
- 후보가 안 흐르면(1번 실패) 판정 보류 — 재료 부족은 전략 잘못이 아님.

## 4. 진짜 5m 재축적 확인 (C-6.18 수정 후 첫 장)
```sql
SELECT ts FROM market_data WHERE timeframe='5m' AND symbol_code ~ '^[0-9]{6}$' ORDER BY ts DESC LIMIT 5;
```
- KR 5m 행이 **5분 간격**으로 나타나야 함. 1분 간격이면 C-6.18 회귀 — 즉시 조사.

## 5. 주말~월요일 잡 실패
```sql
SELECT job_id, status, left(error_message,80) FROM scheduler_runs
WHERE started_at >= '2026-07-04' AND status='failed' LIMIT 10;
```
- transient(단발+직후 복구, 레이트리밋/장마감)는 기록만. 구조적이면 수정 →
  전체 pytest 통과 확인 후 커밋·push (**pytest를 `| tail`로 파이프하지 말 것 — exit code 가림**).

## 6. 레짐 확인
`curl http://localhost:8000/api/v1/intraday-regime` — 장중 unknown이 아니어야 함 (5m 재축적과 연동).

## 7. 보고
결과를 한국어로 사용자에게 보고. 금지: 실주문, 제안 자동 승인, 게이트 기본값 변경, 서버 재시작.
