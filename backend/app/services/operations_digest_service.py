from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.data_freshness_service import DataFreshnessService
from app.services.operations_overview_service import OperationsOverviewService
from app.services.portfolio_summary_service import PortfolioSummaryService
from app.services.scheduler_health_service import SchedulerHealthService

# 심각도 순서(정렬/집계용).
_SEVERITY_ORDER = {"ok": 0, "attention": 1, "alert": 2}
# 단일 종목 노출이 이 % 이상이면 집중 위험으로 본다.
_CONCENTRATION_PCT = 40.0


class OperationsDigestService:
    """운영 종합을 '조치가 필요한 것'만 추려 사람이 읽을 다이제스트로 만든다 (C-3.8).

    운영 종합(C-3.5)을 받아 안전 드리프트/예산 초과/검토 대기/공시 알림/회고 악화 등
    '봐야 할 것'만 한 줄씩 뽑는다. read-only 생성 — 어떤 상태도 바꾸지 않으며, 외부로
    보내는 행위는 별도 알림 채널(기본 none/no-op)의 몫이다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._overview = OperationsOverviewService(session)
        self._freshness = DataFreshnessService(session)
        self._scheduler = SchedulerHealthService(session)
        self._portfolio = PortfolioSummaryService(session)

    async def build(self, days: int = 30) -> dict:
        ov = await self._overview.overview(days=days)
        alerts: list[dict] = []

        safety = ov["safety"]
        if not safety["invariants_ok"]:
            for w in safety["warnings"]:
                alerts.append({"level": "alert", "text": f"안전 불변식: {w}"})

        cost = ov["cost"]
        if cost["budget_status"] == "over":
            alerts.append({
                "level": "alert",
                "text": f"AI 비용 예산 초과 ({cost['budget_used_pct']}% 사용)",
            })
        elif cost["budget_status"] == "warn":
            alerts.append({
                "level": "attention",
                "text": f"AI 비용 예산 임계 도달 ({cost['budget_used_pct']}% 사용)",
            })

        research = ov["research"]
        if research["disclosure_alerts"]:
            alerts.append({
                "level": "attention",
                "text": f"중요 공시 알림 {research['disclosure_alerts']}건 — 확인 필요",
            })
        if research["pending_total"]:
            alerts.append({
                "level": "attention",
                "text": f"검토 대기 제안 {research['pending_total']}건",
            })
        if research.get("promotion_ready"):
            alerts.append({
                "level": "attention",
                "text": f"승격 기준 통과 전략 {research['promotion_ready']}개 — 검토하세요(실거래는 사람만)",
            })

        retro = ov["retrospective"]
        if retro["worse"] > retro["improved"]:
            alerts.append({
                "level": "attention",
                "text": f"회고 악화({retro['worse']}) > 개선({retro['improved']}) — 제안 기준 재검토",
            })

        trading = ov["trading"]
        if trading["closed_trades"] and trading["total_pnl"] < 0:
            alerts.append({
                "level": "attention",
                "text": f"기간 실현손익 마이너스 ({trading['total_pnl']:,.0f}) — 거래 점검",
            })
        # 차단이 충분히 쌓였고 비율이 높으면(검토 표본 5건↑, 50%↑) 알린다.
        if (trading["risk_rejected"] >= 5 and trading["risk_rejection_rate"] is not None
                and trading["risk_rejection_rate"] >= 50):
            alerts.append({
                "level": "attention",
                "text": f"리스크 차단률 {trading['risk_rejection_rate']}% — 전략/리스크 설정 점검",
            })

        freshness = await self._freshness.status()
        if freshness["stale_count"]:
            alerts.append({
                "level": "attention",
                "text": f"데이터 신선도: {', '.join(freshness['stale_sources'])} 오래됨 — 수집 점검",
            })

        scheduler = await self._scheduler.status()
        if scheduler["unhealthy_count"]:
            alerts.append({
                "level": "alert",
                "text": f"자율 잡 이상: {', '.join(scheduler['unhealthy_jobs'])} — 스케줄러 점검",
            })

        portfolio = await self._portfolio.summary()
        concentrated = [
            p for p in portfolio["positions"]
            if p["exposure_pct"] is not None and p["exposure_pct"] >= _CONCENTRATION_PCT
        ]
        for p in concentrated:
            alerts.append({
                "level": "attention",
                "text": f"포지션 집중: {p['symbol_code']} {p['exposure_pct']}% — 분산 검토",
            })

        severity = "ok"
        for a in alerts:
            if _SEVERITY_ORDER[a["level"]] > _SEVERITY_ORDER[severity]:
                severity = a["level"]
        alerts.sort(key=lambda a: _SEVERITY_ORDER[a["level"]], reverse=True)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "severity": severity,
            "has_alerts": bool(alerts),
            "alerts": alerts,
            "summary_line": self._summary_line(severity, alerts),
        }

    @staticmethod
    def _summary_line(severity: str, alerts: list[dict]) -> str:
        if not alerts:
            return "✅ 조치가 필요한 항목이 없습니다."
        icon = "🔴" if severity == "alert" else "🟠"
        return f"{icon} 조치 필요 {len(alerts)}건 (최고 심각도: {severity})"

    def render_text(self, digest: dict) -> str:
        """다이제스트를 알림 채널로 보낼 평문으로 렌더링한다."""
        lines = [digest["summary_line"]]
        for a in digest["alerts"]:
            mark = "‼️" if a["level"] == "alert" else "•"
            lines.append(f"{mark} {a['text']}")
        return "\n".join(lines)
