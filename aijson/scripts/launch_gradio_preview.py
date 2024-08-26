import argparse
import asyncio
import contextlib
import json
import logging
import os
import sys
import time
import traceback
import uuid
from contextlib import contextmanager
from enum import Enum
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Collection, Any
from typing_extensions import assert_never
from unittest import mock

from aijson.models.config.action import ActionInvocation
from aijson.models.config.value_declarations import ValueDeclaration
from pydantic import BaseModel
from structlog.typing import EventDict

from aijson import Flow, ShelveCacheRepo
from aijson.log_config import get_logger, configure_logging
from aijson.models.config.flow import Loop
from aijson.repos.cache_repo import CacheRepo
from aijson.scripts.serve_openai import find_open_port, create_server
from aijson.utils.action_utils import get_actions_dict, import_custom_actions
from aijson.utils.async_utils import merge_iterators
from aijson.utils.format_utils import format_value
from aijson.utils.gradio_utils import single_shot
from aijson.utils.pydantic_utils import is_basemodel_subtype
from aijson.utils.rendering_utils import extract_root_var
from aijson.utils.sentinel_utils import is_sentinel
from aijson.utils.singleton_utils import TempEnvContext
from aijson.utils.static_utils import (
    get_config_variables,
    get_link_dependency_map,
)
from aijson.utils.subtype_utils import is_subtype
from aijson.utils.type_utils import remove_optional

os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"


from gradio.components import Component  # noqa: E402
from gradio.utils import SourceFileReloader, _remove_no_reload_codeblocks  # noqa: E402
import gradio as gr  # noqa: E402


resources_dir = os.path.join(os.path.dirname(__file__), "resources")


with open(os.path.join(resources_dir, "gradio.css")) as f:
    css = f.read()
with open(os.path.join(resources_dir, "gradio.js")) as f:
    js = f.read()


default_env_vars = [
    ("OPENAI_API_KEY", ""),
    ("ANTHROPIC_API_KEY", ""),
]


class ActionStatus(str, Enum):
    READY = "my-ready-action"
    PENDING = "my-pending-action"
    RUNNING = "my-running-action"
    SUCCEEDED = "my-succeeded-action"
    FAILED = "my-failed-action"


def _restore_value(name: str):
    # to persist `reload_module` calls
    if name in globals():
        return globals()[name]
    return None


def _construct_cache_repo():
    return ShelveCacheRepo(temp_dir=TemporaryDirectory().name)


_cache_repo: CacheRepo = _restore_value("_cache_repo") or _construct_cache_repo()

_task_cancelled: dict[str, bool] = _restore_value("_task_cancelled") or {}

_openai_server = _restore_value("_openai_server")

_serve_openai_task: asyncio.Task | None = _restore_value("_serve_openai_task")

_action_errors: dict[str, dict[str, str]] = _restore_value("_action_errors") or {}


def get_default_env_vars() -> tuple[str | None, list[tuple[str, str]]]:
    # load dotenv
    from dotenv import dotenv_values, find_dotenv

    dotenv_path = find_dotenv(usecwd=True)
    if not dotenv_path:
        return None, default_env_vars
    presented_vars = [
        (name, val or "") for name, val in dotenv_values(dotenv_path).items()
    ]
    for name, default_val in default_env_vars:
        if not any(t[0] == name for t in presented_vars):
            val = os.environ.get(name, default=default_val)
            presented_vars.append((name, val))
    return dotenv_path, presented_vars


def _construct_general_settings(log):
    # TODO allow use of redis for cache
    gr.Markdown(
        "All outputs are cached by default. If you'd like to generate new outputs for the same inputs:"
    )
    reset_cache = gr.Button("Clear cache")

    @reset_cache.click
    async def _():
        # TODO keep track of and cleanup temp dirs
        # old_temp_dir = _cache_repo.temp_dir
        _cache_repo.temp_dir = TemporaryDirectory().name
        gr.Info("Cache cleared")


def _construct_env_var_controls(
    log, dotenv_path: str | None, reload_state: gr.State, env_var_state: gr.State
):
    def update_env_var_state(*args):
        if len(args) // 2 != len(args) / 2:
            raise RuntimeError("Number of env var state update should be even")

        return [(k, v) for k, v in zip(args[::2], args[1::2])]

    if dotenv_path is not None:
        dotenv_message = f"Loaded from `{dotenv_path}`"
    else:
        dotenv_message = "If you put a `.env` file in the current directory, these will load automatically."
    gr.Markdown(dotenv_message)

    gr.Markdown(
        "**Note**: Due to [a gradio bug](https://github.com/gradio-app/gradio/issues/8855), "
        "environment variables reset upon reload."
    )

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
                    min_width=20,
                )
                fields.extend((key_field, value_field))
                with gr.Column(scale=0, min_width=16, elem_classes=["my-center-flex"]):
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
            remaining_fields = fields[0 : i * 2] + fields[i * 2 + 2 : len(fields)]
            button.click(update_env_var_state, remaining_fields, env_var_state).then(
                lambda i: i + 1, reload_state, reload_state
            )

    with gr.Row():
        add_button = gr.Button("+")
        add_button.click(lambda ts: ts + [("", "")], env_var_state, env_var_state).then(
            lambda i: i + 1, reload_state, reload_state
        )


def _construct_serve_openai_controls(
    log,
    flow: Flow,
    variable_textboxes: dict[str, gr.Textbox],
):
    async def serve(input_msg_var, *variable_values):
        global _serve_openai_task
        global _openai_server

        variable_values = {
            name: val for name, val in zip(variable_textboxes, variable_values)
        }
        if input_msg_var is not None:
            del variable_values[input_msg_var]

        flow_with_vars = flow.set_vars(**variable_values)

        if _openai_server is not None:
            _openai_server.should_exit = True
        if _serve_openai_task is not None:
            pass
            # canceling here prevents the shutdown triggered above
            # _serve_openai_task.cancel()

        host = "0.0.0.0"
        port = find_open_port()

        # TODO refactor this to dynamically creating a flow calling a subflow
        #  and running in a subprocess
        # TODO run it with the specified environment variables

        _openai_server = await create_server(
            flow_with_vars,
            input_var_name=input_msg_var,
            host=host,
            port=port,
        )
        _serve_openai_task = asyncio.create_task(_openai_server.serve())

        url = f"http://{host}:{port}"
        local_url = f"http://localhost:{port}"
        return f"**Status**: Serving on {url}. Use {local_url} to connect locally."

    gr.Markdown(
        "Serve an OpenAI-compatible Chat API:\n"
        "- using the variable values specified below\n"
        "- replacing the `Message Input` variable's value with the last message of the prompt\n"
        "- making outputs of the flow available as different models in the API\n\n"
        "You can also serve an OpenAI-compatible endpoint by running `python -m ai.scripts.serve_openai --flow path/to/flow`  \n"
        "**Note**: The API does not currently use the Environment Variables specified in the previous config pane. "
    )

    input_msg_dropdown = gr.Dropdown(
        choices=[None] + list(variable_textboxes),  # type: ignore
        value=list(variable_textboxes)[0] if variable_textboxes else None,
        label="Message Input",
    )
    serve_button = gr.Button("Serve")
    status_box = gr.Markdown("**Status**:")
    serve_button.click(
        serve,
        inputs=[
            input_msg_dropdown,
            *variable_textboxes.values(),
        ],
        outputs=status_box,
    )
    # TODO export config button, once subflows are in


def _get_output_component_for_type(
    type_: type | None,
    key: str,
):
    type_, _ = remove_optional(type_)

    if type_ is None or type_ is Any:
        component = gr.Text(
            show_label=False,
            key=key,
            container=False,
        )
    elif is_subtype(type_, str):
        component = gr.Markdown(
            show_label=False,
            key=key,
            line_breaks=True,
        )
    elif (
        is_subtype(type_, dict)
        or is_subtype(type_, list)
        or is_subtype(type_, BaseModel)
    ):
        component = gr.JSON(
            show_label=False,
            key=key,
        )
    else:
        component = gr.Text(
            show_label=False,
            key=key,
            container=False,
        )
    return component


def _build_output_component(
    action_output_components: dict[str, Component],
    run_buttons: dict[str, gr.Button],
    annotation: type | None,
    full_output_name: str,
):
    with gr.Row():
        component = _get_output_component_for_type(
            type_=annotation, key=full_output_name
        )
        action_output_components[full_output_name] = component
        with gr.Column(elem_classes=["my-compact-column"]):
            run_button = gr.Button(
                "▶️",
                # elem_classes=["my-square-column-button"],
            )
            run_buttons[full_output_name] = run_button
            # serve = gr.Button(
            #     "⬆️",
            #     # elem_classes=["my-square-column-button"],
            # )


def construct_gradio_app(log, variables: set[str], flow: Flow):
    actions_dict = get_actions_dict()
    dependency_map = get_link_dependency_map(flow.action_config)

    with gr.Blocks(analytics_enabled=False, css=css, js=js) as preview:
        dotenv_path, env_vars = get_default_env_vars()
        # TODO the env_var_state does not persist gradio reloads
        #  see https://github.com/gradio-app/gradio/issues/8855
        env_var_state = gr.State(env_vars)
        reload_state = gr.State(0)
        single_shot(lambda i: i + 1, reload_state, reload_state)

        # build variable inputs
        variable_textboxes = {
            variable_name: gr.Textbox(
                label=variable_name, interactive=True, key=variable_name, render=False
            )
            for variable_name in variables
        }

        # build options
        with gr.Accordion("Options", open=False):
            with gr.Tabs():
                with gr.Tab("General"):
                    _construct_general_settings(log)
                with gr.Tab("Environment Variables"):
                    _construct_env_var_controls(
                        log,
                        dotenv_path=dotenv_path,
                        reload_state=reload_state,
                        env_var_state=env_var_state,
                    )
                with gr.Tab("Serve OpenAI"):
                    _construct_serve_openai_controls(
                        log,
                        flow=flow,
                        variable_textboxes=variable_textboxes,
                    )

        # render variable inputs
        for box in variable_textboxes.values():
            box.render()

        submit_button = gr.Button("Run All", key="__submit_button")

        # build action outputs
        action_output_components = {}
        run_buttons = {}
        action_accordions = {}

        for action_id, action_invocation in flow.action_config.flow.items():
            # TODO handle loop
            if isinstance(action_invocation, Loop):
                continue
            elif isinstance(action_invocation, ValueDeclaration):
                # TODO is this right
                outputs_type = str
            elif isinstance(action_invocation, ActionInvocation):
                action = actions_dict[action_invocation.action]
                outputs_type = action._get_outputs_type(action_invocation)
            else:
                assert_never(action_invocation)
            with gr.Accordion(
                action_id,
                elem_classes=[
                    "my-status-indicator",
                    ActionStatus.READY.value,
                ],
            ) as action_accordion:
                if is_basemodel_subtype(outputs_type):
                    with gr.Tabs():
                        for (
                            output_name,
                            output_field,
                        ) in outputs_type.model_fields.items():
                            if output_field.deprecated:
                                continue
                            annotation = output_field.annotation
                            full_output_name = f"{action_id}.{output_name}"

                            with gr.Tab(output_name):
                                _build_output_component(
                                    action_output_components=action_output_components,
                                    run_buttons=run_buttons,
                                    annotation=annotation,
                                    full_output_name=full_output_name,
                                )
                else:
                    # TODO put this in a box somehow? gah why does markdown not support container
                    _build_output_component(
                        action_output_components=action_output_components,
                        run_buttons=run_buttons,
                        annotation=outputs_type,
                        full_output_name=action_id,
                    )
            action_accordions[action_id] = action_accordion

        def create_run_func(queued_action_ids: Collection[str]):
            async def _(env_var_tuples, *args):
                # TODO handle non-string inputs and outputs
                # Clear the output fields
                yield {
                    output_component: "{}"
                    if isinstance(output_component, gr.JSON)
                    else ""
                    for target_output, output_component in action_output_components.items()
                    if extract_root_var(target_output) in queued_action_ids
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

                task_id = str(uuid.uuid4())
                _task_cancelled[task_id] = False
                ready_flow.log = ready_flow.log.bind(trace_id=task_id)

                # set all objects as queued
                # build objects and async generators
                action_statuses = {}
                target_outputs_and_agens = []
                for output_target in action_output_components:
                    root_dependency = extract_root_var(output_target)
                    if root_dependency not in queued_action_ids:
                        continue
                    action_statuses[root_dependency] = ActionStatus.PENDING
                    target_outputs_and_agens.append(
                        (
                            output_target,
                            ready_flow.stream(output_target),
                        )
                    )

                # set action statuses (queued)
                yield {
                    action_accordions[action_id]: gr.Accordion(
                        elem_classes=["my-status-indicator", action_status.value],
                    )
                    for action_id, action_status in action_statuses.items()
                }

                # Prepare the environment variables
                env_var_dict = {k: v or None for k, v in env_var_tuples if k}
                context = TempEnvContext(env_var_dict)

                # Stream the variables
                merge = merge_iterators(
                    log,
                    *zip(*target_outputs_and_agens),
                    raise_=True,
                    report_finished=True,
                    suppress_exception_logging=True,
                )
                _action_errors[task_id] = {}
                try:
                    with context:
                        async for target_output, outputs in merge:
                            if _task_cancelled[task_id]:
                                del _task_cancelled[task_id]
                                return

                            action_id = extract_root_var(target_output)

                            # update action status
                            old_status = new_status = action_statuses[action_id]
                            if action_id in _action_errors[task_id]:
                                error_msg = _action_errors[task_id][action_id]
                                del _action_errors[task_id][action_id]
                                gr.Warning(error_msg)
                                new_status = ActionStatus.FAILED
                            elif (
                                is_sentinel(outputs)
                                and old_status != ActionStatus.FAILED
                            ):
                                if old_status == ActionStatus.PENDING:
                                    gr.Warning(f"{action_id} yielded no outputs")
                                    new_status = ActionStatus.FAILED
                                else:
                                    new_status = ActionStatus.SUCCEEDED
                            elif old_status == ActionStatus.PENDING:
                                new_status = ActionStatus.RUNNING
                            if old_status != new_status:
                                action_statuses[action_id] = new_status
                                yield {
                                    action_accordions[action_id]: gr.Accordion(
                                        elem_classes=[
                                            "my-status-indicator",
                                            action_statuses[action_id].value,
                                        ]
                                    )
                                }

                            if is_sentinel(outputs):
                                continue
                            output_component = action_output_components[target_output]
                            if not outputs and isinstance(output_component, gr.JSON):
                                formatted_value = "{}"
                            else:
                                formatted_value = format_value(outputs)
                            yield {output_component: formatted_value}
                finally:
                    del _action_errors[task_id]

            return _

        submit_button.click(
            create_run_func(flow.action_config.flow),
            inputs=[env_var_state] + list(variable_textboxes.values()),
            outputs=list(action_output_components.values())
            + list(action_accordions.values()),
        )
        for run_button_output, run_button in run_buttons.items():
            action_id = extract_root_var(run_button_output)
            relevant_action_ids = dependency_map[action_id] | {action_id}
            output_components = []
            for target_output, component in action_output_components.items():
                action_id = extract_root_var(target_output)
                if action_id not in relevant_action_ids:
                    continue
                output_components.append(component)
                output_components.append(action_accordions[action_id])
            run_button.click(
                create_run_func(relevant_action_ids),
                inputs=[env_var_state] + list(variable_textboxes.values()),
                outputs=output_components,
            )

    return preview


def create_flow_gradio_app(
    flow_path: str, cache_repo: CacheRepo | type[CacheRepo] = ShelveCacheRepo
):
    log = get_logger()

    flow = Flow.from_file(
        flow_path,
        cache_repo=cache_repo,
    )

    # TODO differentiate variables by type
    variables = get_config_variables(flow.action_config)

    return construct_gradio_app(log, variables, flow)


def watchfn(watch_file_path: str, reloader: SourceFileReloader):
    """Watch python files in a given module.

    get_changes is adapted from uvicorn's default file watcher.
    """

    if os.environ.get("PIPE_GRADIO_PORT"):
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

    watch_files = [Path(watch_file_path), Path(__file__)]

    def get_changes() -> Path | None:
        for file in watch_files:
            try:
                mtime = file.stat().st_mtime
            except OSError:  # pragma: nocover
                continue

            old_time = mtimes.get(file)
            if old_time is None:
                mtimes[file] = mtime
                continue
            elif mtime > old_time:
                return file
        return None

    mtimes: dict[Path, float] = {}
    # Need to import the module in this thread so that the
    # module is available in the namespace of this thread
    # (not actually cus it's the same module as this file – the exec and getattr are also commented out due to this)
    # module = importlib.import_module(reloader.watch_module_name)
    while reloader.should_watch():
        changed = get_changes()
        if changed:
            # print(f"Changes detected in: {changed}")
            try:
                # cancel running tasks
                for task_id in _task_cancelled:
                    _task_cancelled[task_id] = True

                # TODO watch action files and reload upon change

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
                mtimes = {}
                reloader.alert_change("error")
                reloader.app.reload_error_message = traceback.format_exc()
                continue
            # demo = getattr(module, reloader.demo_name)
            demo = globals()[reloader.demo_name]
            reloader.swap_blocks(demo)
            mtimes = {}
        time.sleep(0.05)


preview_module = "aijson.scripts.launch_gradio_preview"
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


def _show_action_exceptions_processor(
    logger: logging.Logger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    if "event" not in event_dict:
        return event_dict

    event = event_dict["event"]
    if event != "Action exception" and not event_dict["event"].startswith(
        "Failed to guess what language model to use"
    ):
        return event_dict

    if "trace_id" not in event_dict or "action_id" not in event_dict:
        return event_dict

    task_id = event_dict["trace_id"]
    action_id = event_dict["action_id"]

    if task_id not in _action_errors:
        return event_dict

    if event_dict.get("exc_info"):
        if isinstance(event_dict["exc_info"], BaseException):
            exc = event_dict["exc_info"]
        else:
            _, exc, _ = sys.exc_info()
            assert exc is not None
        _action_errors[task_id][action_id] = (
            f"{action_id} threw an exception: {repr(exc)}"
        )
    else:
        _action_errors[task_id][action_id] = event
    return event_dict


if gr.NO_RELOAD:
    # statically find and import actions recursively from current directory
    import_custom_actions(".")

    configure_logging(
        additional_processors=[_show_action_exceptions_processor],
    )


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
    flow_preview = create_flow_gradio_app(flow_path, cache_repo=_cache_repo)
    flow_preview.launch()
