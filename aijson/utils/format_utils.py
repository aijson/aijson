from typing import Any
import pydantic
import json

import pydantic_core


def json_block(text: str) -> str:
    return "```json\n" + text + "\n```"


def format_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, pydantic.BaseModel):
        return value.model_dump_json(
            indent=2,
        )
    if isinstance(value, (list, dict)):
        try:
            return json.dumps(
                pydantic_core.to_jsonable_python(value),
                indent=2,
            )
        except Exception:
            return json.dumps(
                {
                    "result": str(value),
                },
                indent=2,
            )
    return str(value)
