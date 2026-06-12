def normalize_order_id(order_id: str | int | None) -> str:
    """주문번호를 비교 가능한 표준 형태로 변환한다.

    KIS API 응답의 주문번호(ODNO/odno)는 앞자리 0이 포함된 고정 길이 문자열로 오는
    경우와 그렇지 않은 경우가 섞여 있을 수 있고, 정수로 전달되는 경우도 있다.
    앞뒤 공백과 앞자리 0을 제거한 뒤 문자열로 비교하면 이런 표현 차이로 인한
    매칭 실패를 방지할 수 있다.
    """
    if order_id is None:
        return ""
    normalized = str(order_id).strip().lstrip("0")
    return normalized or "0"
