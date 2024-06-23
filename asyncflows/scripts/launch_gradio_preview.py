import argparse
import os


import gradio as gr

from asyncflows import AsyncFlows
from asyncflows.log_config import get_logger
from asyncflows.utils.async_utils import merge_iterators
from asyncflows.utils.static_utils import get_flow_variables

os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"


def construct_gradio_app(log, variables: set[str], flow: AsyncFlows):
    with gr.Blocks(analytics_enabled=False) as preview:
        variable_textboxes = {
            variable_name: gr.Textbox(label=variable_name, interactive=True)
            for variable_name in variables
        }

        submit_button = gr.Button("Submit")

        action_output_textboxes = {
            action_id: gr.Textbox(label=action_id, interactive=False)
            for action_id in flow.action_config.flow
        }

        async def handle_submit(*args):
            # TODO handle non-string inputs and outputs
            # Clear the output fields
            yield {
                action_output_textbox: ""
                for action_output_textbox in action_output_textboxes.values()
            }

            # Set the variables
            kwargs = {variable_name: arg for variable_name, arg in zip(variables, args)}
            ready_flow = flow.set_vars(**kwargs)

            # Stream the variables
            async for output_textbox, outputs in merge_iterators(
                log,
                *zip(
                    *[
                        (
                            action_output_textbox,
                            ready_flow.stream(f"{action_id}.result"),
                        )  # TODO this is hardcoded
                        for action_id, action_output_textbox in action_output_textboxes.items()
                    ]
                ),
            ):
                yield {output_textbox: outputs}

        submit_button.click(
            handle_submit,
            inputs=list(variable_textboxes.values()),
            outputs=list(action_output_textboxes.values()),
        )

    return preview


def serve_flow_gradio_app(flow_path: str):
    log = get_logger()

    flow = AsyncFlows.from_file(flow_path)

    # TODO differentiate variables by type
    variables = get_flow_variables(flow.action_config)

    preview = construct_gradio_app(log, variables, flow)

    preview.launch()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--flow",
        help="Path to flow for populating link fields with",
        required=True,
    )

    args = parser.parse_args()
    flow_path = args.flow

    serve_flow_gradio_app(flow_path)
