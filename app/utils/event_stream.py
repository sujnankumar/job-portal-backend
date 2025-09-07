import asyncio
import json
from typing import Any, Dict, Set

# Simple in-memory broadcaster for Server-Sent Events (SSE)
# Not suitable for multi-process deployments without a shared broker.

_subscribers: Set[asyncio.Queue] = set()
_lock = asyncio.Lock()


async def subscribe() -> asyncio.Queue:
    """Register a new subscriber and return its queue."""
    q: asyncio.Queue = asyncio.Queue()
    async with _lock:
        _subscribers.add(q)
    return q


async def unsubscribe(q: asyncio.Queue) -> None:
    """Remove a subscriber and drain its queue."""
    async with _lock:
        _subscribers.discard(q)
    try:
        while not q.empty():
            q.get_nowait()
            q.task_done()
    except Exception:
        pass


async def publish(event: Dict[str, Any]) -> None:
    """Publish an event to all subscribers."""
    # Copy current subscribers snapshot to avoid holding lock while putting
    async with _lock:
        targets = list(_subscribers)
    if not targets:
        return
    data = json.dumps(event, default=str)
    for q in targets:
        try:
            q.put_nowait(data)
        except Exception:
            # If a queue is full/broken, drop the message and continue
            pass


async def sse_event_generator(q: asyncio.Queue, heartbeat_interval: float = 15.0):
    """Yield SSE-formatted messages from a queue with periodic heartbeats."""
    try:
        while True:
            try:
                # Wait for next message or timeout for heartbeat
                data = await asyncio.wait_for(q.get(), timeout=heartbeat_interval)
                yield f"data: {data}\n\n"
                q.task_done()
            except asyncio.TimeoutError:
                # SSE comment line as heartbeat
                yield ": keep-alive\n\n"
    finally:
        await unsubscribe(q)
