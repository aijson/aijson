import inspect
import os
import types
from enum import Enum
from typing import Any, Literal, Union, TypedDict

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from aijson.models.config.transform import TransformsFrom
import typing
from typing import Annotated

import pydantic

from aijson.models.primitives import HintLiteral
from aijson.utils.pydantic_utils import is_basemodel_subtype
from aijson.utils.subtype_utils import is_subtype

# forgive me father for I have sinned
# "I have used a global variable", says copilot
# this goes beyond mere global variables
# here is a function that transforms types, and renamespaces them to this module if they're pydantic models
# some types have recursive references, so we cache their forward references

# edit: im kind of proud of this function now that it's been refactored a bit


# TODO could we make these weakrefs somehow? the weakref would need to be tied to the type object
_forward_ref_cache = {}
_transformation_cache = {}


def templatify_fields(
    fields: dict[str, FieldInfo],
    add_union: type | types.UnionType | None = None,
):
    new_fields = {}
    for field_name, field_ in fields.items():
        # Annotate optional fields with a default of None
        if field_.default is not PydanticUndefined:
            default = field_.default
        elif not field_.is_required():
            default = None
        else:
            default = ...
        field_type = field_.annotation

        # recurse over each field
        new_field_type = transform_and_templatify_type(
            field_type,
            add_union,
        )

        # add a union to the mix
        if add_union is not None:
            # raise if `add_union` collides with existing an existing field name
            # TODO should we just not add the union if it collides?
            # for field_name in type_.model_fields:
            #     if any(
            #         field_name in m.model_fields for m in typing.get_args(add_union)
            #     ):
            #         raise ValueError(f"{field_name} is a restricted field name.")
            # if field type is dict-like, it swallos any add union typed dicts/models
            # so we put add union first
            new_field_type = Union[add_union, new_field_type]

        # keep original FieldInfo
        annotated_field_type = Annotated[new_field_type, field_]

        new_fields[field_name] = (annotated_field_type, default)

    return new_fields


def templatify_model(
    type_: type[BaseModel],
    add_union: type | types.UnionType | None = None,
):
    return templatify_fields(
        type_.model_fields,
        add_union,
    )


def transform_and_templatify_type(
    type_: Any,
    add_union: type | types.UnionType | None = None,
) -> Any:  # Union[type[ConfigType], type[ImplementsTransformsInContext]]:
    # cache resolved types to avoid forward references when unnecessary
    cache_key = str(type_)
    if cache_key in _transformation_cache:
        return _transformation_cache[cache_key]
    # cache ForwardRefs to avoid infinite recursion
    if cache_key in _forward_ref_cache:
        return _forward_ref_cache[cache_key]

    # determine `name` and `module`,
    # store ForwardRef if necessary
    if (
        hasattr(type_, "__name__")
        and not hasattr(type_, "__origin__")
        and type_.__module__ != "builtins"
    ):
        if is_basemodel_subtype(type_):
            name = f"{type_.__name__}"
            module = __name__
        else:
            name = type_.__name__
            module = type_.__module__
        _forward_ref_cache[cache_key] = typing.ForwardRef(
            arg=name,
            module=module,
        )
    else:
        name = None
        module = None

    # TODO use remove_optional here?

    origin = typing.get_origin(type_)
    args = typing.get_args(type_)
    if origin is types.UnionType:
        origin = Union

    # remove None from union and denote as optional
    if origin is Union and type(None) in args:
        is_optional = True
        args = tuple(arg for arg in args if arg is not type(None))
        if len(args) == 1:
            type_ = args[0]
        else:
            type_ = Union[args]  # type: ignore
    else:
        is_optional = False

    # recurse over type args if it's a type with origin
    if origin is not None:
        args = tuple(transform_and_templatify_type(arg, add_union) for arg in args)
        type_ = origin[args]  # type: ignore
    # special case pydantic models
    elif is_basemodel_subtype(type_):
        fields = templatify_model(
            type_,
            add_union=add_union,
        )
        # repackage the pydantic model
        # TODO does this break anything? the module namespacing miiiight be a problem
        type_ = pydantic.create_model(
            name or type_.__name__,
            __base__=type_,
            __module__=module or __name__,
            **fields,
        )
        type_.model_rebuild()

    # resolve TransformsFrom
    if is_subtype(type_, TransformsFrom):
        type_ = type_._get_config_type()

    if is_optional:
        type_ = Union[type_, None]
    _transformation_cache[cache_key] = type_
    return type_


def build_type_qualified_name(
    type_: type | types.UnionType, *, markdown: bool, include_paths: bool
) -> str:
    if type_ is type(None):
        return "None"

    # convert unions to a string
    origin = typing.get_origin(type_)
    if origin is not None:
        if origin in [Union, types.UnionType]:
            args = typing.get_args(type_)
            return " | ".join(
                build_type_qualified_name(
                    arg, markdown=markdown, include_paths=include_paths
                )
                for arg in args
            )

        # convert literal to a string
        if origin is Literal:
            args = typing.get_args(type_)
            return " | ".join(repr(arg) for arg in args)

        # handle other origins
        origin_qual_name = build_type_qualified_name(
            origin, markdown=markdown, include_paths=include_paths
        )
        args_qual_names = " | ".join(
            build_type_qualified_name(
                arg, markdown=markdown, include_paths=include_paths
            )
            for arg in typing.get_args(type_)
        )
        return f"{origin_qual_name}[{args_qual_names}]"

    # handle TransformsFrom
    if is_subtype(type_, TransformsFrom):
        return build_type_qualified_name(
            type_._get_config_type(),
            markdown=markdown,
            include_paths=include_paths,
        )

    # convert string enums to a string
    if is_subtype(type_, Enum):
        return " | ".join(repr(member.value) for member in type_)

    # if hasattr(type_, "title") and isinstance(type_.title, str):
    #     name = type_.title
    # else:
    name = type_.__qualname__

    # pass through names of simple and well-known types
    if type_.__module__ in ["builtins", "typing"]:
        return name

    # add markdown link to custom types
    if not markdown or not include_paths:
        return name

    # Building the link to the source code file
    uri_data = build_object_uri(type_)
    if uri_data is None:
        # Fallback to just the type name if we can't get the source file
        return name
    file_url = f"{uri_data['file_uri']}#L{uri_data['line']}"
    return f"[{name}]({file_url})"


URIDict = TypedDict("URIDict", {"file_uri": str, "line": int})


def build_object_uri(obj: Any) -> URIDict | None:
    if hasattr(obj, "_aijson__mapped_func"):
        obj = obj._aijson__mapped_func
    try:
        # Get the file and line number where the type is defined
        source_file = inspect.getfile(obj)
        source_line = inspect.getsourcelines(obj)[1]
        # Construct the file URL
        source_path = os.path.abspath(source_file)
        # file_url = f"file://{source_path}#L{source_line}"
        return {"file_uri": f"file://{source_path}", "line": source_line}
    except Exception:
        return None


# TODO this used to be `-> tuple[type, bool]`, is there a better typehint now that type[Any] is not subclass of type?
def remove_optional(type_: type | None) -> tuple[Any, bool]:
    if type_ is None:
        return typing.Any, True
    if typing.get_origin(type_) in [Union, types.UnionType]:
        args = typing.get_args(type_)
        is_optional = False
        if type(None) in args:
            args = tuple(arg for arg in args if arg is not type(None))
            is_optional = True
        if len(args) == 1:
            return args[0], is_optional
        return Union[args], is_optional  # type: ignore
    return type_, False


def build_field_description(
    field_name: str | None,
    field_info: FieldInfo,
    *,
    markdown: bool,
    include_paths: bool,
) -> str:
    type_, is_optional = remove_optional(field_info.annotation)
    qualified_name = build_type_qualified_name(
        type_, markdown=markdown, include_paths=include_paths
    )

    if field_info.alias:
        field_name = field_info.alias

    if field_name is not None:
        field_desc = f"`{field_name}`: {qualified_name}"
    else:
        field_desc = qualified_name
    if field_info.default not in (
        None,
        PydanticUndefined,
    ):
        field_desc += f" (default: {repr(field_info.default)})"
    elif is_optional:
        field_desc += " (optional)"

    if field_info.description:
        field_desc += f"  \n  {field_info.description}"

    return field_desc


def build_var_literal(
    vars_: list[str],
    strict: bool,
):
    union_elements = []

    if not strict:
        union_elements.append(str)

    if vars_:
        union_elements.append(Literal[tuple(vars_)])  # type: ignore

    if union_elements:
        return Union[tuple(union_elements)]  # type: ignore
    return str


def get_var_string(
    hint_literal: HintLiteral | None,
    strict: bool,
) -> str:
    if hint_literal is None:
        var_str = ""
    else:
        # hint_literal is a nested annotated literal union, pull out only the strings
        strings = []
        frontier = [hint_literal]
        while frontier:
            arg = frontier.pop()
            if isinstance(arg, str):
                strings.append(arg)
            elif hasattr(arg, "__args__"):
                frontier.extend(arg.__args__)  # type: ignore

        var_str = "".join(strings)
    if strict:
        var_str = var_str + "__strict"
    return var_str
