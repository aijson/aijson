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
        '$': {
            'action2',
            'action5.result',
        },
        '$.action1.action3': {}
    }


def _get_literal_vals(literal_type: type[str]) -> list[str]:
    def handle_literal(literal: type[Literal]):
        return [literal.__args__[0]]

    def handle_annotated(annotated: type[Annotated]):
        return handle_literal(annotated.__args__[0])

    def handle_union(union: type[typing.Union]):
        joined = []
        for u in union.__args__:
            joined.extend(handle(u))
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
        config_filename=loops_filename,
        strict=True,
        include_paths=False
    )
    for path, expected in expected_elements.items():
        assert _get_literal_vals(hints[path]) == expected
    assert len(expected_elements) == len(hints)
