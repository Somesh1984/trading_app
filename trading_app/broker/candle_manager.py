from __future__ import annotations

from queue import Empty, Queue
from typing import Any

from trading_app.models import LiveCandle, MarketTick


class CandleManager:
    """
    Candle manager.

    Responsibility:
    - raw tick messages lena
    - ticks ko timeframe bucket me rakhna
    - live candle maintain karna
    - closed candles queue me push karna

    Rule:
    - bucketing always time-based hogi
    - sirf startup ke waqt jo running bucket ho usko partial mark karenge
    - startup ke baad wali sab next buckets normal hongi
    """

    def __init__(self, *, timeframe_seconds: int, startup_epoch: int | None = None) -> None:
        self.timeframe_seconds = timeframe_seconds

        self.tick_queue: Queue[MarketTick] = Queue()
        self.closed_candle_queue: Queue[LiveCandle] = Queue()

        self._live_candles: dict[str, LiveCandle] = {}
        self._last_closed_bucket_by_symbol: dict[str, int] = {}

        self.startup_epoch = int(startup_epoch) if startup_epoch is not None else None
        self.startup_bucket_epoch = (
            self._get_bucket_epoch(self.startup_epoch)
            if self.startup_epoch is not None
            else None
        )
        self.startup_bucket_is_partial = (
            self.startup_epoch is not None
            and self.startup_bucket_epoch is not None
            and self.startup_epoch > self.startup_bucket_epoch
        )

    def put_tick_message(self, message: dict[str, Any]) -> None:
        """Raw websocket message ko MarketTick me convert karke queue me daalo."""
        symbol = str(message.get("symbol", "")).strip()
        if not symbol:
            return

        tick = MarketTick.from_message(message)
        if not tick.symbol or tick.exch_feed_time <= 0:
            return

        self.tick_queue.put(tick)

    def _get_bucket_epoch(self, epoch_seconds: int) -> int:
        return (epoch_seconds // self.timeframe_seconds) * self.timeframe_seconds

    def _is_partial_bucket(self, bucket_epoch: int) -> bool:
        """
        Sirf startup running bucket partial ho sakti hai.
        Baaki saari buckets normal.
        """
        if not self.startup_bucket_is_partial:
            return False

        return bucket_epoch == self.startup_bucket_epoch

    def _new_candle_from_tick(self, tick: MarketTick, bucket_epoch: int) -> LiveCandle:
        return LiveCandle(
            symbol=tick.symbol,
            bucket_epoch=bucket_epoch,
            timeframe_seconds=self.timeframe_seconds,
            open=tick.ltp,
            high=tick.ltp,
            low=tick.ltp,
            close=tick.ltp,
            volume=1,
            is_complete=not self._is_partial_bucket(bucket_epoch),
        )

    def _emit_closed_candle(self, candle: LiveCandle) -> None:
        """
        Duplicate closed candle queue me na jaye.
        Partial closed candle bhi queue me mat bhejo.
        """
        last_closed = self._last_closed_bucket_by_symbol.get(candle.symbol)
        if last_closed is not None and candle.bucket_epoch <= last_closed:
            print(
                "SKIP DUPLICATE CLOSED CANDLE:",
                candle.symbol,
                candle.bucket_epoch,
                flush=True,
            )
            return

        self._last_closed_bucket_by_symbol[candle.symbol] = candle.bucket_epoch

        if not candle.is_complete:
            print(
                "SKIP PARTIAL CLOSED CANDLE:",
                candle.symbol,
                candle.bucket_epoch,
                flush=True,
            )
            return

        self.closed_candle_queue.put(candle)

    def process_pending_ticks(self) -> None:
        """Tick queue drain karo aur candles build/update karo."""
        while True:
            try:
                tick = self.tick_queue.get_nowait()
            except Empty:
                break

            bucket_epoch = self._get_bucket_epoch(tick.exch_feed_time)
            current = self._live_candles.get(tick.symbol)

            if current is None:
                self._live_candles[tick.symbol] = self._new_candle_from_tick(
                    tick, bucket_epoch
                )
                continue

            if current.bucket_epoch == bucket_epoch:
                current.update(tick.ltp)
                continue

            self._emit_closed_candle(current)
            self._live_candles[tick.symbol] = self._new_candle_from_tick(
                tick, bucket_epoch
            )

    def pop_closed_candles(self) -> list[LiveCandle]:
        candles: list[LiveCandle] = []

        while True:
            try:
                candles.append(self.closed_candle_queue.get_nowait())
            except Empty:
                break

        return candles

    def get_live_candle(self, symbol: str) -> LiveCandle | None:
        return self._live_candles.get(symbol)











