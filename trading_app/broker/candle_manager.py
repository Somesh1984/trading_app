from __future__ import annotations

from trading_app.logger import get_logger, log_debug, log_error, log_info, log_warning

logger = get_logger(__name__)


from collections import deque
from datetime import datetime
from queue import Queue
from time import time
from typing import Any, Callable
from zoneinfo import ZoneInfo

from trading_app.models import LiveCandle, MarketTick


IST = ZoneInfo("Asia/Kolkata")
GapCallback = Callable[[str, int, int, int], bool]


class CandleManager:
    def __init__(
        self,
        *,
        timeframe_seconds: int,
        startup_epoch: int | None = None,
        allow_partial_bucket: bool = True,
        close_grace_seconds: int = 1,
        debug: bool = False,
    ) -> None:
        self.timeframe_seconds = timeframe_seconds
        self.allow_partial_bucket = allow_partial_bucket
        self.close_grace_seconds = close_grace_seconds
        self.debug = debug

        self.downstream_managers: list["CandleManager"] = []
        self.closed_candle_queue: Queue[LiveCandle] = Queue()

        self._live_candles: dict[str, LiveCandle] = {}
        self._last_closed_bucket_by_symbol: dict[str, int] = {}
        self._seeded_closed_candles_by_symbol: dict[str, deque[LiveCandle]] = {}

        self._startup_seen_symbols: set[str] = set()
        self._startup_partial_bucket_by_symbol: dict[str, int] = {}

        self._pending_closed_candle_by_symbol: dict[str, LiveCandle] = {}
        self._pending_close_start_epoch_by_symbol: dict[str, int] = {}
        self._next_bucket_tick_count_by_symbol: dict[str, int] = {}

        self._aggregate_candles_by_symbol_and_bucket: dict[
            str,
            dict[int, LiveCandle],
        ] = {}
        self._aggregate_source_buckets_by_symbol_and_bucket: dict[
            str,
            dict[int, set[int]],
        ] = {}
        self._reported_aggregate_gaps: set[tuple[str, int, int, int]] = set()

        self._on_gap_detected: GapCallback | None = None
        self._replayed_closed_buckets: set[tuple[str, int]] = set()

    def set_symbol_startup_epoch(self, symbol: str, startup_epoch: int) -> None:
        startup_epoch = int(startup_epoch)
        startup_bucket_epoch = self._get_anchored_bucket_epoch(
            symbol,
            startup_epoch,
            self.timeframe_seconds,
        )

        self._startup_seen_symbols.add(symbol)

        if self.allow_partial_bucket and startup_epoch > startup_bucket_epoch:
            self._startup_partial_bucket_by_symbol[symbol] = startup_bucket_epoch
        else:
            self._startup_partial_bucket_by_symbol.pop(symbol, None)

    def set_gap_callback(self, callback: GapCallback | None) -> None:
        self._on_gap_detected = callback

    def process_tick_message(self, message: dict[str, Any]) -> None:
        symbol = str(message.get("symbol", "")).strip()
        if not symbol:
            return

        tick = MarketTick.from_message(message)
        if not tick.symbol or tick.exch_feed_time <= 0 or tick.ltp <= 0:
            return

        if tick.symbol not in self._startup_seen_symbols:
            self.set_symbol_startup_epoch(tick.symbol, tick.exch_feed_time)

        bucket_epoch = self._get_bucket_epoch(tick.symbol, tick.exch_feed_time)
        current = self._live_candles.get(tick.symbol)
        pending = self._pending_closed_candle_by_symbol.get(tick.symbol)
        last_closed_bucket = self._last_closed_bucket_by_symbol.get(tick.symbol)

        if pending is not None:
            pending = self._try_close_pending_candle(tick, bucket_epoch, pending)
            last_closed_bucket = self._last_closed_bucket_by_symbol.get(tick.symbol)

        if last_closed_bucket is not None and bucket_epoch <= last_closed_bucket:
            if self.debug:
                log_debug(logger,
                    "SKIP CLOSED BUCKET TICK:",
                    tick.symbol,
                    bucket_epoch,
                    last_closed_bucket,
                    flush=True,
                )
            return

        if pending is not None and bucket_epoch == pending.bucket_epoch:
            pending.update(tick.ltp)
            return

        if current is None:
            self._live_candles[tick.symbol] = self._new_candle_from_tick(
                tick,
                bucket_epoch,
            )
            self._increment_next_bucket_tick_count(tick.symbol, bucket_epoch, pending)
            return

        if bucket_epoch < current.bucket_epoch:
            if self.debug:
                log_debug(logger,
                    "SKIP OLD BUCKET TICK:",
                    tick.symbol,
                    tick.exch_feed_time,
                    bucket_epoch,
                    current.bucket_epoch,
                    flush=True,
                )
            return

        if bucket_epoch == current.bucket_epoch:
            current.update(tick.ltp)
            self._increment_next_bucket_tick_count(tick.symbol, bucket_epoch, pending)
            return

        self._move_current_to_pending(tick.symbol, current)
        self._live_candles[tick.symbol] = self._new_candle_from_tick(
            tick,
            bucket_epoch,
        )

    def aggregate_closed_candle(self, source_candle: LiveCandle) -> None:
        if not self._can_aggregate(source_candle):
            return

        symbol = source_candle.symbol
        target_bucket_epoch = self._get_target_bucket_epoch(source_candle)

        if self._is_closed_target_bucket(symbol, target_bucket_epoch):
            return

        if self._is_duplicate_source_bucket(source_candle, target_bucket_epoch):
            return

        current = self._add_source_to_aggregate(source_candle, target_bucket_epoch)

        if not self._is_aggregate_complete(source_candle, target_bucket_epoch):
            return

        self._emit_completed_aggregate(symbol, target_bucket_epoch, current)

    def _can_aggregate(self, source_candle: LiveCandle) -> bool:
        if not source_candle.is_complete:
            return False

        if source_candle.timeframe_seconds >= self.timeframe_seconds:
            return False

        return self.timeframe_seconds % source_candle.timeframe_seconds == 0

    def _get_target_bucket_epoch(self, source_candle: LiveCandle) -> int:
        return self._get_anchored_bucket_epoch(
            source_candle.symbol,
            source_candle.bucket_epoch,
            source_candle.timeframe_seconds,
        )

    def _is_closed_target_bucket(self, symbol: str, target_bucket_epoch: int) -> bool:
        last_closed_bucket = self._last_closed_bucket_by_symbol.get(symbol)
        return last_closed_bucket is not None and target_bucket_epoch <= last_closed_bucket

    def _is_duplicate_source_bucket(
        self,
        source_candle: LiveCandle,
        target_bucket_epoch: int,
    ) -> bool:
        source_buckets = self._get_aggregate_source_buckets(
            source_candle.symbol,
            target_bucket_epoch,
        )
        return source_candle.bucket_epoch in source_buckets

    def _add_source_to_aggregate(
        self,
        source_candle: LiveCandle,
        target_bucket_epoch: int,
    ) -> LiveCandle:
        symbol = source_candle.symbol
        candles_by_target = (
            self._aggregate_candles_by_symbol_and_bucket.setdefault(symbol, {})
        )
        source_buckets = self._get_aggregate_source_buckets(symbol, target_bucket_epoch)

        current = candles_by_target.get(target_bucket_epoch)
        if current is None:
            current = self._new_candle_from_source(source_candle, target_bucket_epoch)
            candles_by_target[target_bucket_epoch] = current
        else:
            current.high = max(current.high, source_candle.high)
            current.low = min(current.low, source_candle.low)
            current.close = source_candle.close
            current.volume += source_candle.volume

        source_buckets.add(source_candle.bucket_epoch)
        return current

    def _is_aggregate_complete(
        self,
        source_candle: LiveCandle,
        target_bucket_epoch: int,
    ) -> bool:
        source_buckets = self._get_aggregate_source_buckets(
            source_candle.symbol,
            target_bucket_epoch,
        )
        expected_buckets = self._get_expected_source_buckets(
            target_bucket_epoch,
            source_candle.timeframe_seconds,
        )
        return source_buckets == expected_buckets

    def _emit_completed_aggregate(
        self,
        symbol: str,
        target_bucket_epoch: int,
        candle: LiveCandle,
    ) -> None:
        self._emit_closed_candle(candle)

        self._aggregate_candles_by_symbol_and_bucket.get(symbol, {}).pop(
            target_bucket_epoch,
            None,
        )
        self._aggregate_source_buckets_by_symbol_and_bucket.get(symbol, {}).pop(
            target_bucket_epoch,
            None,
        )

    def _get_aggregate_source_buckets(
        self,
        symbol: str,
        target_bucket_epoch: int,
    ) -> set[int]:
        source_buckets_by_target = (
            self._aggregate_source_buckets_by_symbol_and_bucket.setdefault(symbol, {})
        )
        return source_buckets_by_target.setdefault(target_bucket_epoch, set())

    def _get_expected_source_buckets(
        self,
        target_bucket_epoch: int,
        source_timeframe_seconds: int,
    ) -> set[int]:
        required_count = self.timeframe_seconds // source_timeframe_seconds

        return {
            target_bucket_epoch + (i * source_timeframe_seconds)
            for i in range(required_count)
        }

    def seed_closed_candle(self, candle: LiveCandle) -> None:
        if candle.timeframe_seconds != self.timeframe_seconds:
            raise ValueError(
                f"Timeframe mismatch. manager={self.timeframe_seconds}, "
                f"candle={candle.timeframe_seconds}"
            )

        if not candle.is_complete:
            return

        last_closed = self._last_closed_bucket_by_symbol.get(candle.symbol)

        if last_closed is not None:
            expected_bucket = last_closed + self.timeframe_seconds

            if candle.bucket_epoch <= last_closed:
                return

            if candle.bucket_epoch != expected_bucket:
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


    def accept_closed_base_candle(self, candle: LiveCandle) -> bool:
        if candle.timeframe_seconds != self.timeframe_seconds:
            raise ValueError(
                f"Timeframe mismatch. manager={self.timeframe_seconds}, "
                f"candle={candle.timeframe_seconds}"
            )

        if not candle.is_complete:
            return False

        if self._is_partial_bucket(candle.symbol, candle.bucket_epoch):
            self._last_closed_bucket_by_symbol[candle.symbol] = candle.bucket_epoch
            return True

        last_closed = self._last_closed_bucket_by_symbol.get(candle.symbol)

        if last_closed is not None:
            expected_bucket = last_closed + self.timeframe_seconds

            if candle.bucket_epoch <= last_closed:
                return False

            if candle.bucket_epoch < expected_bucket:
                return False

            if candle.bucket_epoch > expected_bucket:
                if self._on_gap_detected is not None:
                    gap_filled = self._on_gap_detected(
                        candle.symbol,
                        expected_bucket,
                        candle.bucket_epoch - self.timeframe_seconds,
                        self.timeframe_seconds,
                    )
                    if not gap_filled and self.debug:
                        log_debug(logger,
                            "CONTINUE AFTER GAP MISS:",
                            candle.symbol,
                            expected_bucket,
                            candle.bucket_epoch,
                            flush=True,
                        )

                self._emit_closed_candle(candle)
                return True

        self._emit_closed_candle(candle)
        return True

    def replay_closed_candle(self, candle: LiveCandle) -> None:
        self.accept_closed_base_candle(candle)

    def pop_closed_candles(self) -> list[LiveCandle]:
        candles: list[LiveCandle] = []

        while not self.closed_candle_queue.empty():
            candles.append(self.closed_candle_queue.get())

        return candles

    def get_live_candle(self, symbol: str) -> LiveCandle | None:
        live = self._live_candles.get(symbol)
        if live is not None:
            return live

        aggregate_candles = self._aggregate_candles_by_symbol_and_bucket.get(symbol)
        if not aggregate_candles:
            return None

        latest_bucket = max(aggregate_candles)
        return aggregate_candles[latest_bucket]

    def get_last_closed_bucket(self, symbol: str) -> int | None:
        return self._last_closed_bucket_by_symbol.get(symbol)

    def get_last_seeded_bucket(self, symbol: str) -> int | None:
        return self._last_closed_bucket_by_symbol.get(symbol)

    def get_seeded_closed_candles(self, symbol: str) -> list[LiveCandle]:
        candles = self._seeded_closed_candles_by_symbol.get(symbol)
        if candles is None:
            return []

        return list(candles)

    def close_due_candles(self, now_epoch: int | None = None) -> int:
        if now_epoch is None:
            now_epoch = int(time())

        closed_count = 0

        for symbol, pending in list(self._pending_closed_candle_by_symbol.items()):
            close_after_epoch = (
                pending.bucket_epoch
                + pending.timeframe_seconds
                + self.close_grace_seconds
            )

            if now_epoch < close_after_epoch:
                continue

            pending.is_complete = True

            if self.accept_closed_base_candle(pending):
                self._clear_pending_state(symbol)
                closed_count += 1

        for symbol, current in list(self._live_candles.items()):
            close_after_epoch = (
                current.bucket_epoch
                + current.timeframe_seconds
                + self.close_grace_seconds
            )

            if now_epoch < close_after_epoch:
                continue

            current.is_complete = True

            if self.accept_closed_base_candle(current):
                self._live_candles.pop(symbol, None)
                closed_count += 1

        return closed_count

    def _try_close_pending_candle(
        self,
        tick: MarketTick,
        bucket_epoch: int,
        pending: LiveCandle,
    ) -> LiveCandle | None:
        pending_start = self._pending_close_start_epoch_by_symbol.get(
            tick.symbol,
            pending.bucket_epoch + pending.timeframe_seconds,
        )
        next_bucket_tick_count = self._next_bucket_tick_count_by_symbol.get(
            tick.symbol,
            0,
        )

        should_close_pending = (
            bucket_epoch > pending.bucket_epoch and next_bucket_tick_count >= 2
        )

        if int(time()) >= pending_start + self.close_grace_seconds:
            should_close_pending = True

        if not should_close_pending:
            return pending

        pending.is_complete = True
        accepted = self.accept_closed_base_candle(pending)

        if not accepted:
            return pending

        self._clear_pending_state(tick.symbol)

        return None

    def _move_current_to_pending(
        self,
        symbol: str,
        current: LiveCandle,
    ) -> None:
        self._pending_closed_candle_by_symbol[symbol] = current
        self._pending_close_start_epoch_by_symbol[symbol] = (
            current.bucket_epoch + current.timeframe_seconds
        )
        self._next_bucket_tick_count_by_symbol[symbol] = 1

    def _clear_pending_state(self, symbol: str) -> None:
        self._pending_closed_candle_by_symbol.pop(symbol, None)
        self._pending_close_start_epoch_by_symbol.pop(symbol, None)
        self._next_bucket_tick_count_by_symbol.pop(symbol, None)

    def _increment_next_bucket_tick_count(
        self,
        symbol: str,
        bucket_epoch: int,
        pending: LiveCandle | None,
    ) -> None:
        if pending is None:
            return

        if bucket_epoch <= pending.bucket_epoch:
            return

        self._next_bucket_tick_count_by_symbol[symbol] = (
            self._next_bucket_tick_count_by_symbol.get(symbol, 0) + 1
        )

    def _emit_closed_candle(self, candle: LiveCandle) -> None:
        symbol = candle.symbol

        last_closed = self._last_closed_bucket_by_symbol.get(symbol)
        if last_closed is not None and candle.bucket_epoch <= last_closed:
            if self.debug:
                log_debug(logger, "SKIP DUPLICATE CLOSE:", symbol, candle.bucket_epoch, flush=True)
            return

        if self._is_partial_bucket(symbol, candle.bucket_epoch):
            self._last_closed_bucket_by_symbol[symbol] = candle.bucket_epoch

            if self.debug:
                log_debug(logger, "SKIP PARTIAL CLOSE:", symbol, candle.bucket_epoch, flush=True)
            return

        candle.is_complete = True
        self._last_closed_bucket_by_symbol[symbol] = candle.bucket_epoch

        if self.debug:
            log_debug(logger,
                "CANDLE CLOSE DEBUG:",
                symbol,
                "bucket:",
                candle.bucket_epoch,
                "O:",
                candle.open,
                "H:",
                candle.high,
                "L:",
                candle.low,
                "C:",
                candle.close,
                flush=True,
            )

        self.closed_candle_queue.put(candle)

        for manager in self.downstream_managers:
            manager.aggregate_closed_candle(candle)

    def _new_candle_from_tick(
        self,
        tick: MarketTick,
        bucket_epoch: int,
    ) -> LiveCandle:
        return LiveCandle(
            symbol=tick.symbol,
            bucket_epoch=bucket_epoch,
            timeframe_seconds=self.timeframe_seconds,
            open=tick.ltp,
            high=tick.ltp,
            low=tick.ltp,
            close=tick.ltp,
            volume=1,
            is_complete=False,
        )

    def _new_candle_from_source(
        self,
        source_candle: LiveCandle,
        bucket_epoch: int,
    ) -> LiveCandle:
        return LiveCandle(
            symbol=source_candle.symbol,
            bucket_epoch=bucket_epoch,
            timeframe_seconds=self.timeframe_seconds,
            open=source_candle.open,
            high=source_candle.high,
            low=source_candle.low,
            close=source_candle.close,
            volume=source_candle.volume,
            is_complete=False,
        )

    def _get_bucket_epoch(self, symbol: str, epoch_seconds: int) -> int:
        return self._get_anchored_bucket_epoch(
            symbol,
            epoch_seconds,
            self.timeframe_seconds,
        )

    def _is_partial_bucket(self, symbol: str, bucket_epoch: int) -> bool:
        return self._startup_partial_bucket_by_symbol.get(symbol) == bucket_epoch

    def _get_anchored_bucket_epoch(
        self,
        symbol: str,
        timestamp_epoch: int,
        source_timeframe_seconds: int,
    ) -> int:
        if source_timeframe_seconds <= 0:
            raise ValueError("source_timeframe_seconds must be positive")

        if self.timeframe_seconds % source_timeframe_seconds != 0:
            raise ValueError(
                "target timeframe must be an exact multiple of source timeframe"
            )

        session_anchor = self._get_session_anchor_epoch(symbol, timestamp_epoch)
        elapsed = timestamp_epoch - session_anchor

        if elapsed < 0:
            elapsed = 0

        bucket_offset = (elapsed // self.timeframe_seconds) * self.timeframe_seconds
        return session_anchor + bucket_offset

    def _get_session_anchor_epoch(self, symbol: str, timestamp_epoch: int) -> int:
        dt = datetime.fromtimestamp(timestamp_epoch, tz=IST)

        if symbol.startswith("MCX:"):
            hour = 9
            minute = 0
        else:
            hour = 9
            minute = 15

        session_start = dt.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        return int(session_start.timestamp())
