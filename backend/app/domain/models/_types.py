from enum import Enum

from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls: type[Enum], name: str) -> SAEnum:
    """소문자 문자열 값(예: 'paper')을 사용하는 PostgreSQL ENUM 타입을 생성한다."""
    return SAEnum(enum_cls, name=name, values_callable=lambda enum_type: [e.value for e in enum_type])
