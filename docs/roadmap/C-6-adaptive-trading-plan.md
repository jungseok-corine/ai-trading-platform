# C-6 — 당일 적응형 자동매매 갭 분석 및 로드맵

> 작성: 2026-07-03
> 기준점: "당일 시장 변동성에 맞춰 자동으로 전략을 조정하며 매매하는, 현실적으로 가장 가능성 있는 AI 자동매매 프로그램"
> 이 문서는 전체 시스템(프론트·백엔드·운영) 분석 결과와 C-6.x 로드맵을 정의한다.

---

## 1. 한 줄 결론

**연구소로서는 과할 정도로 완성됐고, 당일 적응형 자동매매기로서는 심장 두 개가 빠져 있다 —
백테스트 엔진과 인트라데이 적응 루프.** UI는 모든 내부 상태를 1급으로 노출하는 운영자 콘솔이라
사용자 관점 재편이 필요하다.

---

## 2. UI 정보 아키텍처 — 보여줄 것 vs 숨길 것

원칙: **사용자가 매일 내려야 하는 결정과 그 근거만 전면에. 시스템이 스스로 처리하는 과정은
이상이 생겼을 때만.**

### 전면 노출 (사용자 뷰)

| 항목 | 현재 상태 |
|---|---|
| 오늘의 손익·포지션·체결 | ✅ 있음 (dashboard, portfolio) |
| AI 의사결정 피드 ("오늘 AI가 무엇을 왜 했나") | ⚠️ 데이터는 있으나 한 화면에 서사로 없음 (analysis-audit·proposals·reports 파편화) |
| 승인 인박스 (pending 제안 + 근거·기대효과·리스크) | ✅ ActionInbox 있음 — 랜딩으로 승격 필요 |
| 안전 상태 한 줄 + 킬스위치 | ⚠️ SafetySection이 27개 섹션 중 하나로 묻힘 |
| 전략 스코어보드 (신 vs 구 버전 승패·회고 판정) | ⚠️ experiments·retro·promotion-readiness 3곳 분산 |

### 강등 (운영/진단 뷰 — 삭제 아님, 접기)

- funnel, ops-trend, analysis-audit, data-freshness, scheduler runs 상세, job 메타데이터, ai-cost 상세
  → 다이제스트 경보가 올라올 때만 진입하는 진단 뷰
- candidates 원목록, market context 원자료, transition plan 상세 → 제안 카드 요약 근거로 충분, 원자료는 드릴다운
- assignments, scanners 버전 관리 → 승인 플로우에 통합 가능

### 목표 구조

현재 31개 뷰(dashboard + research 27섹션) → 사용자 동선 **4뷰**:
`홈(오늘 요약+안전등+킬스위치)` / `승인함` / `전략 성적표` / `운영(접힘, 경보 시만)`

---

## 3. 과한 부분

1. **Paper 영역 내 승인 게이트 중복** — 후보 제안: 승인 → 실험 준비 → 준비 승인 3중 게이트.
   실전 배치 승인은 유지하되, paper 내 다단계 승인은 비전 원칙 2("Paper는 최대한 자동화")와 충돌.
2. **관측 인프라 > 매매 인프라 역전** — 관제 화면 25개 vs 백테스트 엔진 0. 관측은 이미 충분.
3. **dual LLM 상시 실행** — A/B 확정 후 single로 전환하면 비용·지연 절반.
4. **회고가 forward-only** — 하루 몇 건 표본으로 며칠~몇 주 대기. 백테스트 부재의 구조적 낭비.

---

## 4. 부족한 부분 (중요도순)

| # | 갭 | 내용 |
|---|---|---|
| ① | **백테스트 엔진 부재 (최대 갭)** | 검증 경로가 "승인 → paper 며칠 관찰"뿐. 개선 사이클 1~2주. 히스토리컬 리플레이로 초 단위 검증 필요 |
| ② | **인트라데이 적응 루프 부재** | 분석 루프 전부 장후 1회. 장중 변동성 레짐 감지 → **사람이 사전 승인한 파라미터 밴드 안에서** 자동 전환 필요 (밴드 승인=사람, 밴드 내 선택=자동 — 안전 불변식과 양립) |
| ③ | **실시간 데이터 부재** | REST 1분봉 폴링뿐. 인트라데이 감지의 재료 부족. ②의 선행 조건 |
| ④ | **변동성 사이징·자동 디리스킹 없음** | 사이징 fixed/cash_pct뿐. 리스크 룰은 진입차단형만. ATR 사이징 + 변동성 급등 시 신규 진입 자동 중단(soft kill) 필요 |
| ⑤ | **알림 미연결** | TelegramChannel 코드 있으나 이벤트 배선 없음. 승인 요청·안전 드리프트가 폰으로 와야 무인 시스템 완성 |
| ⑥ | **운영 인프라** | 로컬 docker 단일 서버. 배포 자동화·uptime 감시 없음 (Mac mini 보류 항목) |
| ⑦ | **전략 다양성·실행 품질** | 7종 전부 단일종목 TA. 슬리피지·체결 품질 측정 없음 (실전 전 필수) |

---

## 5. C-6.x 로드맵 (실행 순서)

> 안전 불변식 전부 유지: 실거래 off, AI 제안 자동 승인 금지, 새 잡 기본 비활성,
> 버전 덮어쓰기 금지. 아래 전부 paper 영역.
>
> **구현 완료 (2026-07-03)**: C-6.1~C-6.6 전부 DONE. 커밋: f8b658b(6.1), 6d162f9(6.2),
> 149f15e(6.3), 64cfdb1(6.4), 06cf565(6.5), e237fe6(6.6). 백엔드 2003 테스트 통과,
> 프론트 빌드 통과. C-6.3은 계획의 "장중 잡" 대신 **온디맨드 계산 + 60초 TTL 캐시**로
> 구현(신규 잡 표면 없이 러너·리스크가 필요 시 조회 — 더 단순하고 잡 관리 부담 없음).
> 신규 게이트 기본값: notification_events_enabled=false, volatility_soft_kill_enabled=false.

### C-6.1 — Backtest Engine `DONE`
- 저장된 market_data 위에서 전략 신호 생성기를 히스토리컬 리플레이 + 체결 시뮬레이션(다음 봉 시가,
  수수료 모델 재사용) + 지표 산출(승률·기대값·MDD·거래수).
- API: `POST /backtests` (전략 타입 + 파라미터 + 기간 + 종목) → 결과 저장·조회.
- 주문/브로커 호출 없음. 순수 read-only 계산.
- AI 제안 검증 경로에 연결: 제안 카드에 "백테스트 결과" 첨부 (후속 C-6.1b).

### C-6.2 — Telegram Notification Wiring `DONE`
- 기존 `TelegramChannel` + `operations_digest`를 이벤트에 배선:
  (a) pending 제안 생성 시, (b) 다이제스트 경보(이미 있음 — 채널만 설정), (c) 승격 후보 발생 시.
- 신규 백엔드 이벤트 훅은 config 게이트(기본 off). 시크릿은 `.env`만.

### C-6.3 — Intraday Volatility Regime `DONE`
- 최근 1분봉(기존 KIS polling 경로)으로 시장별 실현변동성·ATR z-score 계산 →
  calm / normal / elevated / extreme 분류. 스냅샷 저장 + `GET /intraday-regime`.
- 장중 N분 주기 잡(기본 off). websocket은 후속(C-6.3b) — 데이터 소스 어댑터로 교체 가능하게 설계.

### C-6.4 — Parameter Bands + In-Band Auto-Switching `DONE`
- StrategyVersion parameters에 선택 필드 `volatility_overrides`:
  `{"elevated": {"quantity_pct_scale": 0.5, "exit_drop_pct": 1.0}, "extreme": {...}}`.
- **사람이 밴드를 포함한 버전을 승인** → 러너가 현재 레짐에 맞는 오버라이드를 신호 생성 시 적용.
- 버전 상태·파라미터 원본 무변경(런타임 적용만). 적용 여부는 signal_logs에 기록.

### C-6.5 — Volatility Sizing + Soft Kill `DONE`
- 사이징: `quantity_mode=vol_scaled` — cash_pct를 현재 레짐 배율로 스케일.
- Soft kill: 리스크 룰 추가 — 레짐 extreme이면 신규 BUY 차단(SELL/청산은 허용). config 기본 off.
- 기존 포지션 자동 축소(강제 매도)는 **범위 제외** — 사람 결정 영역으로 보류.

### C-6.6 — UI 4-View Reorg `DONE`
- 홈(안전등+킬스위치+오늘 손익+AI 피드+승인 인박스) / 승인함 / 전략 성적표 / 운영(기존 섹션 접힘).
- 기존 섹션 삭제 없음 — 재배치·강등만. frontend-only.

### C-6 2차 구현분 (2026-07-03 야간, 전부 `DONE`)

| # | 작업 | 내용 |
|---|---|---|
| C-6.1b | 제안-백테스트 자동 연결 | 제안 생성 시 base vs proposed 백테스트 자동 첨부 (`strategy_proposals.backtest_summary`, 마이그레이션 t1u2v3w4x5y6). **유니버스 전략도 지원**(상위 5종목 집계 — 가동 버전 70%가 유니버스라 필수였음). 제안 카드에 비교 표+verdict 배지. 게이트 `proposal_backtest_enabled=true`(read-only 계산이라 기본 on) |
| C-6.7 | AI 의사결정 피드 | `GET /ai-activity-feed` — 분석 실행·제안 생성·사람 검토 타임라인. 홈 그룹 "AI 피드" |
| C-6.8 | 백테스트 콘솔 UI | 전략 성적표 그룹에서 파라미터 즉시 시뮬레이션 (기존 API 사용) |
| C-6.9 | 체결 품질 측정 | `GET /execution-quality` — 신호가 vs 체결가 슬리피지(양수=불리)·지연 집계 + UI |
| C-6.10 | 다이제스트 슬리피지 경보 | 평균 슬리피지 ≥0.5% & 표본 ≥10건이면 attention 경보 (→ Telegram 연결 시 폰 도착) |
| C-6.11 | LLM에 레짐 컨텍스트 주입 | 분석 번들·프롬프트에 당일 변동성 레짐 노출 — AI가 "장이 요동친 날"임을 알고 제안 |

수동 테스트: `docs/testing/manual-test-checklist-c6.md` (A~E 섹션).

### C-6.22 — 종목-전략 적합성 매칭 (D-31 실행) `DONE` (2026-07-06)
- 배정(assignment) 시 종목 일봉 추세성(trend/range)을 분류해 호환 strategy_type의 규칙을
  우선 선택: breakout류=추세 전용, rsi_reversion=횡보·하락 방어. 순수 분류기
  `trading/analysis/symbol_trendiness.py`(MA20/MA50 + 60일 수익률, regime_fit 어휘 재사용),
  배정 로그 `symbol_trendiness` 기록(u1v2w3x4y5z6). 게이트
  `assignment_fitness_matching_enabled=false`(기본 off). read-only — 버전 생성/주문 없음.

### 보류 (C-6 범위 외)
- C-6.3b websocket 실시간 (실장 검증 필요), Paper 승인 게이트 간소화 (승인 플로우 변경 — 사용자 결정 필요),
  백테스트 verdict vs 회고 적중률 메타 분석, Mac mini 배포.
