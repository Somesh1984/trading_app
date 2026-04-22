# from __future__ import annotations

# from queue import Queue
# from typing import Any

# from trading_app.models import LiveCandle, MarketTick


# class CandleManager:
#     """
#     Candle manager.

#     - raw tick messages leta hai
#     - timeframe based bucket banata hai
#     - startup running bucket ko partial mark karta hai
#     - closed candles queue me deta hai
#     """

#     def __init__(self, *, timeframe_seconds: int, startup_epoch: int | None = None) -> None:
#         self.timeframe_seconds = timeframe_seconds
#         self.closed_candle_queue: Queue[LiveCandle] = Queue()

#         self._live_candles: dict[str, LiveCandle] = {}
#         self._last_closed_bucket_by_symbol: dict[str, int] = {}

#         self.startup_epoch = int(startup_epoch) if startup_epoch is not None else None
#         self.startup_bucket_epoch = (
#             self._get_bucket_epoch(self.startup_epoch)
#             if self.startup_epoch is not None
#             else None
#         )
#         self.startup_bucket_is_partial = (
#             self.startup_epoch is not None
#             and self.startup_bucket_epoch is not None
#             and self.startup_epoch > self.startup_bucket_epoch
#         )

#     def _get_bucket_epoch(self, epoch_seconds: int) -> int:
#         return (epoch_seconds // self.timeframe_seconds) * self.timeframe_seconds

#     def _is_partial_bucket(self, bucket_epoch: int) -> bool:
#         if not self.startup_bucket_is_partial:
#             return False
#         return bucket_epoch == self.startup_bucket_epoch

#     def _new_candle_from_tick(self, tick: MarketTick, bucket_epoch: int) -> LiveCandle:
#         return LiveCandle(
#             symbol=tick.symbol,
#             bucket_epoch=bucket_epoch,
#             timeframe_seconds=self.timeframe_seconds,
#             open=tick.ltp,
#             high=tick.ltp,
#             low=tick.ltp,
#             close=tick.ltp,
#             volume=1,
#             is_complete=not self._is_partial_bucket(bucket_epoch),
#         )

#     def _emit_closed_candle(self, candle: LiveCandle) -> None:
#         last_closed = self._last_closed_bucket_by_symbol.get(candle.symbol)
#         if last_closed is not None and candle.bucket_epoch <= last_closed:
#             print(
#                 "SKIP DUPLICATE CLOSED CANDLE:",
#                 candle.symbol,
#                 candle.bucket_epoch,
#                 self.timeframe_seconds,
#                 flush=True,
#             )
#             return

#         self._last_closed_bucket_by_symbol[candle.symbol] = candle.bucket_epoch

#         if not candle.is_complete:
#             print(
#                 "SKIP PARTIAL CLOSED CANDLE:",
#                 candle.symbol,
#                 candle.bucket_epoch,
#                 self.timeframe_seconds,
#                 flush=True,
#             )
#             return

#         self.closed_candle_queue.put(candle)

#     def process_tick_message(self, message: dict[str, Any]) -> None:
#         symbol = str(message.get("symbol", "")).strip()
#         if not symbol:
#             return

#         tick = MarketTick.from_message(message)
#         if not tick.symbol or tick.exch_feed_time <= 0:
#             return

#         bucket_epoch = self._get_bucket_epoch(tick.exch_feed_time)
#         current = self._live_candles.get(tick.symbol)

#         if current is None:
#             self._live_candles[tick.symbol] = self._new_candle_from_tick(
#                 tick, bucket_epoch
#             )
#             return

#         if current.bucket_epoch == bucket_epoch:
#             current.update(tick.ltp)
#             return

#         self._emit_closed_candle(current)
#         self._live_candles[tick.symbol] = self._new_candle_from_tick(
#             tick, bucket_epoch
#         )

#     def pop_closed_candles(self) -> list[LiveCandle]:
#         candles: list[LiveCandle] = []

#         while not self.closed_candle_queue.empty():
#             candles.append(self.closed_candle_queue.get())

#         return candles

#     def get_live_candle(self, symbol: str) -> LiveCandle | None:
#         return self._live_candles.get(symbol)

#     def seed_closed_candle(self, candle: LiveCandle) -> None:
#         if candle.timeframe_seconds != self.timeframe_seconds:
#             raise ValueError(
#                 f"Timeframe mismatch. manager={self.timeframe_seconds}, candle={candle.timeframe_seconds}"
#             )

#         if not candle.is_complete:
#             return

#         last_closed = self._last_closed_bucket_by_symbol.get(candle.symbol)
#         if last_closed is not None and candle.bucket_epoch <= last_closed:
#             return

#         self._last_closed_bucket_by_symbol[candle.symbol] = candle.bucket_epoch
#         self.closed_candle_queue.put(candle)

#     def seed_closed_candles(self, candles: list[LiveCandle]) -> int:
#         seeded_count = 0

#         for candle in sorted(candles, key=lambda item: (item.symbol, item.bucket_epoch)):
#             before = self._last_closed_bucket_by_symbol.get(candle.symbol)
#             self.seed_closed_candle(candle)
#             after = self._last_closed_bucket_by_symbol.get(candle.symbol)

#             if after is not None and after != before:
#                 seeded_count += 1

#         return seeded_count



from __future__ import annotations

from collections import deque
from queue import Queue
from typing import Any

from trading_app.models import LiveCandle, MarketTick


class CandleManager:
    """
    Candle manager.

    - raw tick messages leta hai
    - timeframe based bucket banata hai
    - startup running bucket ko partial mark karta hai
    - live closed candles queue me deta hai
    - historical closed candles ko state me seed karta hai
    """

    def __init__(self, *, timeframe_seconds: int, startup_epoch: int | None = None) -> None:
        self.timeframe_seconds = timeframe_seconds
        self.closed_candle_queue: Queue[LiveCandle] = Queue()

        self._live_candles: dict[str, LiveCandle] = {}
        self._last_closed_bucket_by_symbol: dict[str, int] = {}
        self._seeded_closed_candles_by_symbol: dict[str, deque[LiveCandle]] = {}

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

    def set_startup_epoch(self, startup_epoch: int) -> None:
        self.startup_epoch = int(startup_epoch)
        self.startup_bucket_epoch = self._get_bucket_epoch(self.startup_epoch)
        self.startup_bucket_is_partial = self.startup_epoch > self.startup_bucket_epoch

    def _get_bucket_epoch(self, epoch_seconds: int) -> int:
        return (epoch_seconds // self.timeframe_seconds) * self.timeframe_seconds

    def _is_partial_bucket(self, bucket_epoch: int) -> bool:
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
        last_closed = self._last_closed_bucket_by_symbol.get(candle.symbol)
        if last_closed is not None and candle.bucket_epoch <= last_closed:
            print(
                "SKIP DUPLICATE CLOSED CANDLE:",
                candle.symbol,
                candle.bucket_epoch,
                self.timeframe_seconds,
                flush=True,
            )
            return

        self._last_closed_bucket_by_symbol[candle.symbol] = candle.bucket_epoch

        if not candle.is_complete:
            print(
                "SKIP PARTIAL CLOSED CANDLE:",
                candle.symbol,
                candle.bucket_epoch,
                self.timeframe_seconds,
                flush=True,
            )
            return

        self.closed_candle_queue.put(candle)

    def seed_closed_candle(self, candle: LiveCandle) -> None:
        if candle.timeframe_seconds != self.timeframe_seconds:
            raise ValueError(
                f"Timeframe mismatch. manager={self.timeframe_seconds}, candle={candle.timeframe_seconds}"
            )

        if not candle.is_complete:
            return

        last_closed = self._last_closed_bucket_by_symbol.get(candle.symbol)
        if last_closed is not None and candle.bucket_epoch <= last_closed:
            return

        store = self._seeded_closed_candles_by_symbol.setdefault(
            candle.symbol,
            deque(maxlen=500),
        )
        store.append(candle)
        self._last_closed_bucket_by_symbol[candle.symbol] = candle.bucket_epoch

    def seed_closed_candles(self, candles: list[LiveCandle]) -> int:
        seeded_count = 0

        for candle in sorted(candles, key=lambda item: (item.symbol, item.bucket_epoch)):
            before = self._last_closed_bucket_by_symbol.get(candle.symbol)
            self.seed_closed_candle(candle)
            after = self._last_closed_bucket_by_symbol.get(candle.symbol)

            if after is not None and after != before:
                seeded_count += 1

        return seeded_count

    def get_last_seeded_bucket(self, symbol: str) -> int | None:
        return self._last_closed_bucket_by_symbol.get(symbol)

    def get_seeded_closed_candles(self, symbol: str) -> list[LiveCandle]:
        candles = self._seeded_closed_candles_by_symbol.get(symbol)
        if candles is None:
            return []
        return list(candles)

    def process_tick_message(self, message: dict[str, Any]) -> None:
        symbol = str(message.get("symbol", "")).strip()
        if not symbol:
            return

        tick = MarketTick.from_message(message)
        if not tick.symbol or tick.exch_feed_time <= 0:
            return

        bucket_epoch = self._get_bucket_epoch(tick.exch_feed_time)
        current = self._live_candles.get(tick.symbol)

        if current is None:
            self._live_candles[tick.symbol] = self._new_candle_from_tick(
                tick, bucket_epoch
            )
            return

        if current.bucket_epoch == bucket_epoch:
            current.update(tick.ltp)
            return

        self._emit_closed_candle(current)
        self._live_candles[tick.symbol] = self._new_candle_from_tick(
            tick, bucket_epoch
        )

    def pop_closed_candles(self) -> list[LiveCandle]:
        candles: list[LiveCandle] = []

        while not self.closed_candle_queue.empty():
            candles.append(self.closed_candle_queue.get())

        return candles

    def get_live_candle(self, symbol: str) -> LiveCandle | None:
        return self._live_candles.get(symbol)