import asyncio
import json
import socket
import time


from fastapi.responses import StreamingResponse
from fastapi import FastAPI, HTTPException

from asyncflows import AsyncFlows
from asyncflows.log_config import get_logger
from asyncflows.models.openai_server import OpenAIChatCompletionRequest
from asyncflows.utils.format_utils import format_value
from asyncflows.utils.rendering_utils import extract_root_var
from asyncflows.utils.static_utils import (
    get_variable_dependency_map,
)


def create_openai_app(
    served_flow: AsyncFlows,
    input_var_name: str | None,
    target_output: str | None,
):
    app = FastAPI()

    async def stream_response(request: OpenAIChatCompletionRequest, flow: AsyncFlows):
        previous_response = ""
        i = -1
        async for outputs in flow.stream(target_output):
            i += 1
            response = format_value(outputs)
            if len(response) <= len(previous_response):
                continue
            delta = response[len(previous_response) :]
            previous_response = response
            chunk = {
                "id": str(i),
                "object": "chat.completion.chunk",
                "created": time.time(),
                "model": request.model,
                "choices": [{"delta": {"role": "assistant", "content": delta}}],
            }
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    async def run_response(request: OpenAIChatCompletionRequest, flow: AsyncFlows):
        outputs = await flow.run(target_output)
        response = format_value(outputs)
        return {
            "id": "0",
            "object": "chat.completion",
            "created": time.time(),
            "model": request.model,
            "choices": [{"message": {"role": "assistant", "content": response}}],
        }

    @app.post("/chat/completions")
    async def chat_completions(request: OpenAIChatCompletionRequest):
        if not request.messages:
            raise HTTPException(status_code=400, detail="No messages provided")
        msg = request.messages[-1].content

        final_flow = served_flow
        if input_var_name:
            final_flow = final_flow.set_vars(**{input_var_name: msg})
        if request.stream:
            return StreamingResponse(
                stream_response(request, final_flow), media_type="application/x-ndjson"
            )
        return await run_response(request, final_flow)

    return app


def find_open_port(start_port: int | None = None, max_tries: int = 50) -> int:
    if start_port is None:
        start_port = 27215
    retries = 0
    while retries < max_tries:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", start_port))
                s.listen(1)
                return s.getsockname()[1]
        except OSError:
            start_port += 1
            retries += 1
    raise RuntimeError("Failed to find open port")


async def run_server(
    flow: AsyncFlows,
    input_var_name: str | None = None,
    host: str = "0.0.0.0",
    port: int | None = None,
    target_output: str | None = None,
):
    import uvicorn

    if port is None:
        port = find_open_port()
    app = create_openai_app(flow, input_var_name, target_output)

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        # log_level="info",
    )
    server = uvicorn.Server(config)

    url = f"http://{host}:{port}"
    print(f"Running OpenAI compatible API on: {url}")
    await server.serve()


if __name__ == "__main__":
    import argparse

    log = get_logger()

    parser = argparse.ArgumentParser()
    parser.add_argument("--flow", type=str, required=True)
    parser.add_argument("--target-output", type=str, required=False)
    parser.add_argument("--port", type=int, required=False)
    parser.add_argument("--host", type=str, default="0.0.0.0")

    args, _ = parser.parse_known_args()

    flow = AsyncFlows.from_file(args.flow)
    dependency_map = get_variable_dependency_map(flow.action_config)
    target_output = args.target_output or flow.action_config.get_default_output()
    root_dependency = extract_root_var(target_output)

    variables = dependency_map[root_dependency]
    if len(variables) > 1:
        log.error(
            "Flow target output must have only one input variable (which is filled by the input message)",
            target_output=target_output,
            variables=variables,
        )
        raise ValueError(
            "Flow target output must have only one input variable (which is filled by the input message)"
        )
    if not variables:
        log.warning("No input variable specified, input messages will be ignored")
        input_var_name = None
    else:
        input_var_name = list(variables)[0]

    asyncio.run(
        run_server(
            flow,
            host=args.host,
            port=args.port,
            input_var_name=input_var_name,
            target_output=args.target_output,
        )
    )