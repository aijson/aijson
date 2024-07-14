import os

import pytest

from asyncflows.utils.loader_utils import load_config_file
from asyncflows.utils.static_utils import (
    check_config_consistency,
    get_config_variables,
)


@pytest.mark.parametrize(
    "actions_path, variables, expected",
    [
        (
            "testing_actions.yaml",
            set(),
            True,
        ),
        ("default_model_var.yaml", set(), False),
        ("default_model_var.yaml", {"some_model"}, True),
    ],
)
def test_static_analysis(
    log, testing_actions_type, actions_path, variables, expected
) -> None:
    full_actions_path = os.path.join("asyncflows", "tests", "resources", actions_path)
    config = load_config_file(full_actions_path, config_model=testing_actions_type)
    assert (
        check_config_consistency(log, config, variables, config.get_default_output())
        is expected
    )


@pytest.mark.parametrize(
    "path, expected_variables",
    (
        (
            "asyncflows/examples/debono.yaml",
            {"query"},
        ),
        (
            "asyncflows/examples/chatbot.yaml",
            {"pdf_filepaths", "message", "conversation_history"},
        ),
    ),
)
def test_get_config_variables(path, expected_variables):
    config = load_config_file(path)
    assert get_config_variables(config) == expected_variables
