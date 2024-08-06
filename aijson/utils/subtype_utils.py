import inspect
from typing import Any, TypeVar, TypeGuard

T = TypeVar("T", bound=type)


def is_subtype(value: Any, type_: T) -> TypeGuard[T]:
    try:
        return inspect.isclass(value) and issubclass(value, type_)
    except Exception:
        # python 3.10 somehow triggers `issubclass() arg 1 must be a class`
        #  when the value is `list[str]`
        #  (interestingly enough this doesn't trigger if class to check against isn't BaseModel)
        return False
