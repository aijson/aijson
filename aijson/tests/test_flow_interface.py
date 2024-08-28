from unittest.mock import patch

from aijson import Flow
from aijson.tests.test_action_service import assert_logs
from aijson.utils.loader_utils import load_config_file

from aijson_ml.actions.llm import (
    Outputs as PromptOutputs,
    Prompt,
    Inputs as PromptInputs,
)


async def test_default_model_var(log_history):
    config = load_config_file("aijson/tests/resources/default_model_var.ai.yaml")
    af = Flow(config=config).set_vars(
        some_model="hi",
    )

    outputs = PromptOutputs(
        result="3",
        response="3",
        data=None,
    )

    async def run(self, inputs: PromptInputs):
        assert inputs._default_model.model == "hi"
        yield outputs

    with patch.object(Prompt, "run", new=run):
        outputs = await af.run()

    assert outputs == "3"

    assert all(log_["log_level"] != "error" for log_ in log_history)

    # with capture_logs() as log_history:
    # outputs = await action_service.run_action(log=log, action_id=action_id)

    # assert_logs(log_history, action_id, "test_add")


async def test_run_all(log_history):
    config = load_config_file("aijson/tests/resources/run_all.ai.yaml")
    flow = Flow(config)
    expected_outputs = [3, 4, 5]
    outputs = await flow.run_all()

    assert len(outputs) == 3

    for output, expected in zip(outputs, expected_outputs):
        assert output.result == expected

    action_name = "test_add"
    assert_logs(log_history, "add_two", action_name, assert_empty=False)
    assert_logs(log_history, "add_three", action_name, assert_empty=False)
    assert_logs(log_history, "add_four", action_name)


async def test_stream_all(log_history):
    config = load_config_file("aijson/tests/resources/run_all.ai.yaml")
    flow = Flow(config)
    outputs = flow.stream_all()

    expected_outputs = {"add_two": 3, "add_three": 4, "add_four": 5}
    outputs = flow.stream_all()

    async for output in outputs:
        for action_name in output:
            expected_output = expected_outputs.get(action_name)
            assert output[action_name].result == expected_output
    action_name = "test_add"
    assert_logs(log_history, "add_two", action_name, assert_empty=False)
    assert_logs(log_history, "add_three", action_name, assert_empty=False)
    assert_logs(log_history, "add_four", action_name)
