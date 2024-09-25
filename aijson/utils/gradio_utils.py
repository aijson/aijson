import os
from typing import Sequence

from gradio.blocks import Block
from gradio.components import Component

os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

import gradio as gr  # noqa: E402


def single_shot(
    fn, inputs, outputs: Block | Sequence[Block], include_request: bool = False
):
    # lower values make the event trigger more times
    # while lagging even with 0.1 it might trigger multiple times
    timer = gr.Timer(0.1)

    def _(request: gr.Request, *args, **kwargs):
        if include_request:
            res = fn(request, *args, **kwargs)
        else:
            res = fn(*args, **kwargs)
        timer_update = gr.Timer(active=False)
        if isinstance(res, list):
            res += [timer_update]
        elif isinstance(res, dict) and all(isinstance(k, Component) for k in res):
            res[timer] = timer_update
        else:
            res = [res, timer_update]
        return res

    if isinstance(outputs, list):
        outputs += [timer]
    elif isinstance(outputs, set):
        outputs.add(timer)
    elif not isinstance(outputs, Sequence):
        outputs = [outputs, timer]
    else:
        raise RuntimeError(f"Unsupported outputs type: {type(outputs)}")
    timer.tick(_, inputs, outputs)

    return timer


def single_shot_async(
    fn, inputs, outputs: Block | Sequence[Block], include_request: bool = False
):
    # lower values make the event trigger more times
    # while lagging even with 0.1 it might trigger multiple times
    timer = gr.Timer(0.1)

    async def _(request: gr.Request, *args, **kwargs):
        if include_request:
            res = await fn(request, *args, **kwargs)
        else:
            res = await fn(*args, **kwargs)
        timer_update = gr.Timer(active=False)
        if isinstance(res, list):
            res += [timer_update]
        elif isinstance(res, dict) and all(isinstance(k, Component) for k in res):
            res[timer] = timer_update
        else:
            res = [res, timer_update]
        return res

    if isinstance(outputs, list):
        outputs += [timer]
    elif isinstance(outputs, set):
        outputs.add(timer)
    elif not isinstance(outputs, Sequence):
        outputs = [outputs, timer]
    else:
        raise RuntimeError(f"Unsupported outputs type: {type(outputs)}")
    timer.tick(_, inputs, outputs)

    return timer
