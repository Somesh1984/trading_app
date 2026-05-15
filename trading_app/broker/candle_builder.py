from __future__ import annotations

import time
from heapq import heappop, heappush
from dataclasses import dataclass
from datetime import datetime
from queue import Full, Queue
from threading import RLock
from typing import Any
from zoneinfo import ZoneInfo

from trading_app.models import LiveCandle


IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN_SECONDS = 9 * 3600 + 15 * 60
MARKET_CLOSE_SECONDS = 15 * 3600 + 30 * 60


@dataclass(slots=True)
class CandleState:
    candle: LiveCandle
    first_tick_epoch: int
    last_tick_epoch: int
    is_partial: bool = False
    partial_reason: str = ""


class Live5sCandleBuilder:
    def __init__(
        self,
        *,
        closed_5s_queue: Queue[LiveCandle],
        tick_queue: Queue[dict[str, Any]] | None = None,
        default_symbol: str = "NSE:NIFTY50-INDEX",
        timeframe_seconds: int = 5,
        close_grace_seconds: int = 1,
        default_symbol_gap_seconds: int = 2,
        stream_disconnect_grace_seconds: float = 1.0,
    ) -> None:
        self.tick_queue = tick_queue
        self.closed_5s_queue = closed_5s_queue
        self._lock = RLock()
        self.default_symbol = default_symbol
        self.timeframe_seconds = timeframe_seconds
        self.close_grace_seconds = close_grace_seconds
        self.default_symbol_gap_seconds = default_symbol_gap_seconds
        self.stream_disconnect_grace_seconds = stream_disconnect_grace_seconds

        self.active_by_symbol: dict[str, CandleState] = {}
        self.pending_by_symbol: dict[str, CandleState] = {}
        self.active_close_heap: list[tuple[int, str, int]] = []
        self.pending_close_heap: list[tuple[int, str, int]] = []
        self.last_closed_bucket_by_symbol: dict[str, int] = {}
        self.last_tick_epoch_by_symbol: dict[str, int] = {}
        self.last_total_volume_by_symbol: dict[str, int] = {}
        self.subscribe_epoch_by_symbol: dict[str, int] = {}
        self.ignored_late_tick_count = 0
        self.ignored_stale_tick_count = 0
        self.dropped_tick_queue_message_count = 0
        self.dropped_closed_candle_count = 0

        self.stream_disconnected = False
        self.stream_disconnect_started_epoch: float | None = None
        self.stream_disconnect_intervals: list[tuple[float, float]] = []
        self.default_symbol_gap_intervals: list[tuple[int, int]] = []

    def set_subscribe_epoch(self, symbol: str, epoch: int) -> None:
        with self._lock:
            self.subscribe_epoch_by_symbol[symbol] = int(epoch)

    def set_stream_disconnected(
        self,
        value: bool,
        now_epoch: float | None = None,
    ) -> None:
        with self._lock:
            now = time.time() if now_epoch is None else now_epoch

            if value:
                if not self.stream_disconnected:
                    self.stream_disconnect_started_epoch = now
                self.stream_disconnected = True
                return

            if (
                self.stream_disconnected
                and self.stream_disconnect_started_epoch is not None
            ):
                duration = now - self.stream_disconnect_started_epoch
                if duration >= self.stream_disconnect_grace_seconds:
                    self._append_unique_interval(
                        self.stream_disconnect_intervals,
                        (self.stream_disconnect_started_epoch, now)
                    )

            self.stream_disconnected = value
            self.stream_disconnect_started_epoch = None

    def on_tick(self, message: dict[str, Any]) -> None:
        with self._lock:
            try:
                if self.tick_queue is not None:
                    self.tick_queue.put_nowait(message)
            except Full:
                self.dropped_tick_queue_message_count += 1

            try:
                symbol = str(message.get("symbol", ""))
                ltp = float(message.get("ltp", 0.0) or 0.0)
                exch_feed_time = int(message.get("exch_feed_time", 0) or 0)
                volume_delta = self._get_volume_delta(symbol, message)

                if not symbol or ltp <= 0 or exch_feed_time <= 0:
                    return

                if not self._is_market_hours(exch_feed_time):
                    return

                bucket_epoch = self._bucket_epoch(exch_feed_time)

                last_closed = self.last_closed_bucket_by_symbol.get(symbol)
                if last_closed is not None and bucket_epoch <= last_closed:
                    self.ignored_late_tick_count += 1
                    return

                pending = self.pending_by_symbol.get(symbol)
                if pending is not None and bucket_epoch == pending.candle.bucket_epoch:
                    self._update_state(pending, ltp, exch_feed_time, volume_delta)
                    self._update_last_tick(symbol, exch_feed_time)
                    return

                active = self.active_by_symbol.get(symbol)

                if active is None:
                    self._set_active_state(
                        symbol,
                        self._new_state(
                            symbol,
                            ltp,
                            exch_feed_time,
                            bucket_epoch,
                            volume_delta,
                        ),
                    )
                    self._update_last_tick(symbol, exch_feed_time)
                    return

                if bucket_epoch < active.candle.bucket_epoch:
                    self.ignored_stale_tick_count += 1
                    return

                if bucket_epoch == active.candle.bucket_epoch:
                    self._update_state(active, ltp, exch_feed_time, volume_delta)
                    self._update_last_tick(symbol, exch_feed_time)
                    return

                self._move_active_to_pending(symbol, active)
                self._set_active_state(
                    symbol,
                    self._new_state(
                        symbol,
                        ltp,
                        exch_feed_time,
                        bucket_epoch,
                        volume_delta,
                    ),
                )
                self._update_last_tick(symbol, exch_feed_time)

            finally:
                self._close_due_pending(time.time())

    def close_due_candles(self, now_epoch: float | None = None) -> int:
        with self._lock:
            now = time.time() if now_epoch is None else now_epoch
            closed_count = self._close_due_pending(now)
            self._move_due_active_to_pending(now)
            closed_count += self._close_due_pending(now)
            self._prune_partial_intervals()
            return closed_count

    def close_due_pending(self, now_epoch: float | None = None) -> int:
        with self._lock:
            now = time.time() if now_epoch is None else now_epoch
            closed_count = self._close_due_pending(now)
            self._prune_partial_intervals()
            return closed_count

    def snapshot_stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "active_symbols": len(self.active_by_symbol),
                "pending_symbols": len(self.pending_by_symbol),
                "ignored_late_ticks": self.ignored_late_tick_count,
                "ignored_stale_ticks": self.ignored_stale_tick_count,
                "dropped_tick_queue_messages": (
                    self.dropped_tick_queue_message_count
                ),
                "dropped_closed_candles": self.dropped_closed_candle_count,
                "disconnect_intervals": len(self.stream_disconnect_intervals),
                "default_symbol_gap_intervals": (
                    len(self.default_symbol_gap_intervals)
                ),
            }

    def _close_due_pending(self, now_epoch: float) -> int:
        closed_count = 0

        while self.pending_close_heap and self.pending_close_heap[0][0] <= now_epoch:
            _, symbol, bucket_epoch = heappop(self.pending_close_heap)
            state = self.pending_by_symbol.get(symbol)

            if state is None:
                continue

            if state.candle.bucket_epoch != bucket_epoch:
                continue

            self._publish_closed_state(state)
            self.pending_by_symbol.pop(symbol, None)
            closed_count += 1

        return closed_count

    def _move_due_active_to_pending(self, now_epoch: float) -> int:
        moved_count = 0

        while self.active_close_heap and self.active_close_heap[0][0] <= now_epoch:
            _, symbol, bucket_epoch = heappop(self.active_close_heap)
            state = self.active_by_symbol.get(symbol)

            if state is None or state.candle.bucket_epoch != bucket_epoch:
                continue

            self._move_active_to_pending(symbol, state)
            moved_count += 1

        return moved_count

    def _move_active_to_pending(self, symbol: str, state: CandleState) -> None:
        self.pending_by_symbol[symbol] = state
        self.active_by_symbol.pop(symbol, None)
        heappush(
            self.pending_close_heap,
            (
                state.candle.bucket_epoch
                + self.timeframe_seconds
                + self.close_grace_seconds,
                symbol,
                state.candle.bucket_epoch,
            ),
        )

    def _set_active_state(self, symbol: str, state: CandleState) -> None:
        self.active_by_symbol[symbol] = state
        heappush(
            self.active_close_heap,
            (
                state.candle.bucket_epoch + self.timeframe_seconds,
                symbol,
                state.candle.bucket_epoch,
            ),
        )

    def _publish_closed_state(self, state: CandleState) -> None:
        state.candle.is_complete = True
        self._apply_disconnect_partial(state)
        self._apply_default_symbol_gap_partial(state)
        self._apply_state_to_candle(state)
        self.last_closed_bucket_by_symbol[state.candle.symbol] = state.candle.bucket_epoch
        try:
            self.closed_5s_queue.put_nowait(state.candle)
        except Full:
            self.dropped_closed_candle_count += 1
            return

    def _new_state(
        self,
        symbol: str,
        ltp: float,
        exch_feed_time: int,
        bucket_epoch: int,
        volume_delta: int | None,
    ) -> CandleState:
        candle = LiveCandle(
            symbol=symbol,
            bucket_epoch=bucket_epoch,
            timeframe_seconds=self.timeframe_seconds,
            open=ltp,
            high=ltp,
            low=ltp,
            close=ltp,
            volume=max(volume_delta or 0, 0),
            tick_count=1,
            is_complete=False,
            first_tick_epoch=exch_feed_time,
            last_tick_epoch=exch_feed_time,
        )

        state = CandleState(
            candle=candle,
            first_tick_epoch=exch_feed_time,
            last_tick_epoch=exch_feed_time,
        )
        self._apply_partial_flags(state, symbol, exch_feed_time, bucket_epoch)
        self._apply_volume_partial(state, volume_delta)
        self._apply_state_to_candle(state)
        return state

    def _update_state(
        self,
        state: CandleState,
        ltp: float,
        exch_feed_time: int,
        volume_delta: int | None,
    ) -> None:
        if ltp > state.candle.high:
            state.candle.high = ltp
        if ltp < state.candle.low:
            state.candle.low = ltp

        state.candle.close = ltp
        state.candle.tick_count += 1
        if volume_delta is not None and volume_delta > 0:
            state.candle.volume += volume_delta
        state.last_tick_epoch = exch_feed_time

        self._apply_partial_flags(
            state,
            state.candle.symbol,
            exch_feed_time,
            state.candle.bucket_epoch,
        )
        self._apply_volume_partial(state, volume_delta)
        self._apply_state_to_candle(state)

    def _get_volume_delta(
        self,
        symbol: str,
        message: dict[str, Any],
    ) -> int | None:
        if not symbol:
            return None

        total_volume = self._extract_total_volume(message)
        if total_volume is None:
            return None

        previous_total = self.last_total_volume_by_symbol.get(symbol)
        self.last_total_volume_by_symbol[symbol] = total_volume

        if previous_total is None:
            return None

        volume_delta = total_volume - previous_total
        if volume_delta < 0:
            return None

        return volume_delta

    def _extract_total_volume(self, message: dict[str, Any]) -> int | None:
        raw_volume = message.get("vol_traded_today")
        if raw_volume is None:
            raw_volume = message.get("volume")

        if raw_volume is None:
            return None

        try:
            return int(float(raw_volume))
        except (TypeError, ValueError):
            return None

    def _apply_partial_flags(
        self,
        state: CandleState,
        symbol: str,
        exch_feed_time: int,
        bucket_epoch: int,
    ) -> None:
        subscribe_epoch = self.subscribe_epoch_by_symbol.get(symbol)
        if subscribe_epoch is not None and subscribe_epoch >= bucket_epoch:
            self._mark_partial(state, "subscribe_after_or_at_bucket_start")

        if symbol == self.default_symbol:
            last_tick = self.last_tick_epoch_by_symbol.get(symbol)
            if (
                last_tick is not None
                and exch_feed_time - last_tick > self.default_symbol_gap_seconds
            ):
                self._record_default_symbol_gap(last_tick, exch_feed_time)

        self._apply_disconnect_partial(state)
        self._apply_default_symbol_gap_partial(state)

    def _apply_volume_partial(
        self,
        state: CandleState,
        volume_delta: int | None,
    ) -> None:
        if volume_delta is None:
            self._mark_partial(state, "volume_baseline_missing_or_reset")

    def _mark_partial(self, state: CandleState, reason: str) -> None:
        state.is_partial = True
        reasons = [
            item
            for item in state.partial_reason.split("|")
            if item
        ]
        if reason not in reasons:
            reasons.append(reason)
        state.partial_reason = "|".join(reasons)

    def _record_default_symbol_gap(self, from_epoch: int, to_epoch: int) -> None:
        self._append_unique_interval(
            self.default_symbol_gap_intervals,
            (from_epoch, to_epoch),
        )

    def _append_unique_interval(
        self,
        intervals: list[tuple[float, float]] | list[tuple[int, int]],
        interval: tuple[float, float] | tuple[int, int],
    ) -> None:
        if interval in intervals:
            return

        intervals.append(interval)

    def _apply_disconnect_partial(self, state: CandleState) -> None:
        candle_start = state.candle.bucket_epoch
        candle_end = state.candle.bucket_epoch + state.candle.timeframe_seconds

        if self._has_disconnect_overlap(candle_start, candle_end):
            self._mark_partial(state, "stream_disconnected")

    def _apply_default_symbol_gap_partial(self, state: CandleState) -> None:
        candle_start = state.candle.bucket_epoch
        candle_end = state.candle.bucket_epoch + state.candle.timeframe_seconds

        if self._has_default_symbol_gap_overlap(candle_start, candle_end):
            self._mark_partial(state, "default_symbol_tick_gap")

    def _has_disconnect_overlap(self, start_epoch: int, end_epoch: int) -> bool:
        for disconnect_start, disconnect_end in self.stream_disconnect_intervals:
            if disconnect_start < end_epoch and disconnect_end > start_epoch:
                return True

        if (
            self.stream_disconnected
            and self.stream_disconnect_started_epoch is not None
        ):
            now = time.time()
            if now - self.stream_disconnect_started_epoch < self.stream_disconnect_grace_seconds:
                return False
            return self.stream_disconnect_started_epoch < end_epoch and now > start_epoch

        return False

    def _has_default_symbol_gap_overlap(self, start_epoch: int, end_epoch: int) -> bool:
        for gap_start, gap_end in self.default_symbol_gap_intervals:
            if gap_start < end_epoch and gap_end > start_epoch:
                return True

        return False

    def _prune_partial_intervals(self) -> None:
        cutoff_epoch = self._oldest_open_candle_epoch()

        if cutoff_epoch is None:
            self.stream_disconnect_intervals.clear()
            self.default_symbol_gap_intervals.clear()
            return

        self.stream_disconnect_intervals = [
            interval
            for interval in self.stream_disconnect_intervals
            if interval[1] > cutoff_epoch
        ]
        self.default_symbol_gap_intervals = [
            interval
            for interval in self.default_symbol_gap_intervals
            if interval[1] > cutoff_epoch
        ]

    def _oldest_open_candle_epoch(self) -> int | None:
        states = [
            *self.active_by_symbol.values(),
            *self.pending_by_symbol.values(),
        ]
        if not states:
            return None

        return min(state.candle.bucket_epoch for state in states)

    def _apply_state_to_candle(self, state: CandleState) -> None:
        state.candle.first_tick_epoch = state.first_tick_epoch
        state.candle.last_tick_epoch = state.last_tick_epoch
        state.candle.is_partial = state.is_partial
        state.candle.partial_reason = state.partial_reason

    def _update_last_tick(self, symbol: str, exch_feed_time: int) -> None:
        self.last_tick_epoch_by_symbol[symbol] = exch_feed_time

    def _bucket_epoch(self, epoch: int) -> int:
        return int(epoch) - (int(epoch) % self.timeframe_seconds)

    def _is_market_hours(self, epoch: int) -> bool:
        dt = datetime.fromtimestamp(epoch, tz=IST)
        seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
        return MARKET_OPEN_SECONDS <= seconds <= MARKET_CLOSE_SECONDS
