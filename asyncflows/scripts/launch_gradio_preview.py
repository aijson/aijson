import argparse
import contextlib
import json
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
from asyncflows.utils.format_utils import format_value
from asyncflows.utils.gradio_utils import single_shot
from asyncflows.utils.pydantic_utils import is_basemodel_subtype
from asyncflows.utils.singleton_utils import TempEnvContext
from asyncflows.utils.static_utils import get_config_variables

os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"


from gradio.utils import SourceFileReloader, _remove_no_reload_codeblocks  # noqa: E402
import gradio as gr  # noqa: E402


css = """
footer {visibility: hidden}

.my-center-flex {
  gap: 0px;
  justify-content: center;
}

.my-square-button {
  height: 100%;
}

.my-centered-container {
  align-items: center;
}

.my-centered-text {
  text-align: center;
}
"""

js = """
function main() {
    const onInputKeyDown = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.code === "KeyC") {
        document.execCommand("copy");
      } else if ((event.ctrlKey || event.metaKey) && event.code === "KeyX") {
        document.execCommand("cut");
      } else if ((event.ctrlKey || event.metaKey) && event.code === "KeyV") {
        document.execCommand("paste");
      } else if ((event.ctrlKey || event.metaKey) && event.code === "KeyA") {
        document.execCommand("selectAll");
      }
    }
      window.addEventListener('keydown', (e) => {
        onInputKeyDown(e);
      })

    return "";
}
"""

default_env_vars = [
    ("OPENAI_API_KEY", ""),
    ("ANTHROPIC_API_KEY", ""),
]


def get_default_env_vars() -> tuple[str | None, list[tuple[str, str]]]:
    # load dotenv
    from dotenv import dotenv_values, find_dotenv

    dotenv_path = find_dotenv()
    if not dotenv_path:
        return None, default_env_vars
    return dotenv_path, [(name, val or "") for name, val in dotenv_values().items()]


def construct_gradio_app(log, variables: set[str], flow: AsyncFlows):
    actions_dict = get_actions_dict()

    with gr.Blocks(analytics_enabled=False, css=css, js=js) as preview:
        dotenv_path, env_vars = get_default_env_vars()
        # TODO the env_var_state does not persist gradio reloads
        #  see https://github.com/gradio-app/gradio/issues/8855
        env_var_state = gr.State(env_vars)
        reload_state = gr.State(0)
        single_shot(lambda i: i + 1, reload_state, reload_state)

        def update_env_var_state(*args):
            if len(args) // 2 != len(args) / 2:
                raise RuntimeError("Number of env var state update should be even")

            return [(k, v) for k, v in zip(args[::2], args[1::2])]

        # build env var accordion
        env_var_label = "Environment Variables"
        if dotenv_path is not None:
            env_var_label += f" (loaded from `{dotenv_path}`)"
        with gr.Accordion(env_var_label, open=False):

            @gr.render(inputs=env_var_state, triggers=[reload_state.change])
            def render_env_vars(env_var_tuples):
                fields = []
                delete_buttons = []
                for i, (k, v) in enumerate(env_var_tuples):
                    with gr.Row(elem_classes=["my-centered-container"]):
                        key_field = gr.Textbox(
                            k,
                            # label="Key",
                            show_label=False,
                            scale=1,
                            min_width=200,
                        )
                        value_field = gr.Textbox(
                            v,
                            # label="Value",
                            type="password",
                            show_label=False,
                            scale=3,
                        )
                        fields.extend((key_field, value_field))
                        with gr.Column(
                            scale=0, min_width=16, elem_classes=["my-center-flex"]
                        ):
                            gr.Markdown(
                                "👁️",
                                elem_classes=["my-centered-text"],
                            )
                            cb = gr.Checkbox(
                                False,
                                show_label=False,
                                container=False,
                                label="",
                                scale=0,
                                min_width=1,
                            )
                            cb.change(
                                lambda t: gr.Textbox(type="text" if t else "password"),
                                cb,
                                value_field,
                            )
                        delete_button = gr.Button(
                            "-",
                            scale=0,
                            min_width=20,
                            elem_classes=["my-square-button"],
                        )
                        delete_buttons.append(delete_button)
                for field in fields:
                    field.change(update_env_var_state, fields, env_var_state)
                for i, button in enumerate(delete_buttons):
                    remaining_fields = (
                        fields[0 : i * 2] + fields[i * 2 + 2 : len(fields)]
                    )
                    button.click(
                        update_env_var_state, remaining_fields, env_var_state
                    ).then(lambda i: i + 1, reload_state, reload_state)

            with gr.Row():
                add_button = gr.Button("+")
                add_button.click(
                    lambda ts: ts + [("", "")], env_var_state, env_var_state
                ).then(lambda i: i + 1, reload_state, reload_state)

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
                            if is_basemodel_subtype(output_field.annotation):
                                component = gr.JSON(
                                    show_label=False,
                                    key=full_output_name,
                                )
                            else:
                                component = gr.Markdown(
                                    show_label=False,
                                    key=full_output_name,
                                    line_breaks=True,
                                )
                            action_output_components[full_output_name] = component

        async def handle_submit(env_var_tuples, *args):
            # TODO handle non-string inputs and outputs
            # Clear the output fields
            yield {
                output_component: "{}" if isinstance(output_component, gr.JSON) else ""
                for output_component in action_output_components.values()
            }

            # Set the variables
            kwargs = {}
            for variable_name, arg in zip(variables, args):
                try:
                    val = json.loads(arg)
                except json.JSONDecodeError:
                    val = arg
                kwargs[variable_name] = val
            ready_flow = flow.set_vars(**kwargs)

            target_outputs_and_agens = []
            for output_target in action_output_components:
                target_outputs_and_agens.append(
                    (
                        output_target,
                        ready_flow.stream(output_target),
                    )
                )

            # Prepare the environment variables
            env_var_dict = {k: v for k, v in env_var_tuples if k and v}
            context = TempEnvContext(env_var_dict)

            # Stream the variables
            merge = merge_iterators(
                log,
                *zip(*target_outputs_and_agens),
                raise_=True,
            )
            with context:
                async for target_output, outputs in merge:
                    output_component = action_output_components[target_output]
                    if not outputs and isinstance(output_component, gr.JSON):
                        formatted_value = "{}"
                    else:
                        formatted_value = format_value(outputs)
                    yield {output_component: formatted_value}

        submit_button.click(
            handle_submit,
            inputs=[env_var_state] + list(variable_textboxes.values()),
            outputs=list(action_output_components.values()),
        )

    return preview


def create_flow_gradio_app(flow_path: str):
    log = get_logger()

    flow = AsyncFlows.from_file(flow_path)

    # TODO differentiate variables by type
    variables = get_config_variables(flow.action_config)

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
    try:
        with mock.patch("gradio.utils.watchfn", partial(watchfn, watch_filepath)):
            yield
    finally:
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
