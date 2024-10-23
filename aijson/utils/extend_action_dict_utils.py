import os
import pydantic

from aijson.flow import Flow


def extend_actions_dict(aijson_document: str | None) -> dict[str, Flow]:
    aijson_documents: dict[str, Flow] = {}
    if aijson_document is None:
        return aijson_documents

    current_dir = os.path.abspath(os.path.dirname(aijson_document))
    current_dir = os.path.join(current_dir)

    def check_dir(dir: str, aijson_documents: dict[str, Flow]) -> dict[str, Flow]:
        for item in os.listdir(dir):
            full_path = os.path.join(dir, item)
            if os.path.isdir(full_path):
                continue
                # aijson_documents = check_dir(full_path, aijson_documents)
            elif os.path.isfile(full_path):
                if full_path.endswith(".ai.json") or full_path.endswith(".ai.yaml"):
                    try:
                        flow = Flow.from_file(full_path)
                        if flow.action_config.name is not None:
                            aijson_documents[full_path] = flow
                    except pydantic.ValidationError:
                        continue
        return aijson_documents

    return check_dir(current_dir, aijson_documents)
