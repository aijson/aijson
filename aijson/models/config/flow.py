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
    HintLiteral,
)
from aijson.utils.action_utils import build_hinted_value_declaration, build_actions
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


def build_model_config(
    strict: bool = False,
):
    # Dynamically build the model config like ActionModel, with the ValueDeclarations

    HintedValueDeclaration = build_hinted_value_declaration(
        strict=strict, excluded_declaration_types=[LinkDeclaration, LambdaDeclaration]
    )

    return transform_and_templatify_type(
        OptionalModelConfig,
        add_union=HintedValueDeclaration,  # type: ignore
        strict=strict,
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


def build_hinted_action_config(
    action_names: list[str] | None = None,
    vars_: HintLiteral | None = None,
    links: HintLiteral | None = None,
    include_paths: bool = False,
    strict: bool = False,
):
    HintedValueDeclaration = build_hinted_value_declaration(
        # vars_=vars_,
        links=links,
        strict=strict,
    )

    actions = build_actions(
        action_names=action_names,
        vars_=vars_,
        links=links,
        include_paths=include_paths,
        strict=strict,
    )
    if not actions:
        raise RuntimeError(
            "No actions found. Install some with `pip install aijson-meta`"
        )

    ActionInvocationUnion = Union[tuple(actions)]  # pyright: ignore

    class HintedLoop(Loop):
        in_: HintedValueDeclaration = Field(  # type: ignore
            ...,
            alias="in",
        )
        flow: "HintedFlowConfig"  # type: ignore

    if links is not None:
        DefaultOutputType = links | None
    else:
        DefaultOutputType = ContextVarPath | None

    class HintedActionConfig(ActionConfig):
        flow: "HintedFlowConfig"  # type: ignore
        default_output: DefaultOutputType = None  # type: ignore

    HintedExecutable = Union[ActionInvocationUnion, HintedLoop, HintedValueDeclaration]
    HintedFlowConfig = dict[ExecutableId, HintedExecutable]

    HintedActionConfig.model_rebuild()  # TODO is this necessary?

    return HintedActionConfig
