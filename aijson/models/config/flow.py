from typing import Union, Literal

from pydantic import Field

from aijson.models.config.action import (
    ActionInvocation,
)
from aijson.models.config.common import StrictModel
from aijson.models.config.model import OptionalModelConfig
from aijson.utils.type_utils import transform_and_templatify_type
from aijson.models.config.value_declarations import ValueDeclaration
from aijson.models.primitives import (
    ContextVarName,
    ContextVarPath,
    ExecutableId,
)
from aijson.utils.action_utils import build_value_declaration, build_actions
from aijson.models.config.value_declarations import (
    LinkDeclaration,
    LambdaDeclaration,
)


class Loop(StrictModel):
    for_: ContextVarName = Field(
        ...,
        alias="for",
    )
    in_: ValueDeclaration = Field(
        ...,
        alias="in",
    )
    flow: "FlowConfig"


def build_model_config():
    # Dynamically build the model config like ActionModel, with the ValueDeclarations

    PartialValueDeclaration = build_value_declaration(
        excluded_declaration_types=[LinkDeclaration, LambdaDeclaration]
    )

    return transform_and_templatify_type(
        OptionalModelConfig,
        add_union=PartialValueDeclaration,  # type: ignore
    )


ModelConfigDeclaration = build_model_config()


class ActionConfig(StrictModel):
    version: Literal["0.1"]  # TODO implement migrations
    default_model: ModelConfigDeclaration = OptionalModelConfig()  # type: ignore
    action_timeout: float = 360
    flow: "FlowConfig"
    default_output: ContextVarPath | None = None  # TODO `| ValueDeclaration`

    def get_default_output(self) -> ContextVarPath:
        if self.default_output is not None:
            return self.default_output
        # return last output of the flow
        return list(self.flow.keys())[-1]


Executable = Union[ActionInvocation, Loop, ValueDeclaration]
FlowConfig = dict[ExecutableId, Executable]


def build_action_config(
    action_names: list[str] | None = None,
    include_paths: bool = False,
):
    actions = build_actions(
        action_names=action_names,
        include_paths=include_paths,
    )
    if not actions:
        raise RuntimeError(
            "No actions found. Install some with `pip install aijson-meta`"
        )

    ActionInvocationUnion = Union[tuple(actions)]  # pyright: ignore

    class HintedLoop(Loop):
        in_: ValueDeclaration = Field(  # type: ignore
            ...,
            alias="in",
        )
        flow: "HintedFlowConfig"  # type: ignore

    DefaultOutputType = ContextVarPath | None

    class HintedActionConfig(ActionConfig):
        flow: "HintedFlowConfig"  # type: ignore
        default_output: DefaultOutputType = None  # type: ignore

    HintedExecutable = Union[ActionInvocationUnion, HintedLoop, ValueDeclaration]
    HintedFlowConfig = dict[ExecutableId, HintedExecutable]

    HintedActionConfig.model_rebuild()  # TODO is this necessary?

    return HintedActionConfig
