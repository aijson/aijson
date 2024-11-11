from unittest.mock import patch

from aijson_ml.actions.llm import Inputs, Prompt
from aijson import Flow
from aijson.tests.resources.testing_actions import AddOutputs, RangeStreamOutput
from aijson.utils.action_utils import get_actions_dict


async def test_basic_subflow(assert_no_errors):
    flow = Flow.from_file("aijson/tests/resources/use_basic_subflow.ai.yaml")
    expected_output = AddOutputs(result=3)
    output = await flow.run()
    assert output == expected_output


async def test_subflow_result(assert_no_errors):
    flow = Flow.from_file("aijson/tests/resources/use_subflow_result.ai.yaml")
    expected_output = 3
    output = await flow.run()
    assert output == expected_output


async def test_prompt_subflow(assert_no_errors):
    flow = Flow.from_file("aijson/tests/resources/use_prompt_subflow.ai.yaml")

    outputs = "Hello! How can I assist you today?"

    async def run(self, inputs: Inputs):
        assert inputs._default_model.model == "hi"
        yield outputs

    with patch.object(Prompt, "run", new=run):
        outputs = await flow.run()


async def test_calling_subflow_in_subflow(assert_no_errors):
    flow = Flow.from_file(
        "aijson/tests/resources/subflows/call_subflow_in_subflow.ai.yaml"
    )
    expected_output = AddOutputs(result=3)
    output = await flow.run()
    assert output == expected_output


async def test_subflow_name(assert_no_errors):
    flow = Flow.from_file("aijson/tests/resources/subflows/subflow_result.ai.yaml")
    assert flow.action_config.name == "subflow_with_result"


async def test_streaming_subflow(assert_no_errors):
    flow = Flow.from_file("aijson/tests/resources/use_streaming_subflow.ai.yaml")
    expected_outputs = [RangeStreamOutput(value=output) for output in range(10)]
    outputs = []
    async for output in flow.stream():
        outputs.append(output)
    assert outputs == expected_outputs


async def test_available_subflows(assert_no_errors):
    actions = get_actions_dict()
    subflows = ["basic", "hello_flow", "subflow_with_result"]
    for subflow_name in subflows:
        subflow = actions.get(subflow_name)
        assert subflow is not None
