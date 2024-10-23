import os
import re

import yaml

from aijson.models.config.flow import ActionConfig, build_action_config


def get_config_model() -> type[ActionConfig]:
    # TODO cache this so it only rebuilds when the action registry changes
    return build_action_config()


def load_config_text(config_text: str) -> ActionConfig:
    config_model = get_config_model()
    return config_model.model_validate(yaml.safe_load(config_text))


def load_config_file(
    filename: str, config_model: type[ActionConfig] | None = None
) -> ActionConfig:
    # LSP on windows passes in /c:/path/to/file.yaml paths, so we need to strip the leading /
    if re.match(r"/[a-zA-Z]:/", filename):
        filename = filename.lstrip("/")

    # when you run flows, you shouldn't run them with config_model=ActionConfig, else it won't know how to coerce fields
    # TODO load it non-strict before loading it for real, to show more informative errors (eg action is not installed)
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Could not find {filename}")

    if config_model is None:
        config_model = get_config_model()

    with open(filename, "r") as f:
        return config_model.model_validate(yaml.safe_load(f))
