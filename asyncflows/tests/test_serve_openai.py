import asyncio
from unittest.mock import ANY

import pytest

from asyncflows import AsyncFlows
from asyncflows.scripts.serve_openai import run_server, find_open_port


@pytest.fixture
async def open_port():
    return find_open_port()


@pytest.fixture
async def serve(testing_actions, open_port):
    flow = AsyncFlows(testing_actions)
    task = asyncio.create_task(
        run_server(flow, port=open_port, target_output="first_sum.result")
    )
    yield
    task.cancel()


async def test_run(serve, open_port):
    import openai

    ai = openai.AsyncOpenAI(base_url=f"http://localhost:{open_port}", api_key="123")

    response = await ai.chat.completions.create(
        messages=[{"role": "user", "content": "stuff about something"}],
        model="gpt-4o",
    )

    assert response.model_dump() == {
        "id": "0",
        "object": "chat.completion",
        "created": ANY,
        "model": "gpt-4o",
        "choices": [
            {
                "finish_reason": None,
                "index": None,
                "logprobs": None,
                "message": {
                    "role": "assistant",
                    "content": "3",
                    "tool_calls": None,
                    "function_call": None,
                },
            },
        ],
        "service_tier": None,
        "system_fingerprint": None,
        "usage": None,
    }


async def test_stream(serve, open_port):
    import openai

    ai = openai.AsyncOpenAI(base_url=f"http://localhost:{open_port}", api_key="123")
    response = await ai.chat.completions.create(
        messages=[{"role": "user", "content": "stuff about something"}],
        model="gpt-4o",
        stream=True,
    )

    result_came_through = False
    async for partial in response:
        result_came_through = True
        assert partial.model_dump() == {
            "id": "0",
            "object": "chat.completion.chunk",
            "created": ANY,
            "model": "gpt-4o",
            "choices": [
                {
                    "delta": {
                        "role": "assistant",
                        "content": "3",
                        "tool_calls": None,
                        "function_call": None,
                    },
                    "finish_reason": None,
                    "index": None,
                    "logprobs": None,
                },
            ],
            "service_tier": None,
            "system_fingerprint": None,
            "usage": None,
        }
    assert result_came_through
