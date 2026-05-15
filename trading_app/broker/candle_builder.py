from __future__ import annotations

import time
from dataclasses import dataclass
from queue import Queue
from typing import Any

from trading_app.models import LiveCandle


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
        tick_queue: Queue[dict[str, Any]],
        closed_5s_queue: Queue[LiveCandle],
        default_symbol: str = "NSE:NIFTY50-INDEX",
        timeframe_seconds: int = 5,
        close_grace_seconds: int = 1,
        default_symbol_gap_seconds: int = 2,
    ) -> None:
        self.tick_queue = tick_queue
        self.closed_5s_queue = closed_5s_queue
        self.default_symbol = default_symbol
        self.timeframe_seconds = timeframe_seconds
        self.close_grace_seconds = close_grace_seconds
        self.default_symbol_gap_seconds = default_symbol_gap_seconds

        self.active_by_symbol: dict[str, CandleState] = {}
        self.pending_by_symbol: dict[str, CandleState] = {}
        self.pending_close_symbols: set[str] = set()
        self.last_closed_bucket_by_symbol: dict[str, int] = {}
        self.last_tick_epoch_by_symbol: dict[str, int] = {}
        self.subscribe_epoch_by_symbol: dict[str, int] = {}

        self.stream_disconnected = False

    def set_subscribe_epoch(self, symbol: str, epoch: int) -> None:
        self.subscribe_epoch_by_symbol[symbol] = int(epoch)

    def set_stream_disconnected(self, value: bool) -> None:
        self.stream_disconnected = value

    def on_tick(self, message: dict[str, Any]) -> None:
        self.tick_queue.put(message)

        symbol = str(message.get("symbol", ""))
        ltp = float(message.get("ltp", 0.0) or 0.0)
        exch_feed_time = int(message.get("exch_feed_time", 0) or 0)

        if not symbol or ltp <= 0 or exch_feed_time <= 0:
            self._close_due_pending(time.time())
            return

        if not self._is_market_hours(exch_feed_time):
            self._close_due_pending(time.time())
            return

        bucket_epoch = self._bucket_epoch(exch_feed_time)

        last_closed = self.last_closed_bucket_by_symbol.get(symbol)
        if last_closed is not None and bucket_epoch <= last_closed:
            self._close_due_pending(time.time())
            return

        pending = self.pending_by_symbol.get(symbol)
        if pending is not None and bucket_epoch == pending.candle.bucket_epoch:
            self._update_state(pending, ltp, exch_feed_time)
            self._update_last_tick(symbol, exch_feed_time)
            self._close_due_pending(time.time())
            return

        active = self.active_by_symbol.get(symbol)

        if active is None:
            self.active_by_symbol[symbol] = self._new_state(
                symbol,
                ltp,
                exch_feed_time,
                bucket_epoch,
            )
            self._update_last_tick(symbol, exch_feed_time)
            self._close_due_pending(time.time())
            return

        if bucket_epoch < active.candle.bucket_epoch:
            self._close_due_pending(time.time())
            return

        if bucket_epoch == active.candle.bucket_epoch:
            self._update_state(active, ltp, exch_feed_time)
            self._update_last_tick(symbol, exch_feed_time)
            self._close_due_pending(time.time())
            return

        self.pending_by_symbol[symbol] = active
        self.pending_close_symbols.add(symbol)

        self.active_by_symbol[symbol] = self._new_state(
            symbol,
            ltp,
            exch_feed_time,
            bucket_epoch,
        )
        self._update_last_tick(symbol, exch_feed_time)
        self._close_due_pending(time.time())

    def _close_due_pending(self, now_epoch: float) -> None:
        for symbol in list(self.pending_close_symbols):
            state = self.pending_by_symbol.get(symbol)
            if state is None:
                self.pending_close_symbols.discard(symbol)
                continue

            close_after = (
                state.candle.bucket_epoch
                + self.timeframe_seconds
                + self.close_grace_seconds
            )

            if now_epoch < close_after:
                continue

            state.candle.is_complete = True
            self._apply_state_to_candle(state)
            self.closed_5s_queue.put(state.candle)

            self.last_closed_bucket_by_symbol[symbol] = state.candle.bucket_epoch
            self.pending_by_symbol.pop(symbol, None)
            self.pending_close_symbols.discard(symbol)

    def _new_state(
        self,
        symbol: str,
        ltp: float,
        exch_feed_time: int,
        bucket_epoch: int,
    ) -> CandleState:
        candle = LiveCandle(
            symbol=symbol,
            bucket_epoch=bucket_epoch,
            timeframe_seconds=self.timeframe_seconds,
            open=ltp,
            high=ltp,
            low=ltp,
            close=ltp,
            volume=1,
            is_complete=False,
        )

        state = CandleState(
            candle=candle,
            first_tick_epoch=exch_feed_time,
            last_tick_epoch=exch_feed_time,
        )
        self._apply_partial_flags(state, symbol, exch_feed_time, bucket_epoch)
        return state

    def _update_state(self, state: CandleState, ltp: float, exch_feed_time: int) -> None:
        if ltp > state.candle.high:
            state.candle.high = ltp
        if ltp < state.candle.low:
            state.candle.low = ltp

        state.candle.close = ltp
        state.candle.volume += 1
        state.last_tick_epoch = exch_feed_time

        self._apply_partial_flags(
            state,
            state.candle.symbol,
            exch_feed_time,
            state.candle.bucket_epoch,
        )

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

        if self.stream_disconnected:
            self._mark_partial(state, "stream_disconnected")

        if symbol == self.default_symbol:
            last_tick = self.last_tick_epoch_by_symbol.get(symbol)
            if (
                last_tick is not None
                and exch_feed_time - last_tick > self.default_symbol_gap_seconds
            ):
                self._mark_partial(state, "default_symbol_tick_gap")

    def _mark_partial(self, state: CandleState, reason: str) -> None:
        state.is_partial = True
        state.partial_reason = reason

    def _apply_state_to_candle(self, state: CandleState) -> None:
        for name, value in (
            ("first_tick_epoch", state.first_tick_epoch),
            ("last_tick_epoch", state.last_tick_epoch),
            ("is_partial", state.is_partial),
            ("partial_reason", state.partial_reason),
        ):
            try:
                setattr(state.candle, name, value)
            except AttributeError:
                pass

    def _update_last_tick(self, symbol: str, exch_feed_time: int) -> None:
        self.last_tick_epoch_by_symbol[symbol] = exch_feed_time

    def _bucket_epoch(self, epoch: int) -> int:
        return int(epoch) - (int(epoch) % self.timeframe_seconds)

    def _is_market_hours(self, epoch: int) -> bool:
        seconds = int(epoch % 86400)
        return MARKET_OPEN_SECONDS <= seconds <= MARKET_CLOSE_SECONDS