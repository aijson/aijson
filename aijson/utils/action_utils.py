import ast
import importlib
import importlib.util
import inspect
import os
import sys
import types
import typing
from typing import Any, Annotated, AsyncIterator, Literal, Union, Type

import pydantic
from pydantic import Field, ConfigDict, create_model
from pydantic.config import JsonDict

from pydantic.fields import FieldInfo

from aijson.log_config import get_logger
from aijson.models.config.action import (
    Action,
    InternalActionBase,
    ActionInvocation,
    ActionMeta,
    StreamingAction,
)
from aijson.models.config.value_declarations import (
    LinkDeclaration,
    ValueDeclaration,
)
from aijson.models.func import _prepare_kwargs
from aijson.models.io import Inputs, Outputs
from aijson.models.primitives import (
    ExecutableName,
)
from aijson.utils.json_schema_utils import ModelNamer
from aijson.utils.pydantic_utils import is_basemodel_subtype
from aijson.utils.type_utils import (
    build_field_description,
    build_object_uri,
    templatify_fields,
)


def build_input_fields(
    action: type[InternalActionBase[Inputs, Outputs]],
    *,
    add_union: type | types.UnionType | None = None,
    include_paths: bool,
    action_invocation: ActionInvocation | None = None,
) -> dict[str, tuple[type, Any]]:
    inputs_type = action._get_inputs_type()
    if not is_basemodel_subtype(inputs_type):
        return {}

    # generate action description
    action_title = build_action_title(action, markdown=False, title_suffix=" Input")
    action_description = build_action_description(
        action,
        action_invocation=action_invocation,
        markdown=False,
        include_title=False,
        include_io=False,
        include_paths=include_paths,
    )
    markdown_action_description = build_action_description(
        action,
        action_invocation=action_invocation,
        markdown=True,
        include_title=False,
        include_io=False,
        include_paths=include_paths,
    )

    new_field_infos = {}

    # add input description
    for field_name, field_info in inputs_type.model_fields.items():
        # field_title = field_name.replace("_", " ").title()
        # title = f"{field_title}: {action_title}"

        title = action_title

        field_description = build_field_description(
            field_name, field_info, markdown=False, include_paths=include_paths
        )
        markdown_field_description = f"- {build_field_description(field_name, field_info, markdown=True, include_paths=include_paths)}"

        description = field_description
        if action_description:
            description = action_description + "\n\n" + description
        markdown_description = markdown_field_description + "\n\n---"
        if markdown_action_description:
            markdown_description = (
                markdown_action_description + "\n\n" + markdown_description
            )

        new_field_info = FieldInfo.merge_field_infos(
            field_info,
            title=title,
            description=description,
            json_schema_extra={
                "markdownDescription": markdown_description,
            },
        )
        new_field_infos[field_name] = new_field_info

    # templatify the input fields
    return templatify_fields(new_field_infos, add_union)


def _get_recursive_subfields(
    obj: dict | pydantic.BaseModel | Any,
    base_description: str | None,
    base_markdown_description: str | None,
    include_paths: bool,
    name_prefix: str = "",
) -> list[type[str]]:
    out = []
    # TODO make it so that non-pydantic output models properly create the link hint
    # if isinstance(obj, dict):
    #     for name, field in obj.items():
    #         # out.append(name)
    #         out.extend(_get_recursive_subfields(field, base_description, base_markdown_description, f"{name}."))
    if is_basemodel_subtype(obj):
        for name, field in obj.model_fields.items():
            annotated_field = _build_annotated_field(
                base_description=base_description,
                base_markdown_description=base_markdown_description,
                field=field,
                include_paths=include_paths,
                name=name,
                name_prefix=name_prefix,
            )
            out.append(annotated_field)
            out.extend(
                _get_recursive_subfields(
                    field.annotation,
                    base_description,
                    base_markdown_description,
                    include_paths=include_paths,
                    name_prefix=f"{name_prefix}{name}.",
                )
            )
    return out


def _build_annotated_field(
    base_description: str | None,
    base_markdown_description: str | None,
    field: FieldInfo,
    include_paths: bool,
    name: str,
    alias_name: str | None = None,
    name_prefix: str = "",
) -> type[str]:
    if alias_name is None:
        alias_name = name
    description = build_field_description(
        name, field, markdown=False, include_paths=include_paths
    )
    if base_description:
        description = base_description + "\n\n" + description
    markdown_description = (
        "- "
        + build_field_description(
            name, field, markdown=True, include_paths=include_paths
        )
        + "\n\n---"
    )
    if base_markdown_description:
        markdown_description = base_markdown_description + "\n\n" + markdown_description
    annotated_field = Annotated[
        Literal[f"{name_prefix}{alias_name}"],
        Field(
            description=description,
            json_schema_extra={
                "markdownDescription": markdown_description,
            },
        ),
    ]
    # TODO figure out a typehint for this, why does type[str] not work?
    return annotated_field  # type: ignore


def build_action_title(
    action: type[InternalActionBase],
    *,
    markdown: bool,
    title_suffix: str = "",
) -> str:
    if action.readable_name:
        title = action.readable_name
    else:
        title = action.name.replace("_", " ").title()
    title += " Action"

    title = f"{title}{title_suffix}"

    if markdown:
        title = f"**{title}**"
    return title


def build_action_description(
    action: type[InternalActionBase[Inputs, Outputs]],
    *,
    markdown: bool,
    include_paths: bool,
    action_invocation: ActionInvocation | None = None,
    include_title: bool = False,
    title_suffix: str = "",
    include_io: bool = True,
) -> None | str:
    description_items = []

    if include_title:
        title = build_action_title(action, markdown=markdown, title_suffix=title_suffix)
        description_items.append(title)

    # grab the main description
    if action.description:
        description_items.append(inspect.cleandoc(action.description))

    if include_io:
        # add inputs description
        inputs_description_items = []
        inputs_type = action._get_inputs_type()
        if is_basemodel_subtype(inputs_type):
            for field_name, field_info in inputs_type.model_fields.items():
                inputs_description_items.append(
                    f"- {build_field_description(field_name, field_info, markdown=markdown, include_paths=include_paths)}"
                )
        if inputs_description_items:
            if markdown:
                title = "**Inputs**"
            else:
                title = "INPUTS"
            description_items.append(f"{title}\n" + "\n".join(inputs_description_items))

        # add outputs description
        outputs_description_items = []
        outputs_type = action._get_outputs_type(action_invocation)
        if is_basemodel_subtype(outputs_type):
            for field_name, field_info in outputs_type.model_fields.items():
                outputs_description_items.append(
                    f"- {build_field_description(field_name, field_info, markdown=markdown, include_paths=include_paths)}"
                )
        elif outputs_type is not type(None):
            outputs_description_items.append(
                f"- {build_field_description(None, FieldInfo(annotation=outputs_type), markdown=markdown, include_paths=include_paths)}"
            )
        if outputs_description_items:
            if markdown:
                title = "**Outputs**"
            else:
                title = "OUTPUTS"
            description_items.append(
                f"{title}\n" + "\n".join(outputs_description_items)
            )

    if not description_items:
        return None
    return "\n\n".join(description_items)


def build_value_declaration(
    excluded_declaration_types: None | list[type[ValueDeclaration]] = None,
) -> type[ValueDeclaration]:
    if excluded_declaration_types is None:
        excluded_declaration_types = []

    union_elements = [
        element
        for element in typing.get_args(ValueDeclaration)
        if element not in excluded_declaration_types
    ]

    return Union[tuple(union_elements)]  # type: ignore


def build_actions(
    action_names: list[str] | None = None,
    include_paths: bool = False,
):
    # Dynamically build action models from currently defined actions
    # for best typehints and autocompletion possible in the jsonschema

    if action_names is None:
        action_names = list(get_actions_dict().keys())

    actions_dict = get_actions_dict()
    action_models = []
    for action_name in action_names:
        action = actions_dict[action_name]

        title = build_action_title(action, markdown=False)

        description = build_action_description(
            action, markdown=False, include_paths=include_paths
        )
        markdown_description = build_action_description(
            action, markdown=True, include_paths=include_paths
        )

        # build action literal
        action_literal = Literal[action.name]  # type: ignore

        json_schema_extra_items = {}

        # add title
        action_literal = Annotated[
            action_literal,
            Field(
                title=title,
            ),
        ]

        # add description
        if description is not None:
            action_literal = Annotated[
                action_literal,
                Field(
                    description=description,
                ),
            ]
            if markdown_description is not None:
                json_schema_extra_items["markdownDescription"] = (
                    markdown_description + "\n\n---",
                )

        # add uri data for LSP
        uri_data = build_object_uri(action)
        if uri_data is not None:
            json_schema_extra_items["uri_data"] = typing.cast(JsonDict, uri_data)

        # add json schema extra (this has to be separate else one overrides the other)
        if json_schema_extra_items:
            action_literal = Annotated[
                action_literal,
                Field(json_schema_extra=json_schema_extra_items),
            ]

        # build base model field
        fields = {
            "action": (
                action_literal,
                ...,
            ),
            "cache_key": (None | str | ValueDeclaration, None),
        }

        # build input fields
        fields |= build_input_fields(
            action,
            add_union=ValueDeclaration,
            include_paths=include_paths,
        )

        # build action invocation model
        action_basemodel = pydantic.create_model(
            action.name + "ActionInvocation",
            __base__=ActionInvocation,
            __module__=__name__,
            __doc__=description,
            model_config=ConfigDict(
                title=title,
                json_schema_extra={
                    "markdownDescription": markdown_description,
                },
                arbitrary_types_allowed=True,
                extra="forbid",
            ),
            **fields,  # pyright: ignore[reportGeneralTypeIssues]
        )
        action_models.append(action_basemodel)
    return action_models


def recursive_import(package_name):
    import pkgutil
    import importlib

    package = importlib.import_module(package_name)
    if not hasattr(package, "__path__"):
        return
    for _, module_name, is_pkg in pkgutil.walk_packages(
        package.__path__, package.__name__ + "."
    ):
        try:
            if is_pkg:
                recursive_import(module_name)
            else:
                importlib.import_module(module_name)
        except ImportError as e:
            print(f"Failed to import {module_name}: {e}")


_processed_entrypoints = set()
_processed_subflows = set()
_processing_subflows = False


def file_contains_action_import(filepath: str):
    if not filepath.endswith(".py"):
        return False
    with open(filepath) as f:
        try:
            tree = ast.parse(f.read())
        except Exception:
            return False
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module is None:
                continue
            if "aijson" not in node.module:
                continue
            if any(
                action_import in [n.name for n in node.names]
                for action_import in (
                    "register_action",
                    "StreamingAction",
                    "Action",
                )
            ):
                return True
    return False


def import_custom_actions(path: str):
    """
    Recursively search for custom actions in the given path
    The files are not imported, they are analyzed statically for
    `register_action`, `StreamingAction` or `Action` imports.
    """
    # TODO needs a proper test
    namer = ModelNamer("__aijson_actions_module")
    for root, dirs, files in os.walk(path):
        files = [f for f in files if not f[0] == "."]
        dirs[:] = [
            d
            for d in dirs
            if not d[0] == "."
            and "site-packages" not in dirs
            # TODO can we remove the above checks for sake of this one?
            and os.path.exists(os.path.join(root, d, "__init__.py"))
        ]
        for file in files:
            filepath = os.path.join(root, file)
            if not file_contains_action_import(filepath):
                continue
            module_name = namer.get()
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None:
                continue
            module = importlib.util.module_from_spec(spec)
            try:
                sys.modules[module_name] = module
                if spec.loader is None:
                    continue
                spec.loader.exec_module(module)
            except Exception:
                if module_name in sys.modules:
                    del sys.modules[module_name]


def get_actions_dict(
    entrypoint_whitelist: list[str] | None = None,
) -> dict[ExecutableName, Type[InternalActionBase[Any, Any]]]:
    import importlib_metadata
    from aijson.utils.static_utils import get_config_variables

    global _processing_subflows

    # global _processing_subflows

    # import all action entrypoints
    entrypoints = importlib_metadata.entry_points(group="aijson")
    for entrypoint in entrypoints.select(name="actions"):
        dist_name = entrypoint.dist.name
        if dist_name in _processed_entrypoints or (
            entrypoint_whitelist is not None and dist_name not in entrypoint_whitelist
        ):
            continue
        _processed_entrypoints.add(dist_name)
        try:
            recursive_import(entrypoint.value)
        except Exception as e:
            print(f"Failed to import {dist_name} entrypoint: {e}")

    if not _processing_subflows:
        from aijson.utils.extend_action_dict_utils import extend_actions_dict
        from aijson.models.config.flow import Executable
        from aijson.flow import Flow

        def _get_action_invocation(invocation: Executable, flow: Flow) -> tuple[type[Action]|type[StreamingAction], type] | None:
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
        

        _processing_subflows = True
        all_subflows = extend_actions_dict()
        for flow_name in all_subflows:
            flow = all_subflows.get(flow_name)
            if flow is None:
                continue
            if flow.action_config.name is None:
                continue
            if flow.action_config.name in _processed_subflows:
                continue
            _processed_subflows.add(flow.action_config.name)
            outputs_type = None
            _type = None
            target_output = flow.action_config.get_default_output()
            invocation = flow.action_config.flow.get(target_output)
            if invocation is None:
                continue
            action_invocation = _get_action_invocation(invocation, flow)
            if action_invocation is None:
                continue
            _type, outputs_type = action_invocation
            if _type is None:
                continue

            dependencies = get_config_variables(flow.action_config)

            field_definitions = {}
            for dependency in dependencies:
                field_definitions[dependency] = (str, ...)

            InputsModel = create_model(
                flow.action_config.name,
                model_config=ConfigDict(
                    arbitrary_types_allowed=True,
                ),
                # __base__ = inputs_type,
                **field_definitions,
            )

            if _type == StreamingAction:

                class streaming_action(StreamingAction[InputsModel, outputs_type]):
                    name = flow.action_config.name
                    target = target_output
                    subflow = flow

                    async def run(self, inputs) -> AsyncIterator[Any]:
                        if flow is not None:
                            args = _prepare_kwargs(inputs)
                            new_flow = self.subflow.set_vars(**args)
                            run = new_flow.stream(self.target)
                            async for i in run:
                                yield i

                streaming_action(get_logger(), "")
            elif _type == Action:

                class action(Action[InputsModel, outputs_type]):
                    name = flow.action_config.name
                    target = target_output
                    subflow = flow

                    async def run(self, inputs):
                        if flow is not None:
                            args = _prepare_kwargs(inputs)
                            new_flow = self.subflow.set_vars(**args)
                            return await new_flow.run(self.target)

                action(get_logger(), "")
    # return all subclasses of Action as registered in the metaclass
    return ActionMeta.actions_registry


           
