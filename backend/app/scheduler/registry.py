"""자율(연구/분석) 잡 레지스트리 — 웹에서 ON/OFF 토글 가능한 잡 정의.

매매 인접 잡(strategy_runner/order_sync/trading_state_sync)은 여기 포함하지 않는다.
여기 있는 잡은 모두 read-only 연구/집계 잡이며 주문과 무관하다.
시작 시(lifecycle)와 런타임 토글(SchedulerControlService)이 이 레지스트리를 공유한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI

from app.scheduler.jobs import (
    DAILY_ANALYSIS_JOB_ID,
    DAILY_REPORT_JOB_ID,
    DART_FINANCE_JOB_ID,
    DART_INGEST_JOB_ID,
    DATA_REFRESH_JOB_ID,
    EDGAR_INGEST_JOB_ID,
    INTELLIGENCE_DISCOVERY_JOB_ID,
    INTELLIGENCE_EVOLUTION_JOB_ID,
    INTELLIGENCE_EXPERIMENT_AUTOPILOT_JOB_ID,
    INTELLIGENCE_INGEST_JOB_ID,
    INTELLIGENCE_SCANNER_PROPOSAL_JOB_ID,
    INTRADAY_EVENT_MONITOR_JOB_ID,
    OPERATIONS_DIGEST_JOB_ID,
    PAPER_SIGNAL_SESSION_RUNNER_JOB_ID,
    RESEARCH_PIPELINE_JOB_ID,
    SCANNER_REVIEW_JOB_ID,
    STRATEGY_REVIEW_JOB_ID,
    US_MARKET_REFRESH_JOB_ID,
    run_daily_analysis_job,
    run_daily_report_job,
    run_dart_finance_job,
    run_dart_ingest_job,
    run_data_refresh_job,
    run_edgar_ingest_job,
    run_intelligence_discovery_job,
    run_intelligence_evolution_job,
    run_intelligence_experiment_autopilot_job,
    run_intelligence_ingest_job,
    run_intelligence_scanner_proposal_job,
    run_intraday_event_monitor_job,
    run_operations_digest_job,
    run_paper_signal_session_job,
    run_research_pipeline_job,
    run_scanner_review_job,
    run_strategy_review_job,
    run_us_market_refresh_job,
)


@dataclass(frozen=True)
class ControllableJob:
    job_id: str
    label_ko: str
    schedule_desc: str
    func: Callable[[FastAPI], Awaitable[None]]
    build_trigger: Callable[[Any], Any]  # settings -> APScheduler trigger
    env_enabled: Callable[[Any], bool]  # settings -> env 기본 활성 여부
    # ── C-3.1: read-only 위험도/특성 메타데이터 (실행 동작과 무관, 표시 전용) ──
    description: str = ""
    risk_level: str = "MANUAL_FIRST"  # SAFE_ON | MANUAL_FIRST | KEEP_OFF | DO_NOT_ENABLE
    recommended_state: str = "MANUAL_FIRST"  # ON_OK | MANUAL_FIRST | KEEP_OFF
    writes_db: bool = False
    uses_llm: bool = False
    external_network: bool = False
    creates_proposals: bool = False
    action_taking: bool = False  # 제안 승인/ACTIVE 생성/실전주문 등 실제 적용 행동 (여기선 전부 False)
    paper_action: bool = False  # paper 실험 상태 변경(auto-conclude 등). 실전 거래 아님
    cost_risk: bool = False  # LLM 등 유료 호출 가능성
    data_volume_risk: bool = False  # 다수 레코드 생성 가능
    affects_live_trading: bool = False  # 항상 False — 어떤 잡도 실전 거래/주문/브로커에 영향 없음
    safety_notes: tuple[str, ...] = ()


_NO_LIVE = "실전 주문 영향 없음"

CONTROLLABLE_JOBS: list[ControllableJob] = [
    ControllableJob(
        job_id=RESEARCH_PIPELINE_JOB_ID,
        label_ko="연구 파이프라인 (스캔→후보→배정)",
        schedule_desc="5분 간격",
        func=run_research_pipeline_job,
        build_trigger=lambda s: IntervalTrigger(seconds=s.research_pipeline_interval_seconds),
        env_enabled=lambda s: s.research_pipeline_scheduler_enabled,
        description="시장 데이터를 스캔해 후보를 찾고 전략에 배정하는 연구 파이프라인 (결정론적, LLM 미사용).",
        risk_level="MANUAL_FIRST",
        recommended_state="MANUAL_FIRST",
        writes_db=True,
        data_volume_risk=True,
        safety_notes=("다수의 candidate/assignment 레코드 생성 가능", "LLM 미사용", _NO_LIVE),
    ),
    ControllableJob(
        job_id=DATA_REFRESH_JOB_ID,
        label_ko="수급 데이터 수집",
        schedule_desc="매일 16:00",
        func=run_data_refresh_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.data_refresh_scheduler_hour, minute=s.data_refresh_scheduler_minute
        ),
        env_enabled=lambda s: s.data_refresh_scheduler_enabled,
        description="KIS API에서 투자자별 수급 데이터를 수집해 저장한다.",
        risk_level="MANUAL_FIRST",
        recommended_state="MANUAL_FIRST",
        writes_db=True,
        external_network=True,
        safety_notes=("KIS API 호출 — 레이트리밋 주의", _NO_LIVE),
    ),
    ControllableJob(
        job_id=US_MARKET_REFRESH_JOB_ID,
        label_ko="미국장 스냅샷 수집",
        schedule_desc="매일 07:00",
        func=run_us_market_refresh_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.us_market_refresh_scheduler_hour, minute=s.us_market_refresh_scheduler_minute
        ),
        env_enabled=lambda s: s.us_market_refresh_scheduler_enabled,
        description="미국장 일별 스냅샷(지수/금리/VIX 등)을 수집한다. 기본 provider=manual이면 외부 호출 없음.",
        risk_level="MANUAL_FIRST",
        recommended_state="MANUAL_FIRST",
        writes_db=True,
        external_network=True,
        safety_notes=("기본 provider=manual은 외부 호출 없음(no-op)", _NO_LIVE),
    ),
    ControllableJob(
        job_id=DAILY_ANALYSIS_JOB_ID,
        label_ko="AI 일일 분석 (LLM)",
        schedule_desc="매일 15:40",
        func=run_daily_analysis_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.ai_daily_analysis_scheduler_hour, minute=s.ai_daily_analysis_scheduler_minute
        ),
        env_enabled=lambda s: s.ai_daily_analysis_enabled,
        description="AI가 활성 전략 버전을 일일 분석해 기록한다 (읽기 전용 메타 분석). provider≠fake면 LLM 유료 호출.",
        risk_level="KEEP_OFF",
        recommended_state="KEEP_OFF",
        writes_db=True,
        uses_llm=True,
        external_network=True,
        cost_risk=True,
        safety_notes=("provider≠fake 시 LLM 유료 호출", "읽기 전용 분석 — 제안/승인 없음", _NO_LIVE),
    ),
    ControllableJob(
        job_id=SCANNER_REVIEW_JOB_ID,
        label_ko="스캐너 개선 제안 (검토)",
        schedule_desc="매일 16:10",
        func=run_scanner_review_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.scanner_review_scheduler_hour, minute=s.scanner_review_scheduler_minute
        ),
        env_enabled=lambda s: s.scanner_review_scheduler_enabled,
        description="스캐너 룰 성과를 점검해 개선 제안(pending)을 생성한다 (휴리스틱, LLM 미사용).",
        risk_level="KEEP_OFF",
        recommended_state="KEEP_OFF",
        writes_db=True,
        creates_proposals=True,
        data_volume_risk=True,
        safety_notes=("pending 제안만 생성 — 자동 승인/활성화 없음", _NO_LIVE),
    ),
    ControllableJob(
        job_id=STRATEGY_REVIEW_JOB_ID,
        label_ko="전략 개선 제안 (검토)",
        schedule_desc="매일 16:20",
        func=run_strategy_review_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.strategy_review_scheduler_hour, minute=s.strategy_review_scheduler_minute
        ),
        env_enabled=lambda s: s.strategy_review_scheduler_enabled,
        description="전략 버전 성과를 점검해 개선 제안(pending)을 생성한다 (휴리스틱, LLM 미사용).",
        risk_level="KEEP_OFF",
        recommended_state="KEEP_OFF",
        writes_db=True,
        creates_proposals=True,
        data_volume_risk=True,
        safety_notes=("pending 제안만 생성 — 자동 승인/활성화 없음", _NO_LIVE),
    ),
    ControllableJob(
        job_id=DAILY_REPORT_JOB_ID,
        label_ko="일일 리포트",
        schedule_desc="매일 15:45",
        func=run_daily_report_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.daily_report_scheduler_hour, minute=s.daily_report_scheduler_minute
        ),
        env_enabled=lambda s: s.daily_report_scheduler_enabled,
        description="일일 연구 리포트를 생성해 저장한다 (읽기 전용 집계).",
        risk_level="SAFE_ON",
        recommended_state="ON_OK",
        writes_db=True,
        safety_notes=(_NO_LIVE,),
    ),
    ControllableJob(
        job_id=OPERATIONS_DIGEST_JOB_ID,
        label_ko="운영 다이제스트",
        schedule_desc="매일 16:30",
        func=run_operations_digest_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.operations_digest_scheduler_hour, minute=s.operations_digest_scheduler_minute
        ),
        env_enabled=lambda s: s.operations_digest_scheduler_enabled,
        description="운영 상태를 집계해 다이제스트/스냅샷을 기록한다 (읽기 전용 리포트).",
        risk_level="SAFE_ON",
        recommended_state="ON_OK",
        writes_db=True,
        safety_notes=("알림 채널 미설정 시 외부 전송 없음(no-op)", _NO_LIVE),
    ),
    ControllableJob(
        job_id=DART_INGEST_JOB_ID,
        label_ko="DART 공시 수집",
        schedule_desc="10분 간격",
        func=run_dart_ingest_job,
        build_trigger=lambda s: IntervalTrigger(seconds=s.dart_ingest_interval_seconds),
        env_enabled=lambda s: s.dart_ingest_scheduler_enabled,
        description="DART 공시를 주기적으로 수집해 저장한다.",
        risk_level="MANUAL_FIRST",
        recommended_state="MANUAL_FIRST",
        writes_db=True,
        external_network=True,
        data_volume_risk=True,
        safety_notes=("DART API 호출 — 레이트리밋 주의", _NO_LIVE),
    ),
    ControllableJob(
        job_id=EDGAR_INGEST_JOB_ID,
        label_ko="SEC EDGAR 공시 수집 (미국)",
        schedule_desc="30분 간격(미국장)",
        func=run_edgar_ingest_job,
        build_trigger=lambda s: IntervalTrigger(seconds=s.edgar_ingest_interval_seconds),
        env_enabled=lambda s: s.edgar_ingest_scheduler_enabled,
        description="SEC EDGAR 미국 공시를 주기적으로 수집해 저장한다.",
        risk_level="MANUAL_FIRST",
        recommended_state="MANUAL_FIRST",
        writes_db=True,
        external_network=True,
        data_volume_risk=True,
        safety_notes=("SEC EDGAR 호출 — 레이트리밋 주의", _NO_LIVE),
    ),
    ControllableJob(
        job_id=INTRADAY_EVENT_MONITOR_JOB_ID,
        label_ko="보유종목 장중 공시 감시",
        schedule_desc="10분 간격(장중)",
        func=run_intraday_event_monitor_job,
        build_trigger=lambda s: IntervalTrigger(
            seconds=s.intraday_event_monitor_interval_seconds
        ),
        env_enabled=lambda s: s.intraday_event_monitor_scheduler_enabled,
        description="보유/활성 종목의 장중 공시를 감시해 중요 알림을 기록한다 (감시 대상 한정).",
        risk_level="MANUAL_FIRST",
        recommended_state="MANUAL_FIRST",
        writes_db=True,
        external_network=True,
        safety_notes=("감시 대상(보유/활성) 종목 한정", _NO_LIVE),
    ),
    ControllableJob(
        job_id=DART_FINANCE_JOB_ID,
        label_ko="DART 재무제표 수집 (XBRL)",
        schedule_desc="매일 02:00",
        func=run_dart_finance_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.dart_finance_scheduler_hour, minute=s.dart_finance_scheduler_minute
        ),
        env_enabled=lambda s: s.dart_finance_scheduler_enabled,
        description="DART XBRL 재무제표를 수집해 저장한다.",
        risk_level="MANUAL_FIRST",
        recommended_state="MANUAL_FIRST",
        writes_db=True,
        external_network=True,
        data_volume_risk=True,
        safety_notes=("DART XBRL 호출", _NO_LIVE),
    ),
    ControllableJob(
        job_id=INTELLIGENCE_INGEST_JOB_ID,
        label_ko="Intelligence 수집 파이프라인",
        schedule_desc="매일 06:00",
        func=run_intelligence_ingest_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.intelligence_ingest_scheduler_hour,
            minute=s.intelligence_ingest_scheduler_minute,
        ),
        env_enabled=lambda s: s.intelligence_ingest_scheduler_enabled,
        description="뉴스 등 인텔리전스 소스를 수집해 이벤트로 저장한다 (어댑터 기반).",
        risk_level="MANUAL_FIRST",
        recommended_state="MANUAL_FIRST",
        writes_db=True,
        external_network=True,
        data_volume_risk=True,
        safety_notes=("외부 소스(RSS 등) 호출", _NO_LIVE),
    ),
    ControllableJob(
        job_id=INTELLIGENCE_DISCOVERY_JOB_ID,
        label_ko="Intelligence 후보 발굴",
        schedule_desc="매일 07:00",
        func=run_intelligence_discovery_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.intelligence_discovery_scheduler_hour,
            minute=s.intelligence_discovery_scheduler_minute,
        ),
        env_enabled=lambda s: s.intelligence_discovery_scheduler_enabled,
        description="수집된 이벤트에서 후보 종목을 발굴해 저장한다 (결정론적, LLM 미사용).",
        risk_level="MANUAL_FIRST",
        recommended_state="MANUAL_FIRST",
        writes_db=True,
        data_volume_risk=True,
        safety_notes=("LLM 미사용(결정론적)", _NO_LIVE),
    ),
    ControllableJob(
        job_id=INTELLIGENCE_SCANNER_PROPOSAL_JOB_ID,
        label_ko="Intelligence 기반 스캐너 룰 개선 제안 (LLM)",
        schedule_desc="매일 08:00",
        func=run_intelligence_scanner_proposal_job,
        build_trigger=lambda s: CronTrigger(
            hour=s.intelligence_scanner_proposal_scheduler_hour,
            minute=s.intelligence_scanner_proposal_scheduler_minute,
        ),
        env_enabled=lambda s: s.intelligence_scanner_proposal_scheduler_enabled,
        description="인텔리전스 맥락을 근거로 LLM이 스캐너 룰 개선 제안(pending)을 생성한다.",
        risk_level="KEEP_OFF",
        recommended_state="KEEP_OFF",
        writes_db=True,
        uses_llm=True,
        external_network=True,
        creates_proposals=True,
        cost_risk=True,
        safety_notes=("LLM 유료 호출", "pending 제안만 생성 — 자동 승인 없음", _NO_LIVE),
    ),
    ControllableJob(
        job_id=INTELLIGENCE_EXPERIMENT_AUTOPILOT_JOB_ID,
        label_ko="Intelligence Paper 실험 자동 종료 점검 (C-2.27)",
        schedule_desc="1시간 간격",
        func=run_intelligence_experiment_autopilot_job,
        build_trigger=lambda s: IntervalTrigger(
            seconds=s.intelligence_experiment_autopilot_interval_seconds
        ),
        env_enabled=lambda s: s.intelligence_experiment_autopilot_scheduler_enabled,
        description="RUNNING paper 실험을 점검해 종료 조건 충족 시 자동 종료(conclude)한다. 주문/전략 실행 없음.",
        risk_level="MANUAL_FIRST",
        recommended_state="MANUAL_FIRST",
        writes_db=True,
        paper_action=True,
        safety_notes=("Paper 실험 상태만 변경(auto-conclude) — 실전 거래 아님", "주문/전략 실행 없음", _NO_LIVE),
    ),
    ControllableJob(
        job_id=INTELLIGENCE_EVOLUTION_JOB_ID,
        label_ko="Intelligence AI Evolution Loop (C-2.28)",
        schedule_desc="1시간 간격",
        func=run_intelligence_evolution_job,
        build_trigger=lambda s: IntervalTrigger(
            seconds=s.intelligence_evolution_interval_seconds
        ),
        env_enabled=lambda s: s.intelligence_evolution_scheduler_enabled,
        description="완료된 paper 실험을 LLM이 분석해 개선 제안(pending)을 생성한다.",
        risk_level="KEEP_OFF",
        recommended_state="KEEP_OFF",
        writes_db=True,
        uses_llm=True,
        external_network=True,
        creates_proposals=True,
        cost_risk=True,
        safety_notes=("LLM 유료 호출", "pending 제안만 생성 — 자동 승인 없음", _NO_LIVE),
    ),
    ControllableJob(
        job_id=PAPER_SIGNAL_SESSION_RUNNER_JOB_ID,
        label_ko="Paper 신호 세션 실행기 (signal-only)",
        schedule_desc="1분 간격",
        func=run_paper_signal_session_job,
        build_trigger=lambda s: IntervalTrigger(
            seconds=s.paper_signal_session_runner_interval_seconds
        ),
        env_enabled=lambda s: s.paper_signal_session_runner_enabled,
        description=(
            "active Paper Signal Session의 DRAFT 전략 버전으로 SignalLog만 기록한다. "
            "TradeService 미구성 — 주문/체결/브로커 주문 없음. 버전은 DRAFT 유지."
        ),
        risk_level="MANUAL_FIRST",
        recommended_state="MANUAL_FIRST",
        writes_db=True,
        external_network=True,
        data_volume_risk=True,
        safety_notes=(
            "SignalLog만 기록 — 주문/체결/Trade 없음",
            "TradeService/주문 클라이언트 미구성",
            "연결 StrategyVersion은 DRAFT 유지 → trade-capable runner가 보지 못함",
            "KIS 시세(캔들) 조회만 — 주문 TR 없음",
            _NO_LIVE,
        ),
    ),
]

CONTROLLABLE_BY_ID: dict[str, ControllableJob] = {j.job_id: j for j in CONTROLLABLE_JOBS}


def apply_job_enabled(app: FastAPI, settings: Any, job: ControllableJob, enabled: bool) -> None:
    """실행 중인 scheduler에 잡을 추가/제거해 토글을 즉시 반영한다."""
    scheduler: AsyncIOScheduler | None = getattr(app.state, "scheduler", None)
    if scheduler is None:
        return
    existing = scheduler.get_job(job.job_id)
    if enabled and existing is None:
        scheduler.add_job(
            job.func,
            trigger=job.build_trigger(settings),
            id=job.job_id,
            args=[app],
            max_instances=1,
            replace_existing=True,
        )
    elif not enabled and existing is not None:
        scheduler.remove_job(job.job_id)
