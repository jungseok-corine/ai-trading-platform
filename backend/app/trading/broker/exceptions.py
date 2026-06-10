class KISAPIError(Exception):
    """KIS Open API가 rt_cd != '0' (실패) 응답을 반환했을 때 발생한다."""

    def __init__(self, msg_cd: str, msg1: str):
        self.msg_cd = msg_cd
        self.msg1 = msg1
        super().__init__(f"KIS API error [{msg_cd}]: {msg1}")
