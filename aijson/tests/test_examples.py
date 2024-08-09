import builtins
import os


import pytest

from aijson import Flow
from aijson.utils.loader_utils import load_config_file
from aijson.utils.static_utils import check_config_consistency

examples_dir = "examples"


@pytest.fixture(scope="function")
def mock_builtins_input(monkeypatch):
    responded = False

    def input_mock(*args, **kwargs):
        nonlocal responded

        if responded:
            # simulate CTRL+D
            raise EOFError
        responded = True
        return "Hi"

    monkeypatch.setattr(builtins, "input", input_mock)


@pytest.fixture
def mock_database_url_env_var():
    database_url_bak = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    yield
    if database_url_bak is not None:
        os.environ["DATABASE_URL"] = database_url_bak
    else:
        del os.environ["DATABASE_URL"]


def get_example_names():
    example_names = []
    for example in os.listdir(examples_dir):
        if example.endswith(".ai.yaml"):
            example_names.append(example[:-8])
    return example_names


# @pytest.mark.skipif(
#     "ANTHROPIC_API_KEY" not in os.environ, reason="requires ANTROPIC_API_KEY env var"
# )
@pytest.mark.parametrize(
    "example_name",
    get_example_names(),
)
async def test_run_example(
    mock_prompt_action,
    mock_transformer_action,
    mock_builtins_input,
    mock_sqlite_engine,
    mock_async_sqlite_engine,
    mock_database_url_env_var,
    example_name,
    log_history,
):
    example_stem = os.path.join(examples_dir, example_name)
    example_yaml = f"{example_stem}.ai.yaml"

    # if example files don't exist
    if not os.path.exists(example_yaml):
        raise FileNotFoundError(f"Example not found: {example_yaml}")

    flow = Flow.from_file(example_yaml)
    if example_name in example_vars:
        vars_ = example_vars[example_name]
        flow = flow.set_vars(**vars_)

    await flow.run()

    assert not any(log_line["log_level"] == "error" for log_line in log_history)


example_vars = {
    "application_judgement": {
        "application": "foo",
        "application_criteria": "bar",
    },
    "chatbot": {
        "pdf_filepaths": [
            "examples/books/Alice's Adventures in Wonderland, by Lewis Carroll.pdf"
        ],
        "message": "foo",
        "conversation_history": "bar",
    },
    "debono": {
        "query": "foo",
    },
    "get_page_title": {
        "url": "foo",
    },
    "rag": {
        "texts": ["foo"],
        "question": "bar",
    },
    "sql_rag": {
        "query": "foo",
    },
    "text_style_transfer": {
        "writing_sample": "foo",
        "topic": "bar",
    },
    "meeting_review": {
        "meeting_notes": "foo",
    },
    "simple_list": {
        "thing": "foo",
    },
}


@pytest.mark.parametrize(
    "example_name",
    get_example_names(),
)
async def test_examples_statically(log, example_name):
    example_stem = os.path.join(examples_dir, example_name)
    example_yaml = f"{example_stem}.ai.yaml"

    vars_ = example_vars.get(example_name, set())

    # if example files don't exist
    if not os.path.exists(example_yaml):
        raise FileNotFoundError(f"Example not found: {example_yaml}")

    config = load_config_file(example_yaml)
    assert check_config_consistency(
        log, config, set(vars_), config.get_default_output()
    )
