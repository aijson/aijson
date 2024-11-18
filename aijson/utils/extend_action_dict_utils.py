import os
from typing import Any, AsyncIterator
import pydantic
import copy

from aijson.flow import Flow
from aijson.log_config import get_logger
from aijson.models.config.action import (
    Action,
    ActionInvocation,
    ActionMeta,
    StreamingAction,
)
from aijson.models.config.flow import Executable, FlowConfig
from aijson.models.config.value_declarations import LinkDeclaration, ValueDeclaration
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
                            _add_subflows(
                                flow,
                                full_path,
                                flow.action_config.name,
                            )
                    except pydantic.ValidationError:
                        continue

    return check_dir(".")


def _add_subflows(flow: Flow, path: str, subflow_name: str):
    for action in flow.action_config.flow:
        _new_action(flow, action, path, subflow_name)
    _new_action(flow, None, path, subflow_name)


def _get_action_invocation(
    invocation: Executable, flow: Flow, path: str, subflow_name: str
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
        if isinstance(invocation, LinkDeclaration):
            first = flow.action_config.flow.get(list(dependencies)[0])
            if first is None:
                return None
            return _get_action_invocation(first, flow, path, subflow_name)
        else:
            return (Action, str)

    else:
        _add_subflows(__copy_subflow(flow, invocation.flow), path, subflow_name)
        return (Action, str)


def _new_action(
    flow: Flow,
    action_name: ExecutableId | None,
    path: str,
    subflow_name: str,
):
    if flow.action_config.name is None:
        return

    is_default_action = False
    if action_name is None:
        action_name = flow.action_config.get_default_output()
        is_default_action = True
    invocation = flow.action_config.flow.get(action_name)
    if invocation is None:
        return
    action_invocation = _get_action_invocation(
        invocation, flow, path, f"{subflow_name}.{action_name}"
    )
    if action_invocation is None:
        return
    _type, outputs_type = action_invocation
    if _type is None:
        return

    if outputs_type is str:
        dependencies = set()
    else:
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
        full_action_name = subflow_name
    else:
        full_action_name = f"{subflow_name}.{action_name}"

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


def __copy_subflow(flow: Flow, flow_config: FlowConfig):
    subflow = copy.deepcopy(flow)
    subflow.action_config.flow = flow_config
    subflow.action_config.name = flow.action_config.name
    subflow = subflow.set_vars()
    return subflow
