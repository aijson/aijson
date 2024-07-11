from typing import Any
import pydantic
import json


def json_block(text: str) -> str:
    return "```json\n" + text + "\n```"


def format_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, pydantic.BaseModel):
        return json_block(
            value.model_dump_json(
                indent=2,
            )
        )
    try:
        return json_block(
            json.dumps(
                value,
                indent=2,
            )
        )
    except json.JSONDecodeError:
        return str(value)
