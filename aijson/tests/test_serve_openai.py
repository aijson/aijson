import asyncio
from unittest.mock import ANY

import openai
import pytest

from aijson import Flow
from aijson.scripts.serve_openai import run_server, find_open_port
from aijson.utils.static_utils import get_target_outputs


@pytest.fixture
async def open_port():
    return find_open_port()


@pytest.fixture
def flow(testing_actions):
    return Flow(testing_actions)


@pytest.fixture(autouse=True)
async def serve(open_port, flow):
    task = asyncio.create_task(run_server(flow, port=open_port))
    yield
    task.cancel()


@pytest.fixture
async def client(open_port) -> openai.AsyncClient:
    import openai

    return openai.AsyncOpenAI(base_url=f"http://localhost:{open_port}", api_key="123")
    # return openai.AsyncOpenAI()


async def test_run(client):
    response = await client.chat.completions.create(
        messages=[{"role": "user", "content": "stuff about something"}],
        model="second_sum.result",
    )

    assert response.model_dump() == {
        "id": "0",
        "object": "chat.completion",
        "created": ANY,
        "model": "second_sum.result",
        "choices": [
            {
                "finish_reason": None,
                "index": None,
                "logprobs": None,
                "message": {
                    "role": "assistant",
                    "content": "7",
                    "tool_calls": None,
                    "function_call": None,
                    "refusal": None,
                },
            },
        ],
        "service_tier": None,
        "system_fingerprint": None,
        "usage": None,
    }


async def test_run_model_none(client):
    response = await client.chat.completions.create(
        messages=[{"role": "user", "content": "stuff about something"}],
        model=None,  # type: ignore
    )

    assert response.model_dump() == {
        "id": "0",
        "object": "chat.completion",
        "created": ANY,
        "model": "first_sum.result",
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
                    "refusal": None,
                },
            },
        ],
        "service_tier": None,
        "system_fingerprint": None,
        "usage": None,
    }


async def test_stream(client):
    # TODO test against a streaming action
    response = await client.chat.completions.create(
        messages=[{"role": "user", "content": "stuff about something"}],
        model="first_sum.result",
        stream=True,
    )

    result_came_through = False
    async for partial in response:
        result_came_through = True
        assert partial.model_dump() == {
            "id": "0",
            "object": "chat.completion.chunk",
            "created": ANY,
            "model": "first_sum.result",
            "choices": [
                {
                    "delta": {
                        "role": "assistant",
                        "content": "3",
                        "tool_calls": None,
                        "function_call": None,
                        "refusal": None,
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


async def test_models(client, flow):
    response = await client.models.list()
    legal_target_outputs = get_target_outputs(flow.action_config)
    assert legal_target_outputs == [m.id for m in response.data]


async def test_model(client):
    response = await client.models.retrieve("first_sum.result")
    assert response.id == "first_sum.result"
