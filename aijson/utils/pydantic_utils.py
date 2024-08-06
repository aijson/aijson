from typing import TypeGuard, Any

from pydantic import BaseModel

from aijson.utils.subtype_utils import is_subtype


def iterate_fields(model: BaseModel):
    for key in model.model_dump(exclude_unset=True):
        value = getattr(model, key)
        field_info = model.model_fields[key]
        name = key if field_info.alias is None else field_info.alias
        yield name, value


def is_basemodel_subtype(value: Any) -> TypeGuard[type[BaseModel]]:
    return is_subtype(value, BaseModel)
