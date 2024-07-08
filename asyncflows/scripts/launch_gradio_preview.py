import argparse
import contextlib
import os
import time
import traceback
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from unittest import mock

from asyncflows import AsyncFlows
from asyncflows.log_config import get_logger
from asyncflows.models.config.flow import Loop
from asyncflows.utils.action_utils import get_actions_dict
from asyncflows.utils.async_utils import merge_iterators
from asyncflows.utils.static_utils import get_flow_variables

os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"


from gradio.utils import SourceFileReloader, _remove_no_reload_codeblocks  # noqa: E402
import gradio as gr  # noqa: E402


css = """
footer {visibility: hidden}
"""


def construct_gradio_app(log, variables: set[str], flow: AsyncFlows):
    actions_dict = get_actions_dict()

    with gr.Blocks(analytics_enabled=False, css=css) as preview:
        # build variable inputs
        variable_textboxes = {
            variable_name: gr.Textbox(
                label=variable_name, interactive=True, key=variable_name
            )
            for variable_name in variables
        }

        submit_button = gr.Button("Submit", key="__submit_button")

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
                                show_label=False, key=full_output_name
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

            objects_and_agens = []
            for (
                output_target,
                action_output_textbox,
            ) in action_output_components.items():
                objects_and_agens.append(
                    (
                        action_output_textbox,
                        ready_flow.stream(output_target),
                    )
                )

            # Stream the variables
            merge = merge_iterators(
                log,
                *zip(*objects_and_agens),
                raise_=True,
            )
            async for output_textbox, outputs in merge:
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


def watchfn(watch_file_path: str, reloader: SourceFileReloader):
    """Watch python files in a given module.

    get_changes is adapted from uvicorn's default file watcher.
    """

    # print the port the server is running on to pipe 3
    # wait for port to be assigned
    while not hasattr(flow_preview, "server_port"):
        time.sleep(0.05)
    with os.fdopen(3, "w") as fd:
        fd.write(str(flow_preview.server_port))

    # The thread running watchfn will be the thread reloading
    # the app. So we need to modify this thread_data attr here
    # so that subsequent calls to reload don't launch the app
    from gradio.cli.commands.reload import reload_thread

    reload_thread.running_reload = True

    def get_changes() -> Path | None:
        nonlocal last_mtime

        file = Path(watch_file_path)

        try:
            mtime = file.stat().st_mtime
        except OSError:  # pragma: nocover
            return None

        if last_mtime is None:
            last_mtime = mtime
            return None
        elif mtime > last_mtime:
            return file
        return None

    last_mtime: float | None = None
    # Need to import the module in this thread so that the
    # module is available in the namespace of this thread
    # (not actually cus it's the same module as this file – the exec and getattr are also commented out due to this)
    # module = importlib.import_module(reloader.watch_module_name)
    while reloader.should_watch():
        changed = get_changes()
        if changed:
            # print(f"Changes detected in: {changed}")
            try:
                changed_demo_file = _remove_no_reload_codeblocks(
                    str(reloader.demo_file)
                )

                # exec(changed_demo_file, module.__dict__)
                exec(changed_demo_file, globals())
            except Exception:
                # TODO use error logger
                print(
                    f"Reloading {reloader.watch_module_name} failed with the following exception: "
                )
                traceback.print_exc()
                last_mtime = None
                reloader.alert_change("error")
                reloader.app.reload_error_message = traceback.format_exc()
                continue
            # demo = getattr(module, reloader.demo_name)
            demo = globals()[reloader.demo_name]
            reloader.swap_blocks(demo)
            last_mtime = None
        time.sleep(0.05)


preview_module = "asyncflows.scripts.launch_gradio_preview"
preview_module_path = __file__
env_baks = {}


@contextmanager
def patch_gradio(watch_filepath: str):
    env_overrides = {
        "GRADIO_WATCH_MODULE_NAME": preview_module,
        "GRADIO_WATCH_DEMO_NAME": "flow_preview",
        "GRADIO_WATCH_DEMO_PATH": preview_module_path,
        "GRADIO_WATCH_DIRS": "1",
    }

    for env_var, val in env_overrides.items():
        env_baks[env_var] = os.environ.get(env_var)
        os.environ[env_var] = val

    with mock.patch("gradio.utils.watchfn", partial(watchfn, watch_filepath)):
        yield

    for env_var, val in env_baks.items():
        if val is None:
            del os.environ[env_var]
        else:
            os.environ["env_var"] = val


parser = argparse.ArgumentParser()
parser.add_argument(
    "--flow",
    help="Path to flow for populating link fields with",
    required=True,
)

args, _ = parser.parse_known_args()
flow_path = args.flow

context = contextlib.nullcontext()
if gr.NO_RELOAD:
    context = patch_gradio(flow_path)

with context:
    flow_preview = create_flow_gradio_app(flow_path)
    flow_preview.launch()
