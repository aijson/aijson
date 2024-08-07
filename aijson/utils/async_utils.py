import asyncio
import functools
import sys
import time
from asyncio import CancelledError, ensure_future
from typing import TypeVar, AsyncIterator, Awaitable, Sequence

import sentry_sdk
import structlog

from aijson.utils.sentinel_utils import Sentinel, SentinelType

T = TypeVar("T")
IdType = TypeVar("IdType")
OutputType = TypeVar("OutputType")


class LagMonitor:
    def __init__(
        self,
        log: structlog.stdlib.BoundLogger,
        interval: float = 0.5,
        lag_threshold: float = 0.3,
    ):
        self.log = log
        self.interval = interval
        self.lag_threshold = lag_threshold
        self.task = None

    def start(self):
        loop = asyncio.get_running_loop()
        self.task = loop.create_task(self._loop_monitor(loop))

    def stop(self):
        if self.task is None:
            raise RuntimeError("LagMonitor not started")
        self.task.cancel()

    async def _loop_monitor(self, loop: asyncio.AbstractEventLoop):
        while loop.is_running():
            start = loop.time()

            await asyncio.sleep(self.interval)

            time_elapsed = loop.time() - start
            lag = time_elapsed - self.interval
            if lag > self.lag_threshold:
                self.log.warning(
                    "Event loop lagging",
                    lag=lag,
                )


async def merge_iterators(
    log: structlog.stdlib.BoundLogger,
    ids: Sequence[IdType],
    coros: list[AsyncIterator[OutputType]],
    raise_: bool = False,
    report_finished: bool = False,
    suppress_exception_logging: bool = False,
) -> AsyncIterator[tuple[IdType, OutputType | SentinelType | Exception | None]]:
    async def worker(
        aiter: AsyncIterator[OutputType], iterator_id: IdType, queue: asyncio.Queue
    ):
        try:
            async for value in aiter:
                await queue.put((False, (iterator_id, value)))
        except Exception as exc:
            # If an exception occurs, send it through the queue
            await queue.put((True, (iterator_id, exc)))
        finally:
            # Notify the main loop that this coroutine is done
            await queue.put((None, iterator_id))

    queue = asyncio.Queue()
    workers = []  # List to keep track of worker tasks.

    try:
        for id_, aiter in zip(ids, coros):
            worker_task = asyncio.create_task(worker(aiter, id_, queue))
            workers.append(worker_task)

        remaining_workers = len(workers)
        while remaining_workers > 0:
            result = await queue.get()
            execution_status, args = result
            if execution_status is None:
                id_ = args
                # One coroutine has finished.
                remaining_workers -= 1
                if report_finished:
                    yield id_, Sentinel
                continue

            # A result or an exception was received.
            exception_raised, (id_, value_or_exc) = result
            if exception_raised:
                if not suppress_exception_logging:
                    log.exception(
                        "Exception raised in worker",
                        id=id_,
                        exc_info=value_or_exc,
                    )
                    sentry_sdk.capture_exception(value_or_exc)
                # yield id_, None
                # If any exception is received, cancel all workers and raise the exception.
                # for worker_task in workers:
                #     worker_task.cancel()
                # await asyncio.gather(*workers, return_exceptions=True)
                # raise value_or_exc
            else:
                # Yield the result.
                try:
                    yield id_, value_or_exc
                except GeneratorExit:
                    log.warning(
                        "Generator exited",
                        id=id_,
                    )
                    # TODO maybe this should always raise?
                    if raise_:
                        raise
                except CancelledError:
                    log.warning(
                        "Generator cancelled",
                        id=id_,
                    )
                    if raise_:
                        raise
    finally:
        for worker_task in workers:
            worker_task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


# incompatible with python3.12, and not used anywhere at the moment
# async def cancel_generators(agenerators: list[AsyncGenerator]):
#     tasks = []
#     for coro in agenerators:
#         task = Task(coro.__anext__())
#         tasks.append(task)
#         task.cancel()
#
#     await asyncio.gather(*tasks, return_exceptions=True)


async def iterator_to_coro(async_iterator: AsyncIterator[T | None]) -> T | None:
    output = None
    async for output in async_iterator:
        pass
    return output


class Timer:
    def __init__(self):
        self.blocking_time = 0
        self.blocking_start_time = None
        self.wall_start_time = 0
        self.wall_end_time = 0

    def start(self):
        now = time.monotonic()
        if not self.wall_start_time:
            self.wall_start_time = now
        self.blocking_start_time = time.perf_counter()

    def end(self):
        self.wall_end_time = time.monotonic()
        if self.blocking_start_time is None:
            return
        end_perf_counter = time.perf_counter()
        self.blocking_time += end_perf_counter - self.blocking_start_time
        self.blocking_start_time = None

    @property
    def wall_time(self):
        # if self.wall_end_time is None or self.wall_start_time is None:
        #     raise RuntimeError("Timer not yet started")
        return self.wall_end_time - self.wall_start_time


async def _cancel_and_wait(fut, loop):
    """Cancel the *fut* future or task and wait until it completes."""

    waiter = loop.create_future()
    cb = functools.partial(_release_waiter, waiter)
    fut.add_done_callback(cb)

    try:
        fut.cancel()
        # We cannot wait on *fut* directly to make
        # sure _cancel_and_wait itself is reliably cancellable.
        await waiter
    finally:
        fut.remove_done_callback(cb)


def _release_waiter(waiter, *args):
    if not waiter.done():
        waiter.set_result(None)


async def _old_wait_for(
    fut: asyncio.Future,
    timeout: float,
):
    """
    Plucked and amended from python3.11 `asyncio.wait_for`

    Wait for the single Future or coroutine to complete, with timeout.

    Coroutine will be wrapped in Task.

    Returns result of the Future or coroutine.  When a timeout occurs,
    it cancels the task and raises TimeoutError.  To avoid the task
    cancellation, wrap it in shield().

    If the wait is cancelled, the task is also cancelled.

    This function is a coroutine.
    """
    loop = asyncio.get_running_loop()

    waiter = loop.create_future()
    timeout_handle = loop.call_later(timeout, _release_waiter, waiter)
    cb = functools.partial(_release_waiter, waiter)

    fut = ensure_future(fut, loop=loop)
    fut.add_done_callback(cb)

    try:
        # wait until the future completes or the timeout
        try:
            await waiter
        except asyncio.CancelledError:
            if fut.done():
                return fut.result()
            else:
                fut.remove_done_callback(cb)
                # We must ensure that the task is not running
                # after wait_for() returns.
                # See https://bugs.python.org/issue32751
                await _cancel_and_wait(fut, loop=loop)
                raise

        if fut.done():
            return fut.result()
        else:
            fut.remove_done_callback(cb)
            # We must ensure that the task is not running
            # after wait_for() returns.
            # See https://bugs.python.org/issue32751
            await _cancel_and_wait(fut, loop=loop)
            # In case task cancellation failed with some
            # exception, we should re-raise it
            # See https://bugs.python.org/issue40607
            try:
                return fut.result()
            except asyncio.CancelledError as exc:
                raise asyncio.TimeoutError() from exc
    finally:
        timeout_handle.cancel()


async def _await_with_timeout(
    fut: asyncio.Future,
    timeout: float,
):
    # python 3.12 rewrote `asyncio.wait_for`
    if sys.version_info.minor >= 12:
        # TODO write a callback-based wait for with `asyncio.timeouts`,
        #  it'll be more efficient
        return await _old_wait_for(fut, timeout=timeout)
    return await asyncio.wait_for(fut, timeout=timeout)

    # for some reason these futures don't seem to be futures until
    # they're triggered by `call_later`, so we need to create a separate future,
    # add a callback to the original one, and wait for it to finish

    # we can use timeouts package in python>=3.11


async def measure_coro(
    log: structlog.stdlib.BoundLogger,
    f: Awaitable[T],
    timer: Timer,
    timeout: float = 180,
) -> T:
    coro_wrapper = f.__await__()
    arg = None
    exc = None
    fut = None
    first_run = True

    while True:
        try:
            if first_run:
                first_run = False
            elif fut is None:
                log.debug(
                    "Coroutine returned None",
                    arg=arg,
                )
                try:
                    await asyncio.sleep(0)
                except asyncio.CancelledError:
                    log.debug(
                        "Subcoroutine cancelled during bare yield",
                        arg=arg,
                    )
            else:
                try:
                    arg = await _await_with_timeout(fut, timeout=timeout)
                    log.debug(
                        "Subcoroutine finished",
                        # result=arg,
                    )
                except asyncio.TimeoutError as e:
                    log.error(
                        "Subcoroutine timed out",
                        arg=arg,
                        exc_info=e,
                    )
                    raise
                except asyncio.CancelledError:
                    log.debug(
                        "Subcoroutine cancelled during wait",
                        arg=arg,
                        # exc_info=e,
                    )
                    # fut.set_exception(e)
                except Exception as e:
                    log.debug(
                        "Subcoroutine raised exception",
                        arg=arg,
                        # exc_info=e,
                    )
                    exc = e
            timer.start()
            if exc is not None:
                fut = coro_wrapper.throw(exc)
                exc = None
            else:
                fut = coro_wrapper.send(arg)
        except StopIteration as e:
            return e.value
        finally:
            timer.end()
            arg = None


async def measure_async_iterator(
    log: structlog.stdlib.BoundLogger,
    f: AsyncIterator[T],
    timer: Timer,
    timeout: float = 180,
) -> AsyncIterator[T]:
    iter_wrapper = f.__aiter__()
    while True:
        try:
            yield await measure_coro(
                log,
                iter_wrapper.__anext__(),
                timer,
                timeout,
            )
        except StopAsyncIteration:
            break
        # except Exception:
        #     raise
    # iter_wrapper = f.__aiter__()
    # out = sentinel = object()
    # while True:
    #     try:
    #         if out is not sentinel:
    #             # it still thinks this is an `object()` and not a `T`
    #             yield out  # type: ignore
    #         # timer.start()
    #         out = await measure_coro(
    #             log,
    #             iter_wrapper.__anext__(),
    #             timer,
    #         )
    #     except StopAsyncIteration:
    #         break
    #     except Exception:
    #         raise
    # finally:
    #     timer.end()
    #     timer.start()
    #     try:
    #         # TODO this does not measure blocking time properly;
    #         #  it could also yield within f to other coroutines and it would get counted as part of f's blocking time
    #         async for out in f:
    #             timer.end()
    #             yield out
    #             timer.start()
    #     except Exception:
    #         # fut.set_exception(e)
    #         # break
    #         raise
    #     finally:
    #         timer.end()

    # async def wrapper(*args, **kwargs):
    #     async_gen = f(*args, **kwargs).__aiter__()
    #
    #     while True:
    #         timer.start()
    #         # Attempt to yield the next value from the async generator
    #         try:
    #             yield await async_gen.asend(None)
    #         except StopAsyncIteration:
    #             # If no more values are available, break the loop
    #             break
    #         except Exception as e:
    #             # If an exception occurs, send it back to the async generator
    #             yield async_gen.athrow(e)
    #         finally:
    #             timer.end()
    #
    # return wrapper

    # write iterator in same style as  measure_coro

    # async_gen = f.__aiter__()
    # arg = None
    #
    # while True:
    #     try:
    #         timer.start()
    #         fut = await async_gen.asend(arg)
    #         if fut is None:
    #             log.debug(
    #                 "Coroutine returned None",
    #                 async_gen=async_gen,
    #                 arg=arg,
    #             )
    #             await asyncio.sleep(0)
    #         else:
    #             arg = await asyncio.wait([fut], timeout=120)
    #     except StopIteration as e:
    #         return e.value
    #     except Exception as e:
    #         # fut.set_exception(e)
    #         # break
    #         raise
    #     finally:
    #         timer.end()
