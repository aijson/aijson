import argparse
import json
import os

from pydantic import TypeAdapter

from aijson.models.config.flow import (
    build_hinted_action_config,
)
from aijson.utils.action_utils import (
    build_link_literal,
    get_actions_dict,
    import_custom_actions,
)


def _build_aijson_schema(
    action_names: list[str],
    include_paths: bool,
    strict: bool,
    config_filename: str | None = None,
    link_hint_literal_name: str = "__LinkHintLiteral",
):
    if config_filename:
        link_hint_literal = build_link_literal(
            config_filename=config_filename,
            strict=strict,
            include_paths=include_paths,
        )
    else:
        link_hint_literal = None

    HintedActionConfig = build_hinted_action_config(
        action_names=action_names,
        links=link_hint_literal,
        vars_=None,
        include_paths=include_paths,
        strict=strict,
    )
    workflow_schema = HintedActionConfig.model_json_schema()

    if link_hint_literal is not None:
        definitions = workflow_schema["$defs"]
        if link_hint_literal_name in definitions:
            raise ValueError(
                f"Link hint literal name `{link_hint_literal_name}` already exists in definitions"
            )
        definitions[link_hint_literal_name] = TypeAdapter(
            link_hint_literal
        ).json_schema()

    return workflow_schema


def _build_and_save_aijson_schema(
    action_names: list[str],
    output_file: str,
    include_paths: bool,
    strict: bool,
    config_filename: str | None = None,
):
    workflow_schema = _build_aijson_schema(
        action_names=action_names,
        include_paths=include_paths,
        strict=strict,
        config_filename=config_filename,
    )
    os.makedirs("schemas", exist_ok=True)
    with open(os.path.join("schemas", output_file), "w") as f:
        json.dump(workflow_schema, f, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--flow",
        default="",
        help="Path to flow for populating link fields with",
    )
    parser.add_argument(
        "--discover-actions",
        action="store_true",
        help="Recursively discover and import actions defined in the current working directory",
    )

    args = parser.parse_args()

    if args.discover_actions:
        import_custom_actions(".")

    if args.flow:
        action_names = list(get_actions_dict().keys())

        schema = _build_aijson_schema(
            action_names=action_names,
            config_filename=args.flow,
            strict=True,
            include_paths=True,
        )
        # print to stdout for backwards compat
        json_schema_dump = json.dumps(schema, indent=2)
        print(json_schema_dump)
        # print to fd `3` for functionality even if errors are thrown
        try:
            buffer_size = 512
            with os.fdopen(3, "w") as fd:
                # chunk it
                for i in range(0, len(json_schema_dump), buffer_size):
                    fd.write(json_schema_dump[i : i + buffer_size])
        except Exception:
            pass
    else:
        action_names = list(get_actions_dict().keys())

        # TODO assert tests not imported before this line
        import aijson.tests.resources.testing_actions  # noqa

        testing_action_names = list(get_actions_dict().keys())

        # build default action and test action schemas
        _build_and_save_aijson_schema(
            action_names=action_names,
            output_file="aijson_schema.json",
            strict=False,
            include_paths=False,
        )

        _build_and_save_aijson_schema(
            action_names=testing_action_names,
            output_file="testing_aijson_schema.json",
            strict=False,
            include_paths=False,
        )
