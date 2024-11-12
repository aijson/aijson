import os
from typing import Any, AsyncIterator
import pydantic

from aijson.flow import Flow
from aijson.log_config import get_logger
from aijson.models.config.action import (
    Action,
    ActionInvocation,
    ActionMeta,
    StreamingAction,
)
from aijson.models.config.flow import Executable
from aijson.models.config.value_declarations import ValueDeclaration
from aijson.models.primitives import ExecutableId
from aijson.utils.static_utils import get_config_variables
from pydantic import ConfigDict, create_model
from aijson.models.func import _prepare_kwargs

_processed_subflows = set()


def add_subflows():
    def check_dir(dir: str):
        for item in os.listdir(dir):
            full_path = os.path.join(dir, item)
            if os.path.isdir(full_path):
                check_dir(full_path)
            elif os.path.isfile(full_path):
                if full_path.endswith(".ai.json") or full_path.endswith(".ai.yaml"):
                    try:
                        if full_path in _processed_subflows:
                            continue
                        _processed_subflows.add(full_path)
                        flow = Flow.from_file(full_path)
                        if flow.action_config.name is not None:
                            _add_subflows(flow, full_path)
                    except pydantic.ValidationError:
                        continue

    return check_dir(".")


def _add_subflows(flow: Flow, path: str):
    if flow.action_config.name is None:
        return

    for action in flow.action_config.flow:
        _new_action(flow, action, path)
    _new_action(flow, None, path)


def _get_action_invocation(
    invocation: Executable, flow: Flow
) -> tuple[type[Action] | type[StreamingAction], type] | None:
    if isinstance(invocation, ActionInvocation):
        name = invocation.action
        action_type = ActionMeta.actions_registry.get(name)
        if action_type is None:
            return None
        outputs_type = action_type._get_outputs_type(None)
        _type = None
        if issubclass(action_type, Action):
            _type = Action
        elif issubclass(action_type, StreamingAction):
            _type = StreamingAction
        else:
            return None
        return (_type, outputs_type)
    elif isinstance(invocation, ValueDeclaration):
        dependencies = invocation.get_dependencies()
        if len(dependencies) >= 0:
            first = flow.action_config.flow.get(list(dependencies)[0])
            if first is None:
                return None
            return _get_action_invocation(first, flow)
    return None


def _new_action(flow: Flow, action_name: ExecutableId | None, path: str):
    if flow.action_config.name is None:
        return

    is_default_action = False
    if action_name is None:
        action_name = flow.action_config.get_default_output()
        is_default_action = True
    invocation = flow.action_config.flow.get(action_name)
    if invocation is None:
        return
    action_invocation = _get_action_invocation(invocation, flow)
    if action_invocation is None:
        return
    _type, outputs_type = action_invocation
    if _type is None:
        return

    dependencies = get_config_variables(flow.action_config)

    field_definitions = {}
    for dependency in dependencies:
        field_definitions[dependency] = (str, ...)

    InputsModel = create_model(
        f"{flow.action_config.name}.{action_name}",
        model_config=ConfigDict(
            arbitrary_types_allowed=True,
        ),
        # __base__ = inputs_type,
        **field_definitions,
    )
    if is_default_action:
        full_action_name = flow.action_config.name
    else:
        full_action_name = f"{flow.action_config.name}.{action_name}"

    if _type == StreamingAction:

        class streaming_action(StreamingAction[InputsModel, outputs_type]):
            name = full_action_name
            target = action_name
            subflow = flow
            subflow_source_file = path
            subflow_source_line = 0

            async def run(self, inputs) -> AsyncIterator[Any]:
                if self.subflow is not None:
                    args = _prepare_kwargs(inputs)
                    new_flow = self.subflow.set_vars(**args)
                    stream = new_flow.stream(self.target)
                    async for i in stream:
                        yield i

        streaming_action(get_logger(), "")
    elif _type == Action:

        class action(Action[InputsModel, outputs_type]):
            name = full_action_name
            target = action_name
            subflow = flow
            subflow_source_file = path
            subflow_source_line = 0

            async def run(self, inputs):
                if self.subflow is not None:
                    args = _prepare_kwargs(inputs)
                    new_flow = self.subflow.set_vars(**args)
                    return await new_flow.run(self.target)

        action(get_logger(), "")
