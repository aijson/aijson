from typing import Literal, Union, assert_never

import pydantic
from aijson.models.config.flow import ActionConfig, Executable, Loop
from aijson.utils.action_utils import (
    get_actions_dict,
    build_action_description,
    _build_annotated_field,
    _get_recursive_subfields,
)
from aijson.utils.loader_utils import load_config_file

from pydantic.fields import FieldInfo

from aijson.log_config import get_logger
from aijson.models.config.action import (
    ActionInvocation,
)
from aijson.models.config.value_declarations import (
    ValueDeclaration,
)
from aijson.models.io import DefaultOutputOutputs
from aijson.models.primitives import (
    ExecutableId,
    LinkHints,
)
from aijson.utils.pydantic_utils import is_basemodel_subtype


def build_link_hints(
    config_filename: str,
    strict: bool,
    include_paths: bool,
) -> LinkHints:
    """
    Builds a dictionary mapping namespace paths in the flow (including subflows)
    to hint literals of possible link values.
    """

    try:
        # load the file not as a non-strict model
        action_config = load_config_file(config_filename, config_model=ActionConfig)
    except pydantic.ValidationError:
        log = get_logger()
        log.debug(
            "Failed to load action config",
            exc_info=True,
        )
        return {}

    actions_dict = get_actions_dict()

    def build(flow: dict[ExecutableId, Executable], flow_id: ExecutableId) -> LinkHints:
        link_hints = {}

        namespace_types = []
        if not strict:
            namespace_types.append(str)

        for executable_id, executable_invocation in flow.items():
            if isinstance(executable_invocation, Loop):
                # TODO give better hints for internals of loop
                # executable_literal = Literal[executable_id]  # type: ignore
                # namespace_types.append(executable_literal)
                link_hints |= build(
                    executable_invocation.flow, f"{flow_id}.{executable_id}"
                )
                continue
            elif isinstance(executable_invocation, ValueDeclaration):
                executable_literal = Literal[executable_id]  # type: ignore
                namespace_types.append(executable_literal)
                continue
            elif isinstance(executable_invocation, ActionInvocation):
                # if there are any models, then each recursive subfield is a var, like jsonpath
                try:
                    action_type = actions_dict[executable_invocation.action]
                except KeyError:
                    continue
                outputs_type = action_type._get_outputs_type(executable_invocation)
                base_description = build_action_description(
                    action_type,
                    action_invocation=executable_invocation,
                    markdown=False,
                    include_title=True,
                    include_io=False,
                    include_paths=include_paths,
                    title_suffix=" Output",
                )
                base_markdown_description = build_action_description(
                    action_type,
                    action_invocation=executable_invocation,
                    markdown=True,
                    include_title=True,
                    include_io=False,
                    include_paths=include_paths,
                    title_suffix=" Output",
                )

                if is_basemodel_subtype(outputs_type):
                    if issubclass(outputs_type, DefaultOutputOutputs):
                        output_attr = outputs_type._default_output
                        field = outputs_type.model_fields[output_attr]
                        annotated_field = _build_annotated_field(
                            base_description=base_description,
                            base_markdown_description=base_markdown_description,
                            field=field,
                            include_paths=include_paths,
                            name=output_attr,
                            alias_name=executable_id,
                        )
                        namespace_types.append(annotated_field)
                    namespace_types.extend(
                        _get_recursive_subfields(
                            outputs_type,
                            base_description,
                            base_markdown_description,
                            include_paths=include_paths,
                            name_prefix=f"{executable_id}.",
                        )
                    )
                else:
                    namespace_types.append(
                        _build_annotated_field(
                            base_description=base_description,
                            base_markdown_description=base_markdown_description,
                            field=FieldInfo(
                                annotation=outputs_type,
                            ),
                            include_paths=include_paths,
                            name=executable_id,
                        )
                    )

            else:
                assert_never(executable_invocation)

        if namespace_types:
            hint_union = Union[tuple(namespace_types)]  # type: ignore
        else:
            hint_union = str

        link_hints[flow_id] = hint_union
        return link_hints

    return build(action_config.flow, "$")