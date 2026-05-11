from __future__ import annotations

import threading
import time
from queue import Empty, Queue

from trading_app.broker.candle_manager import CandleManager
from trading_app.broker.websocket import RawMessage
from trading_app.models import LiveCandle


class CandleRunner:
    """
    Background candle processing runner.

    Responsibility:
    - raw tick queue consume karna
    - multiple candle managers ko same tick dena
    - per-timeframe closed candle queues maintain karna
    """

    def __init__(
        self,
        *,
        tick_queue: Queue[RawMessage],
        candle_managers: dict[str, CandleManager],
        poll_interval: float = 0.05,
    ) -> None:
        self.tick_queue = tick_queue
        self.candle_managers = candle_managers
        self.poll_interval = poll_interval

        self.closed_candle_queues: dict[str, Queue[LiveCandle]] = {
            name: Queue() for name in candle_managers
        }

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            processed_any = self._drain_tick_queue()

            self._close_due_candles()
            self._drain_closed_candles()

            if not processed_any:
                time.sleep(self.poll_interval)

    def _drain_tick_queue(self) -> bool:
        processed_any = False

        while True:
            try:
                message = self.tick_queue.get_nowait()
            except Empty:
                break

            processed_any = True

            for manager in self.candle_managers.values():
                manager.process_tick_message(message)

        return processed_any

    def _drain_closed_candles(self) -> None:
        for name, manager in self.candle_managers.items():
            candles = manager.pop_closed_candles()

            for candle in candles:
                self.closed_candle_queues[name].put(candle)

    def _close_due_candles(self) -> None:
        now_epoch = int(time.time())

        for manager in self.candle_managers.values():
            manager.close_due_candles(now_epoch)

    def start(self) -> None:
        if self.is_alive():
            return

        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run,
            name="CandleRunner",
            daemon=True,
        )

        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

        try:
            if (
                self._thread is not None
                and self._thread is not threading.current_thread()
            ):
                self._thread.join(timeout=2)

        finally:
            self._thread = None

    def is_alive(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
        )

    def pop_closed_candles(
        self,
        name: str,
    ) -> list[LiveCandle]:
        queue = self.closed_candle_queues[name]

        candles: list[LiveCandle] = []

        while True:
            try:
                candles.append(queue.get_nowait())

            except Empty:
                break

        return candles
