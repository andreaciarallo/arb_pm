"""
Async write queue for SQLite opportunity logging.

Decouples opportunity detection from SQLite writes using asyncio.Queue.
The main scan loop calls enqueue() without blocking. A background worker
coroutine drains the queue and performs synchronous SQLite inserts.

Queue bounded at 1000 items. If full, the opportunity is dropped with a
warning log — detection continues uninterrupted (D-specifics).
"""
import asyncio

from loguru import logger

from bot.storage.schema import insert_opportunity

_MAX_QUEUE_SIZE = 1000


class AsyncWriter:
    """
    Async write queue for SQLite opportunity logging.

    Usage:
        writer = AsyncWriter(conn)
        writer.start()
        writer.enqueue(opportunity)  # non-blocking
        await writer.flush()         # drain queue (for shutdown/test)
        await writer.stop()          # graceful shutdown
    """

    def __init__(self, conn) -> None:
        self._conn = conn
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE_SIZE)
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        """Start the background writer coroutine."""
        self._running = True
        self._task = asyncio.create_task(self._worker())

    def enqueue(self, opportunity) -> None:
        """
        Enqueue an opportunity for writing. Non-blocking.

        If the queue is full, the opportunity is dropped with a warning.
        The detection loop is never blocked.
        """
        try:
            self._queue.put_nowait(opportunity)
        except asyncio.QueueFull:
            logger.warning(
                "SQLite write queue full (1000 items) — opportunity dropped. "
                "Consider increasing scan_interval_seconds or checking disk I/O."
            )

    async def flush(self) -> None:
        """Wait until all queued items have been written."""
        await self._queue.join()

    async def stop(self) -> None:
        """Drain the queue and stop the background worker."""
        self._running = False
        await self.flush()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _worker(self) -> None:
        """Background coroutine that drains the queue into SQLite."""
        while self._running or not self._queue.empty():
            try:
                opportunity = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                try:
                    insert_opportunity(self._conn, opportunity)
                except Exception as e:
                    logger.error(f"SQLite insert failed: {e}")
                finally:
                    self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
