import inspect
import types
import typing
from collections.abc import AsyncIterator
from typing import Callable, Any, overload, TypeVar

import pydantic
from pydantic import BaseModel
from pydantic.fields import Field

from aijson.models.config.action import Action, StreamingAction
from aijson.utils.subtype_utils import is_subtype


def _prepare_kwargs(inputs_model: BaseModel):
    kwargs = {}
    for name in inputs_model.model_fields:
        # TODO make sure aliases work fine?
        kwargs[name] = getattr(inputs_model, name)
    return kwargs


def _prepare_func(func: Callable):
    if inspect.isasyncgenfunction(func):

        async def _(self, inputs_model: BaseModel):
            kwargs = _prepare_kwargs(inputs_model)
            async for ret in func(**kwargs):
                yield ret
    else:

        async def _(self, inputs_model: BaseModel):
            kwargs = _prepare_kwargs(inputs_model)
            if inspect.iscoroutinefunction(func):
                return await func(**kwargs)
            return func(**kwargs)

    return _


def _construct_decorator(
    name: str | None = None,
    description: str | None = None,
    cache: bool = True,
    version: int | None = None,
):
    def _(func: Callable):
        nonlocal name
        nonlocal description
        # nonlocal cache
        # nonlocal version

        # inspect name, docstring
        if name is None:
            name = func.__name__
        if description is None:
            description = inspect.getdoc(func)

        # infer inputs
        sig = inspect.signature(func)
        model_fields = {}
        for param_name, param in sig.parameters.items():
            annotation = param.annotation
            if annotation is inspect._empty:
                annotation = Any
            field_info_kwargs = {}
            if param.default is not inspect._empty:
                field_info_kwargs["default"] = param.default
            model_fields[param_name] = (annotation, Field(**field_info_kwargs))
        InputsModel = pydantic.create_model("FuncInputs" + f"__{name}", **model_fields)

        OutputsModel = sig.return_annotation
        if sig.return_annotation is inspect._empty:
            # TODO make sure Any works as an output
            OutputsModel = Any
        elif inspect.isasyncgenfunction(func):
            # return typehint should be AsyncIterator or AsyncGenerator
            base = typing.get_origin(OutputsModel)
            if is_subtype(base, AsyncIterator):
                # first arg should be YieldType
                OutputsModel = typing.get_args(OutputsModel)[0]
            else:
                raise NotImplementedError(
                    f"Unsupported base return type for {name}: {base}"
                )

        # TODO test streaming
        run = _prepare_func(func)

        attrs = {
            "name": name,
            "description": description,
            "cache": cache,
            "version": version,
            "run": run,
            "_aijson__mapped_func": func,
        }

        def exec_body(ns):
            # have to use exec_body instead of passing the attrs directly
            # because of name arg collision with `name` in the type constructor
            for name, val in attrs.items():
                ns[name] = val

        if inspect.isasyncgenfunction(run):
            types.new_class(
                "_",
                (StreamingAction[InputsModel, OutputsModel],),
                exec_body=exec_body,
            )
        else:
            types.new_class(
                "_",
                (Action[InputsModel, OutputsModel],),
                exec_body=exec_body,
            )

        return func

    return _


T = TypeVar("T", bound=Callable)


@overload
def register_action(
    func: T,
) -> T: ...


@overload
def register_action(
    *,
    name: str | None = None,
    description: str | None = None,
    cache: bool = True,
    version: int | None = None,
) -> Callable[
    [
        T,
    ],
    T,
]: ...


def register_action(
    func=None,
    *,
    name: str | None = None,
    description: str | None = None,
    cache: bool = True,
    version: int | None = None,
):
    """
    Create a function decorator that register it as an action.

    Parameters
    ----------
    name: str | None
    The name of the action, used to identify it in the aijson configuration. Required.

    description: str | None
    The description of the action, used to describe it to the LLM upon action selection. Optional.

    cache: bool
    Whether to cache the result of this action. Defaults to `True`.

    version: int
    The version of the action, used to persist cache across project changes.
    Optional, defaults to `None` (never cache across project changes).
    """

    deco = _construct_decorator(
        name=name,
        description=description,
        cache=cache,
        version=version,
    )

    if func is not None:
        return deco(func)
    else:
        return deco
