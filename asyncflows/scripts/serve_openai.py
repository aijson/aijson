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
from asyncflows.utils.static_utils import (
    get_config_variables,
    get_target_outputs,
)


def create_openai_app(
    served_flow: AsyncFlows,
    input_var_name: str | None,
):
    app = FastAPI()

    async def stream_response(target_output: str, flow: AsyncFlows):
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
                "model": target_output,
                "choices": [{"delta": {"role": "assistant", "content": delta}}],
            }
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    async def run_response(target_output: str, flow: AsyncFlows):
        outputs = await flow.run(target_output)
        response = format_value(outputs)
        return {
            "id": "0",
            "object": "chat.completion",
            "created": time.time(),
            "model": target_output,
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

        target_output = request.model
        if target_output is None:
            target_output = final_flow.action_config.get_default_output()

        if request.stream:
            return StreamingResponse(
                stream_response(target_output, final_flow),
                media_type="application/x-ndjson",
            )
        return await run_response(target_output, final_flow)

    @app.get("/models")
    async def models():
        # TODO add description to each
        target_outputs = get_target_outputs(served_flow.action_config)
        return {
            "data": [
                {
                    "id": target_output,
                    "object": "model",
                    "created": 0,
                    "owned_by": "system",
                }
                for target_output in target_outputs
            ]
        }

    @app.get("/models/{model}")
    async def model(model: str):
        # TODO add description to each
        target_outputs = get_target_outputs(served_flow.action_config)
        if model not in target_outputs:
            return 404
        return {
            "id": model,
            "object": "model",
            "created": 0,
            "owned_by": "system",
        }

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


async def create_server(
    flow: AsyncFlows,
    input_var_name: str | None = None,
    host: str = "0.0.0.0",
    port: int | None = None,
):
    import uvicorn

    if port is None:
        port = find_open_port()
    app = create_openai_app(flow, input_var_name)

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        # log_level="info",
    )
    return uvicorn.Server(config)


async def run_server(
    flow: AsyncFlows,
    input_var_name: str | None = None,
    host: str = "0.0.0.0",
    port: int | None = None,
):
    server = await create_server(
        flow=flow,
        input_var_name=input_var_name,
        host=host,
        port=port,
    )

    url = f"http://{host}:{port}"
    print(f"Running OpenAI compatible API on: {url}")
    await server.serve()


if __name__ == "__main__":
    import argparse

    log = get_logger()

    parser = argparse.ArgumentParser()
    parser.add_argument("--flow", type=str, required=True)
    parser.add_argument("--port", type=int, required=False)
    parser.add_argument("--host", type=str, default="0.0.0.0")

    args, _ = parser.parse_known_args()

    _flow = AsyncFlows.from_file(args.flow)
    variables = get_config_variables(_flow.action_config)
    if len(variables) > 1:
        log.error(
            "Flow must have only one variable (which is filled by the input message)",
            variables=variables,
        )
        raise ValueError(
            "Flow must have only one variable (which is filled by the input message)"
        )
    if not variables:
        log.warning("No variable in flow, input messages will be ignored")
        input_var_name = None
    else:
        input_var_name = list(variables)[0]

    asyncio.run(
        run_server(
            _flow,
            host=args.host,
            port=args.port,
            input_var_name=input_var_name,
        )
    )
