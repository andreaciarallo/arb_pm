"""
Async write queue for SQLite paper trade logging.

Decouples paper trade simulation from SQLite writes using asyncio.Queue.
The main scan loop calls enqueue() without blocking. A background worker
coroutine drains the queue and performs synchronous SQLite inserts.

Queue bounded at 1000 items. If full, the paper trade is dropped with a
warning log — detection continues uninterrupted.

Pattern copied from bot.storage.writer.AsyncWriter (Phase 2).
"""
import asyncio

from loguru import logger

from bot.storage.schema import insert_paper_trade

_MAX_QUEUE_SIZE = 1000


class PaperTradeWriter:
    """
    Async write queue for SQLite paper trade logging.

    Usage:
        writer = PaperTradeWriter(conn)
        writer.start()
        writer.enqueue(paper_trade)  # non-blocking
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

    def enqueue(self, paper_trade) -> None:
        """
        Enqueue a paper trade for writing. Non-blocking.

        If the queue is full, the paper trade is dropped with a warning.
        The detection loop is never blocked.
        """
        try:
            self._queue.put_nowait(paper_trade)
        except asyncio.QueueFull:
            logger.warning(
                "Paper trade write queue full (1000 items) — paper trade dropped. "
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
                paper_trade = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                try:
                    insert_paper_trade(self._conn, paper_trade)
                except Exception as e:
                    logger.error(f"SQLite paper trade insert failed: {e}")
                finally:
                    self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
