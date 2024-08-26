from unittest.mock import patch

from aijson import Flow
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


async def test_run_all():
    # import logging
    # from aijson.log_config import configure_logging
    # from dotenv import load_dotenv

    # load_dotenv()
    # configure_logging(pretty=False, level=logging.INFO)

    config = load_config_file("aijson/tests/resources/run_all.ai.yaml")
    question = "1 + "
    flow = Flow(config).set_vars(question=question)

    expected_outputs = ["3", "4", "5"]
    outputs = await flow.run_all()
    for index, output in enumerate(outputs):
        try:
            expected = expected_outputs[index]
            assert expected in output
        except IndexError:
            assert False
