from typing import Any

from typing_extensions import TypeIs

from aijson.utils.subtype_utils import is_subtype


class Sentinel:
    pass


def is_sentinel(value: Any) -> TypeIs[type[Sentinel]]:
    return is_subtype(value, Sentinel)


def is_set_of_tuples(value: Any) -> TypeIs[set[tuple]]:
    """Custom type guard to check if the value is a set of tuples."""
    if not isinstance(value, set):
        return False
    for item in value:
        if not isinstance(item, tuple):
            return False
    return True
