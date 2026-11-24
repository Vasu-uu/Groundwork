"""Run async jobs with a concurrency limit, failing fast on the first error."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import TypeVar

A = TypeVar("A")
R = TypeVar("R")


async def map_bounded(fn: Callable[[A], Awaitable[R]], items: Iterable[A], limit: int) -> list[R]:
    """`[await fn(x) for x in items]`, at most `limit` at a time, results in input order.

    If one job raises (e.g. the model server went down), the others are
    cancelled and that first exception is raised as-is (not as an ExceptionGroup).
    """
    gate = asyncio.Semaphore(limit)
    stop = asyncio.Event()

    async def run(item: A) -> R:
        async with gate:
            if stop.is_set():  # an earlier job failed: do not start new work
                raise asyncio.CancelledError
            try:
                return await fn(item)
            except Exception:
                stop.set()
                raise

    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(run(x)) for x in items]
    except ExceptionGroup as group_error:
        raise group_error.exceptions[0] from None
    return [t.result() for t in tasks]
