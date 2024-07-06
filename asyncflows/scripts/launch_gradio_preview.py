import argparse
import os

from asyncflows import AsyncFlows
from asyncflows.log_config import get_logger
from asyncflows.models.config.flow import Loop
from asyncflows.utils.action_utils import get_actions_dict
from asyncflows.utils.async_utils import merge_iterators
from asyncflows.utils.static_utils import get_flow_variables

os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"


import gradio as gr  # noqa: E402


css = """
footer {visibility: hidden}
"""


def construct_gradio_app(log, variables: set[str], flow: AsyncFlows):
    actions_dict = get_actions_dict()

    with gr.Blocks(analytics_enabled=False, css=css) as preview:
        # build variable inputs
        variable_textboxes = {
            variable_name: gr.Textbox(label=variable_name, interactive=True)
            for variable_name in variables
        }

        submit_button = gr.Button("Submit")

        # build action outputs
        action_output_components = {}
        for action_id, action_invocation in flow.action_config.flow.items():
            # TODO handle loop
            if isinstance(action_invocation, Loop):
                continue
            action = actions_dict[action_invocation.action]
            outputs_type = action._get_outputs_type(action_invocation)
            with gr.Accordion(action_id):
                with gr.Tabs():
                    for output_name, output_field in outputs_type.model_fields.items():
                        if output_field.deprecated:
                            continue
                        full_output_name = f"{action_id}.{output_name}"
                        with gr.Tab(output_name):
                            action_output_components[full_output_name] = gr.Markdown(
                                show_label=False,
                            )

        async def handle_submit(*args):
            # TODO handle non-string inputs and outputs
            # Clear the output fields
            yield {
                action_output_textbox: ""
                for action_output_textbox in action_output_components.values()
            }

            # Set the variables
            kwargs = {variable_name: arg for variable_name, arg in zip(variables, args)}
            ready_flow = flow.set_vars(**kwargs)

            objects_and_coros = []
            for (
                output_target,
                action_output_textbox,
            ) in action_output_components.items():
                objects_and_coros.append(
                    (
                        action_output_textbox,
                        ready_flow.stream(output_target),
                    )
                )

            # Stream the variables
            async for output_textbox, outputs in merge_iterators(
                log,
                *zip(*objects_and_coros),
            ):
                yield {output_textbox: outputs}

        submit_button.click(
            handle_submit,
            inputs=list(variable_textboxes.values()),
            outputs=list(action_output_components.values()),
        )

    return preview


def create_flow_gradio_app(flow_path: str):
    log = get_logger()

    flow = AsyncFlows.from_file(flow_path)

    # TODO differentiate variables by type
    variables = get_flow_variables(flow.action_config)

    return construct_gradio_app(log, variables, flow)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--flow",
        help="Path to flow for populating link fields with",
        required=True,
    )

    args = parser.parse_args()
    flow_path = args.flow

    demo = create_flow_gradio_app(flow_path)
    demo.launch()
