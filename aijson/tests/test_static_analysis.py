import os

import pytest

from aijson.utils.loader_utils import load_config_file
from aijson.utils.static_utils import (
    check_config_consistency,
    get_config_variables,
    get_variable_dependency_map,
    get_link_dependency_map,
)


@pytest.mark.parametrize(
    "actions_path, variables, expected",
    [
        (
            "testing_actions.ai.yaml",
            set(),
            True,
        ),
        ("default_model_var.ai.yaml", set(), False),
        ("default_model_var.ai.yaml", {"some_model"}, True),
    ],
)
def test_static_analysis(
    log, testing_actions_type, actions_path, variables, expected
) -> None:
    full_actions_path = os.path.join("aijson", "tests", "resources", actions_path)
    config = load_config_file(full_actions_path, config_model=testing_actions_type)
    assert (
        check_config_consistency(log, config, variables, config.get_default_output())
        is expected
    )


@pytest.mark.parametrize(
    "path, expected_variables",
    (
        (
            "examples/debono.ai.yaml",
            {"query"},
        ),
        (
            "examples/chatbot.ai.yaml",
            {"pdf_filepaths", "message", "conversation_history"},
        ),
    ),
)
def test_get_config_variables(path, expected_variables):
    config = load_config_file(path)
    assert get_config_variables(config) == expected_variables


@pytest.mark.parametrize(
    "path, expected_map",
    (
        (
            "examples/hello_world.ai.yaml",
            {"hello_world": set()},
        ),
        (
            "examples/chatbot.ai.yaml",
            {
                "chatbot": {"pdf_filepaths", "conversation_history", "message"},
                "extract_chatbot": {"pdf_filepaths", "conversation_history", "message"},
                "extract_pdf_texts": {"pdf_filepaths"},
                "extract_query": {"message"},
                "generate_query": {"message"},
                "reranking": {"pdf_filepaths", "message"},
                "retrieval": {"pdf_filepaths", "message"},
            },
        ),
    ),
)
def test_get_variable_dependency_map(path, expected_map):
    config = load_config_file(path)
    assert get_variable_dependency_map(config) == expected_map


@pytest.mark.parametrize(
    "path, expected_map",
    (
        (
            "examples/hello_world.ai.yaml",
            {"hello_world": set()},
        ),
        (
            "examples/chatbot.ai.yaml",
            {
                "chatbot": {
                    "extract_pdf_texts",
                    "extract_query",
                    "generate_query",
                    "reranking",
                    "retrieval",
                },
                "extract_chatbot": {
                    "chatbot",
                    "extract_pdf_texts",
                    "extract_query",
                    "generate_query",
                    "reranking",
                    "retrieval",
                },
                "extract_pdf_texts": set(),
                "extract_query": {"generate_query"},
                "generate_query": set(),
                "reranking": {
                    "extract_pdf_texts",
                    "extract_query",
                    "generate_query",
                    "retrieval",
                },
                "retrieval": {"extract_pdf_texts", "extract_query", "generate_query"},
            },
        ),
    ),
)
def test_get_link_dependency_map(path, expected_map):
    config = load_config_file(path)
    assert get_link_dependency_map(config) == expected_map
