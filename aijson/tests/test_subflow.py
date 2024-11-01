from aijson import Flow
from aijson.tests.resources.testing_actions import AddOutputs
from aijson.utils.loader_utils import load_config_file


async def test_basic_subflow(log_history):
    config = load_config_file("aijson/tests/resources/use_basic_subflow.ai.yaml")
    flow = Flow(config)
    expectedOutput = AddOutputs(result=3)
    output = await flow.run()
    assert all(log_["log_level"] != "error" for log_ in log_history)
    assert output == expectedOutput
