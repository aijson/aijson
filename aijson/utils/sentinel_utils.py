import enum
from typing import Any, Literal

from typing_extensions import TypeIs


class SentinelEnum(enum.Enum):
    Sentinel = enum.auto()


SentinelType = Literal[SentinelEnum.Sentinel]
Sentinel = SentinelEnum.Sentinel


def is_sentinel(value: Any) -> TypeIs[SentinelType]:
    return value is Sentinel


def is_set_of_tuples(value: Any) -> TypeIs[set[tuple]]:
    """Custom type guard to check if the value is a set of tuples."""
    if not isinstance(value, set):
        return False
    for item in value:
        if not isinstance(item, tuple):
            return False
    return True
