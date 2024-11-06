from unittest.mock import patch

from aijson_ml.actions.llm import Inputs, Prompt
from aijson import Flow
from aijson.tests.resources.testing_actions import AddOutputs
from aijson.utils.loader_utils import load_config_file


async def test_basic_subflow(assert_no_errors):
    config = load_config_file("aijson/tests/resources/use_basic_subflow.ai.yaml")
    flow = Flow(config)
    expectedOutput = AddOutputs(result=3)
    output = await flow.run()
    assert output == expectedOutput


async def test_subflow_result(assert_no_errors):
    config = load_config_file("aijson/tests/resources/use_subflow_result.ai.yaml")
    flow = Flow(config)
    expectedOutput = 3
    output = await flow.run()
    assert output == expectedOutput


async def test_prompt_subflow(assert_no_errors):
    config = load_config_file("aijson/tests/resources/use_prompt_subflow.ai.yaml")
    flow = Flow(config)

    outputs = "Hello! How can I assist you today?"

    async def run(self, inputs: Inputs):
        assert inputs._default_model.model == "hi"
        yield outputs

    with patch.object(Prompt, "run", new=run):
        outputs = await flow.run()
