from aijson.models.config.value_declarations import ValueDeclaration
from typing_extensions import Any, assert_never

import structlog

from aijson.models.config.action import ActionInvocation
from aijson.utils.action_utils import get_actions_dict
from aijson.utils.pydantic_utils import is_basemodel_subtype
from aijson.utils.rendering_utils import extract_root_var
from aijson.models.config.flow import (
    ActionConfig,
    Loop,
    FlowConfig,
    Executable,
)
from aijson.models.config.model import ModelConfig
from aijson.models.primitives import ContextVarPath, ExecutableId
from aijson.services.action_service import ActionService


def _get_root_dependencies(
    input_spec: Any,
):
    dependency_tuples = (
        ActionService._get_dependency_ids_and_stream_flag_from_input_spec(input_spec)
    )
    return [dep for dep, _ in dependency_tuples]


def check_default_model_consistency(
    log: structlog.stdlib.BoundLogger,
    default_model: ModelConfig,
    variables: set[str],
):
    dependencies = _get_root_dependencies(default_model)

    unmet_dependencies = [dep for dep in dependencies if dep not in variables]

    pass_ = True

    for dep in unmet_dependencies:
        log.error("Variable not found", variable_name=dep)
        pass_ = False

    return pass_


def check_flow_consistency(
    log: structlog.stdlib.BoundLogger,
    nodes: list[ExecutableId],
    variables: set[str],
    flow: FlowConfig,
):
    pass_ = True

    for executable_id in nodes:
        log = log.bind(
            dependency_path=f"{log._context['dependency_path']}.{executable_id}"
        )
        invocation = flow[executable_id]
        if not check_invocation_consistency(log, flow, invocation, variables):
            pass_ = False

    return pass_


def check_loop_consistency(
    log: structlog.stdlib.BoundLogger,
    flow: FlowConfig,
    loop: Loop,
    variables: set[str],
):
    dependencies = _get_root_dependencies(loop.in_)

    unmet_dependencies = [dep for dep in dependencies if dep not in variables]

    pass_ = True

    for dep in unmet_dependencies:
        if dep not in flow:
            log.error("Dependency not found in flow", dependency=dep)
            pass_ = False
        else:
            if not check_invocation_consistency(
                log.bind(dependency_path=dep), flow, flow[dep], variables
            ):
                pass_ = False

    joint_variables = variables | {loop.for_}
    joint_flow = flow | loop.flow

    # TODO at time of writing all actions in the loop subflow are run;
    #  after we move from that, this shouldn't check against the whole flow, but only the relevant invocations
    if not check_flow_consistency(
        log, list(loop.flow), joint_variables, flow=joint_flow
    ):
        pass_ = False

    return pass_


def check_action_consistency(
    log: structlog.stdlib.BoundLogger,
    flow: FlowConfig,
    invocation: ActionInvocation | ValueDeclaration,
    variables: set[str],
):
    dependencies = _get_root_dependencies(invocation)

    unmet_dependencies = [dep for dep in dependencies if dep not in variables]

    pass_ = True

    for dep in unmet_dependencies:
        if dep not in flow:
            log.error("Dependency not found in flow", dependency=dep)
            pass_ = False
        else:
            if not check_invocation_consistency(
                log.bind(dependency_path=dep), flow, flow[dep], variables
            ):
                pass_ = False

    return pass_


def check_invocation_consistency(
    log: structlog.stdlib.BoundLogger,
    flow: FlowConfig,
    invocation: Executable,
    variables: set[str],
):
    if isinstance(invocation, Loop):
        return check_loop_consistency(log, flow, invocation, variables)
    elif isinstance(invocation, ActionInvocation):
        return check_action_consistency(log, flow, invocation, variables)
    elif isinstance(invocation, ValueDeclaration):
        return check_action_consistency(log, flow, invocation, variables)
    else:
        assert_never(invocation)


def check_config_consistency(
    log: structlog.stdlib.BoundLogger,
    config: ActionConfig,
    variables: set[str],
    target_output: ContextVarPath,
):
    pass_ = True

    if not check_default_model_consistency(
        log.bind(dependency_path="default_model"), config.default_model, variables
    ):
        pass_ = False

    root_dependency_id = extract_root_var(target_output)
    if root_dependency_id not in config.flow:
        log.error("Dependency not found in flow", dependency=root_dependency_id)
        return False

    if not check_invocation_consistency(
        log.bind(dependency_path=root_dependency_id),
        config.flow,
        config.flow[root_dependency_id],
        variables,
    ):
        pass_ = False

    return pass_


def get_invocation_dependencies(
    invocation: Executable,
) -> set[str]:
    if isinstance(invocation, Loop):
        return set(_get_root_dependencies(invocation.in_)) | {
            dep
            for dep in get_flow_dependencies(invocation.flow)
            if dep != invocation.for_
        }
    elif isinstance(invocation, (ActionInvocation, ValueDeclaration)):
        return set(_get_root_dependencies(invocation))
    else:
        assert_never(invocation)


def get_flow_dependencies(
    flow: FlowConfig,
) -> set[str]:
    vars_ = set()
    for invocation in flow.values():
        vars_ |= {
            dep for dep in get_invocation_dependencies(invocation) if dep not in flow
        }
    return vars_


def get_config_variables(
    config: ActionConfig,
) -> set[str]:
    return set(_get_root_dependencies(config.default_model)) | get_flow_dependencies(
        config.flow
    )


def get_dependency_map(
    config: ActionConfig,
) -> dict[str, set[str]]:
    base_deps = set(_get_root_dependencies(config.default_model))
    dependencies_for_invocation = {
        invocation_id: get_invocation_dependencies(invocation)
        for invocation_id, invocation in config.flow.items()
    }

    def resolve_deps(invocation_id: str) -> set[str]:
        resolved_deps = set(dependencies_for_invocation[invocation_id])
        for dependency in dependencies_for_invocation[invocation_id]:
            if dependency in dependencies_for_invocation:
                resolved_deps |= resolve_deps(dependency)
        return resolved_deps

    return {
        invocation_id: base_deps | resolve_deps(invocation_id)
        for invocation_id in config.flow
    }


def get_variable_dependency_map(
    config: ActionConfig,
) -> dict[str, set[str]]:
    dependency_map = get_dependency_map(config)
    return {
        invocation_id: {d for d in dependencies if d not in config.flow}
        for invocation_id, dependencies in dependency_map.items()
    }


def get_link_dependency_map(
    config: ActionConfig,
) -> dict[str, set[str]]:
    dependency_map = get_dependency_map(config)
    return {
        invocation_id: {d for d in dependencies if d in config.flow}
        for invocation_id, dependencies in dependency_map.items()
    }


def get_target_outputs(config: ActionConfig):
    actions_dict = get_actions_dict()

    legal_target_outputs = []
    for action_id, action_invocation in config.flow.items():
        # TODO handle loop
        if isinstance(action_invocation, Loop):
            continue
        elif isinstance(action_invocation, ActionInvocation):
            action = actions_dict[action_invocation.action]
            outputs_type = action._get_outputs_type(action_invocation)
        elif isinstance(action_invocation, ValueDeclaration):
            # TODO is this right
            outputs_type = Any
        else:
            assert_never(action_invocation)
        legal_target_outputs.append(action_id)
        if not is_basemodel_subtype(outputs_type):
            continue
        for output_name, output_field in outputs_type.model_fields.items():
            if output_field.deprecated:
                continue
            full_output_name = f"{action_id}.{output_name}"
            legal_target_outputs.append(full_output_name)
    return legal_target_outputs
