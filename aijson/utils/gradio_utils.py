import os

os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

import gradio as gr  # noqa: E402


def single_shot(fn, inputs, outputs):
    # lower values make the event trigger more times
    # while lagging even with 0.1 it might trigger multiple times
    timer = gr.Timer(0.1)

    def _(*args, **kwargs):
        res = fn(*args, **kwargs)
        timer_update = gr.Timer(active=False)
        if isinstance(res, list):
            res += [timer_update]
        elif isinstance(res, dict):
            res[timer] = timer_update
        else:
            res = [res, timer_update]
        return res

    if isinstance(outputs, list):
        outputs += [timer]
    elif isinstance(outputs, set):
        outputs.add(timer)
    else:
        outputs = [outputs, timer]
    timer.tick(_, inputs, outputs)

    return timer
