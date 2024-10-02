import os
import types
import typing
from typing import Literal, Annotated, Any

import pytest
from aijson.utils.hint_utils import build_link_hints


@pytest.fixture
def loops_filename():
    return os.path.join(
        os.path.dirname(__file__),
        "resources",
        "loops.ai.yaml",
    )


@pytest.fixture
def expected_elements():
    return {
        "$": {
            # "action1",
            "action2",
            "action5.result",
        },
        "$.action1.flow": {
            "action1",
            "action2.result",
            "action5.result",
            # "action3",
        },
        "$.action1.flow.action3.flow": {
            "action1",
            "action2.string",
            "action5.result",
            "action3.result",
            "action9.result",
            "action4.result",
        },
    }


def _get_literal_vals(literal_type: type[str]) -> set[str]:
    def handle_literal(literal: type[Literal]):  # pyright: ignore[reportInvalidTypeForm]
        return {literal.__args__[0]}  # pyright: ignore[reportAttributeAccessIssue]

    def handle_annotated(annotated: type[Annotated]):
        return handle_literal(annotated.__args__[0])

    def handle_union(union: type[typing.Union]):  # pyright: ignore[reportInvalidTypeForm]
        joined = set()
        for u in union.__args__:  # pyright: ignore[reportGeneralTypeIssues]
            joined |= handle(u)
        return joined

    def handle(t: Any):
        origin = typing.get_origin(t)
        if origin is Literal:
            return handle_literal(t)
        elif origin is Annotated:
            return handle_annotated(t)
        elif origin in [typing.Union, types.UnionType]:
            return handle_union(t)
        else:
            raise RuntimeError(f"Unexpected type: {literal_type}")

    return handle(literal_type)


def test_build_link_hints(loops_filename, expected_elements):
    hints = build_link_hints(
        config_filename=loops_filename, strict=True, include_paths=False
    )
    for path, expected in expected_elements.items():
        literal_vals = _get_literal_vals(hints[path])
        assert literal_vals == expected
    assert len(expected_elements) == len(hints)
