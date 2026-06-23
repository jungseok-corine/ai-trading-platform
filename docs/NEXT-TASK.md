# NEXT-TASK.md — Claude가 다음에 무엇을 할지 판단하는 기준 파일

> Claude는 세션 시작 시 이 파일을 먼저 읽는다.
> 작업 완료 시 이 파일의 Status를 DONE으로 갱신하고, "Next Task After Completion"을 새 Current Task로 업데이트한다.

---

## Current Task

**C-2.21.0 — DartLab Feasibility Spike**

| 필드 | 값 |
|------|----|
| **Status** | `READY` |
| **Priority** | 높음 |
| **Type** | Spike (기능 구현 없음, 검증·설계만) |

---

## Goal

DartLab 라이브러리를 우리 Market Intelligence Core의 데이터 어댑터로 사용할 수 있는지 검증한다.

구체적으로:
1. DartLab이 무엇인지, 어떤 데이터를 제공하는지 파악
2. 우리 환경(Python, FastAPI, asyncio, PostgreSQL)과 호환 가능한지 확인
3. DART / EDGAR / 뉴스 / 매크로 데이터 중 DartLab이 커버하는 범위 파악
4. 어댑터 패턴으로 통합할 수 있는 설계 초안 작성
5. "사용 가능 / 부분 사용 / 대안 필요" 중 하나로 결론 도출

---

## Background

현재 시스템에는 다음 데이터 수집기가 구현되어 있다:
- `DartProvider` / `DartIngestService` — DART 공시 수집 (기본 비활성)
- `EdgarProvider` / `EdgarIngestService` — SEC EDGAR 공시 수집 (기본 비활성)
- `NewsCuratorService` — 수집된 공시를 뉴스로 취급 (실제 RSS 뉴스 없음)
- `InvestorFlowService` — 수급 데이터 수집 (기본 비활성)
- `MacroRegimeService` — FRED/Twelve Data 기반 거시 체제 분류

**갭**: 실제 뉴스 RSS, 더 풍부한 공시 메타데이터, 테마/섹터 데이터가 없다.

**DartLab 가설**: DartLab(또는 유사한 오픈소스 DART 클라이언트)이 우리가 직접 구현한 것보다
더 풍부한 공시 메타데이터, 뉴스, 재무 데이터를 제공할 수 있을 것이다.

---

## Scope (이번 작업에서 할 것)

### 검증 항목

1. **설치 가능성**
   - DartLab pip 설치 가능 여부
   - 의존성 충돌 (httpx, SQLAlchemy, pydantic v2 등)
   - 컨테이너 환경(네트워크 제한)에서 설치 가능한지

2. **라이선스**
   - 상업적 사용 가능 여부
   - 재배포 제약 여부

3. **데이터 범위 확인**
   - DART 공시: 우리 `DartProvider`와 중복/보완 관계
   - EDGAR 공시: 커버하는지 여부
   - 뉴스: RSS나 뉴스 피드 제공 여부
   - 재무 데이터: 제공 여부 (필요성 평가)
   - 매크로 데이터: 제공 여부

4. **캐시 구조**
   - 로컬 캐시 방식 (SQLite, 파일 등) → 우리 PostgreSQL과 충돌 여부
   - 캐시 우회 가능 여부 (우리 DB에 직접 저장하려면)

5. **async 호환성**
   - async/await 지원 여부
   - 없다면 `asyncio.to_thread`로 감쌀 수 있는지

### 어댑터 설계 스케치

DartLab을 우리 어댑터 패턴에 통합한다면 어떤 구조가 적합한지 초안 작성:

```python
# 예시 설계 스케치 (실제 구현 아님)
class DartLabAdapter(BaseIntelligenceAdapter):
    async def fetch_disclosures(self, ...): ...
    async def fetch_news(self, ...): ...
```

---

## Out of Scope (이번 작업에서 하지 말 것)

- Market Intelligence Core DB 스키마 구현 → C-2.21.1에서
- 실제 수집 파이프라인 구현 → C-2.22에서
- 기존 `DartProvider` / `EdgarProvider` 코드 수정 → 이번 Spike에서 하지 않음
- 실주문 또는 실계좌 관련 코드 건드리기
- 대규모 리팩토링

---

## Safety Constraints

이 Spike 작업 동안 반드시 지켜야 할 안전 규칙:

- `KIS_REAL_TRADING_ENABLED=false` 유지
- 실주문 API 호출 없음
- 기존 DB 스키마 변경 없음
- 기존 수집기(`DartProvider`, `EdgarIngestService`) 변경 없음
- `.env`, API 키, 시크릿 값 출력 없음

---

## Definition of Done

다음 조건이 모두 충족되면 완료:

- [ ] DartLab(또는 동등한 라이브러리) 설치 가능성 검증 완료
- [ ] 라이선스 확인 완료
- [ ] 제공 데이터 범위 목록 작성 완료 (DART/EDGAR/뉴스/매크로 각각)
- [ ] async 호환성 검토 완료
- [ ] 어댑터 통합 설계 초안 작성 완료
- [ ] "사용 가능 / 부분 사용 / 대안 필요" 결론 도출
- [ ] 결론과 설계를 `docs/design/C-2.21.0-dartlab-spike.md`에 문서화
- [ ] 코드 변경 없음 (Spike이므로 코드 구현 없음)

---

## Expected Report Format

작업 완료 후 다음 형식으로 보고한다:

```
## 완료 보고: C-2.21.0 DartLab Feasibility Spike

### 결론
[사용 가능 / 부분 사용 / 대안 필요] — 한 줄 요약

### DartLab 검증 결과
- 설치 가능성: ✅ / ❌
- 라이선스: ✅ / ⚠️
- async 호환성: ✅ / ⚠️ (감싸기 필요) / ❌
- 데이터 범위: DART ✅ / EDGAR ✅/❌ / 뉴스 ✅/❌ / 매크로 ✅/❌

### 어댑터 설계 초안
[코드 스케치 또는 링크]

### 권장사항
[다음 단계 제안]

### 코드 변경 여부
없음 (Spike)
```

---

## Next Task After Completion

**C-2.21.1 — Market Intelligence Core Foundation**

DartLab Spike 결론에 따라:
- "사용 가능" → DartLab 어댑터를 Market Intelligence Core에 통합
- "부분 사용" → 기존 DartProvider를 DartLab으로 보강
- "대안 필요" → 직접 구현 또는 다른 라이브러리 선택

→ 결론을 `docs/DECISIONS.md`에 기록하고 C-2.21.1 진행
