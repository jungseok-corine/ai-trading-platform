class KISAPIError(Exception):
    """KIS Open API가 rt_cd != '0' (실패) 응답을 반환했을 때 발생한다."""

    def __init__(self, msg_cd: str, msg1: str):
        self.msg_cd = msg_cd
        self.msg1 = msg1
        super().__init__(f"KIS API error [{msg_cd}]: {msg1}")


class RealTradingDisabledError(Exception):
    """real_trading_enabled=False인 상태에서 실전 주문 API가 호출될 때 발생한다.

    C-2.13: KIS_REAL_TRADING_ENABLED=true로 명시적으로 설정하지 않으면 실전 주문은 불가.
    잔고/체결 조회는 이 제약과 무관하게 허용된다.
    """
