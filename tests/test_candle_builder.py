from datetime import datetime
from queue import Empty, Queue
from zoneinfo import ZoneInfo

from trading_app.broker import candle_builder as candle_builder_module
from trading_app.broker.candle_builder import Live5sCandleBuilder


IST = ZoneInfo("Asia/Kolkata")
SYMBOL = "NSE:NIFTY50-INDEX"
OTHER_SYMBOL = "NSE:RELIANCE-EQ"


def market_epoch(hour: int, minute: int, second: int) -> int:
    return int(datetime(2025, 4, 23, hour, minute, second, tzinfo=IST).timestamp())


def make_builder() -> Live5sCandleBuilder:
    return Live5sCandleBuilder(
        tick_queue=Queue(),
        closed_5s_queue=Queue(),
        default_symbol=SYMBOL,
        timeframe_seconds=5,
        close_grace_seconds=1,
    )


def make_builder_with_tick_queue(tick_queue: Queue) -> Live5sCandleBuilder:
    return Live5sCandleBuilder(
        tick_queue=tick_queue,
        closed_5s_queue=Queue(),
        default_symbol=SYMBOL,
        timeframe_seconds=5,
        close_grace_seconds=1,
    )


def make_builder_with_closed_queue(closed_queue: Queue) -> Live5sCandleBuilder:
    return Live5sCandleBuilder(
        tick_queue=Queue(),
        closed_5s_queue=closed_queue,
        default_symbol=SYMBOL,
        timeframe_seconds=5,
        close_grace_seconds=1,
    )


def test_builder_publishes_active_candle_after_bucket_close_plus_grace(monkeypatch):
    builder = make_builder()
    tick_epoch = market_epoch(9, 15, 1)
    bucket_epoch = tick_epoch - (tick_epoch % 5)
    monkeypatch.setattr(candle_builder_module.time, "time", lambda: bucket_epoch + 2)

    builder.on_tick(
        {
            "symbol": SYMBOL,
            "ltp": 100.0,
            "exch_feed_time": tick_epoch,
            "vol_traded_today": 1000,
        }
    )

    assert builder.closed_5s_queue.empty()

    assert builder.close_due_candles(bucket_epoch + 5) == 0
    assert SYMBOL not in builder.active_by_symbol
    assert SYMBOL in builder.pending_by_symbol

    builder.on_tick(
        {
            "symbol": SYMBOL,
            "ltp": 101.0,
            "exch_feed_time": bucket_epoch + 4,
            "vol_traded_today": 1015,
        }
    )
    assert builder.closed_5s_queue.empty()

    closed_count = builder.close_due_candles(bucket_epoch + 6)

    assert closed_count == 1
    candle = builder.closed_5s_queue.get_nowait()
    assert candle.symbol == SYMBOL
    assert candle.bucket_epoch == bucket_epoch
    assert (candle.open, candle.high, candle.low, candle.close, candle.tick_count) == (
        100.0,
        101.0,
        100.0,
        101.0,
        2,
    )
    assert candle.volume == 15
    assert candle.is_complete is True


def test_builder_marks_subscription_bucket_as_partial(monkeypatch):
    builder = make_builder()
    tick_epoch = market_epoch(9, 15, 1)
    bucket_epoch = tick_epoch - (tick_epoch % 5)
    monkeypatch.setattr(candle_builder_module.time, "time", lambda: bucket_epoch + 2)

    builder.set_subscribe_epoch(SYMBOL, tick_epoch)
    builder.on_tick(
        {
            "symbol": SYMBOL,
            "ltp": 100.0,
            "exch_feed_time": tick_epoch,
        }
    )
    builder.close_due_candles(bucket_epoch + 6)

    candle = builder.closed_5s_queue.get_nowait()
    assert candle.is_partial is True
    assert "subscribe_after_or_at_bucket_start" in candle.partial_reason
    assert candle.first_tick_epoch == tick_epoch
    assert candle.last_tick_epoch == tick_epoch
    assert "volume_baseline_missing_or_reset" not in candle.partial_reason


def test_builder_accumulates_volume_from_cumulative_total(monkeypatch):
    builder = make_builder()
    tick_epoch = market_epoch(9, 15, 1)
    next_bucket_epoch = (tick_epoch - (tick_epoch % 5)) + 5
    monkeypatch.setattr(candle_builder_module.time, "time", lambda: tick_epoch)

    builder.on_tick(
        {
            "symbol": OTHER_SYMBOL,
            "ltp": 200.0,
            "exch_feed_time": tick_epoch,
            "vol_traded_today": 1000,
        }
    )
    builder.on_tick(
        {
            "symbol": OTHER_SYMBOL,
            "ltp": 201.0,
            "exch_feed_time": next_bucket_epoch,
            "vol_traded_today": 1010,
        }
    )
    builder.on_tick(
        {
            "symbol": OTHER_SYMBOL,
            "ltp": 202.0,
            "exch_feed_time": next_bucket_epoch + 2,
            "vol_traded_today": 1025,
        }
    )
    builder.close_due_candles(next_bucket_epoch + 6)

    candles = [
        builder.closed_5s_queue.get_nowait(),
        builder.closed_5s_queue.get_nowait(),
    ]
    current = next(candle for candle in candles if candle.bucket_epoch == next_bucket_epoch)
    assert current.volume == 25
    assert current.tick_count == 2
    assert current.is_partial is False


def test_builder_ignores_volume_reset_without_marking_partial(monkeypatch):
    builder = make_builder()
    tick_epoch = market_epoch(9, 15, 1)
    next_bucket_epoch = (tick_epoch - (tick_epoch % 5)) + 5
    monkeypatch.setattr(candle_builder_module.time, "time", lambda: tick_epoch)

    builder.on_tick(
        {
            "symbol": OTHER_SYMBOL,
            "ltp": 200.0,
            "exch_feed_time": tick_epoch,
            "vol_traded_today": 1000,
        }
    )
    builder.on_tick(
        {
            "symbol": OTHER_SYMBOL,
            "ltp": 201.0,
            "exch_feed_time": next_bucket_epoch,
            "vol_traded_today": 900,
        }
    )
    builder.close_due_candles(next_bucket_epoch + 6)

    candles = [
        builder.closed_5s_queue.get_nowait(),
        builder.closed_5s_queue.get_nowait(),
    ]
    current = next(candle for candle in candles if candle.bucket_epoch == next_bucket_epoch)
    assert current.volume == 0
    assert current.is_partial is False
    assert current.partial_reason == ""
    assert builder.volume_reset_count == 1


def test_builder_ignores_ticks_outside_market_hours():
    builder = make_builder()

    builder.on_tick(
        {
            "symbol": SYMBOL,
            "ltp": 100.0,
            "exch_feed_time": market_epoch(8, 59, 59),
        }
    )

    try:
        builder.closed_5s_queue.get_nowait()
    except Empty:
        pass
    else:
        raise AssertionError("outside-market tick should not publish a candle")


def test_on_tick_only_scans_pending_closes(monkeypatch):
    builder = make_builder()

    def fail_active_scan(now_epoch):
        raise AssertionError("on_tick should not scan active candles")

    monkeypatch.setattr(builder, "_move_due_active_to_pending", fail_active_scan)
    builder.on_tick(
        {
            "symbol": SYMBOL,
            "ltp": 100.0,
            "exch_feed_time": market_epoch(9, 15, 1),
        }
    )


def test_tick_queue_put_is_non_blocking_when_full():
    tick_queue = Queue(maxsize=1)
    tick_queue.put_nowait({"already": "full"})
    builder = make_builder_with_tick_queue(tick_queue)

    builder.on_tick(
        {
            "symbol": SYMBOL,
            "ltp": 100.0,
            "exch_feed_time": market_epoch(9, 15, 1),
        }
    )

    assert builder.dropped_tick_queue_message_count == 1


def test_closed_queue_put_is_non_blocking_when_full(monkeypatch):
    closed_queue = Queue(maxsize=1)
    closed_queue.put_nowait({"already": "full"})
    builder = make_builder_with_closed_queue(closed_queue)
    tick_epoch = market_epoch(9, 15, 1)
    bucket_epoch = tick_epoch - (tick_epoch % 5)
    monkeypatch.setattr(candle_builder_module.time, "time", lambda: bucket_epoch + 2)

    builder.on_tick(
        {
            "symbol": SYMBOL,
            "ltp": 100.0,
            "exch_feed_time": tick_epoch,
            "vol_traded_today": 1000,
        }
    )
    builder.close_due_candles(bucket_epoch + 6)

    assert builder.dropped_closed_candle_count == 1
    assert builder.last_closed_bucket_by_symbol[SYMBOL] == bucket_epoch


def test_fast_disconnect_does_not_mark_partial(monkeypatch):
    builder = make_builder()
    tick_epoch = market_epoch(9, 15, 1)
    bucket_epoch = tick_epoch - (tick_epoch % 5)
    monkeypatch.setattr(candle_builder_module.time, "time", lambda: bucket_epoch + 2)

    builder.set_stream_disconnected(True, now_epoch=bucket_epoch + 2)
    builder.set_stream_disconnected(False, now_epoch=bucket_epoch + 2.5)
    builder.on_tick(
        {
            "symbol": SYMBOL,
            "ltp": 100.0,
            "exch_feed_time": tick_epoch,
        }
    )
    builder.close_due_candles(bucket_epoch + 6)

    candle = builder.closed_5s_queue.get_nowait()
    assert "stream_disconnected" not in candle.partial_reason


def test_disconnect_interval_marks_overlapping_candle_partial(monkeypatch):
    builder = make_builder()
    tick_epoch = market_epoch(9, 15, 1)
    bucket_epoch = tick_epoch - (tick_epoch % 5)
    monkeypatch.setattr(candle_builder_module.time, "time", lambda: bucket_epoch + 2)

    builder.set_stream_disconnected(True, now_epoch=bucket_epoch + 2)
    builder.set_stream_disconnected(False, now_epoch=bucket_epoch + 4)
    builder.on_tick(
        {
            "symbol": SYMBOL,
            "ltp": 100.0,
            "exch_feed_time": tick_epoch,
            "vol_traded_today": 1000,
        }
    )
    builder.close_due_candles(bucket_epoch + 6)

    candle = builder.closed_5s_queue.get_nowait()
    assert candle.is_partial is True
    assert "stream_disconnected" in candle.partial_reason


def test_default_symbol_gap_marks_other_symbol_candle_partial(monkeypatch):
    builder = make_builder()
    tick_epoch = market_epoch(9, 15, 1)
    bucket_epoch = tick_epoch - (tick_epoch % 5)
    monkeypatch.setattr(candle_builder_module.time, "time", lambda: bucket_epoch + 2)

    builder.on_tick(
        {
            "symbol": SYMBOL,
            "ltp": 100.0,
            "exch_feed_time": bucket_epoch + 1,
            "vol_traded_today": 1000,
        }
    )
    builder.on_tick(
        {
            "symbol": OTHER_SYMBOL,
            "ltp": 200.0,
            "exch_feed_time": bucket_epoch + 2,
            "vol_traded_today": 2000,
        }
    )
    builder.on_tick(
        {
            "symbol": SYMBOL,
            "ltp": 101.0,
            "exch_feed_time": bucket_epoch + 4,
            "vol_traded_today": 1010,
        }
    )
    builder.close_due_candles(bucket_epoch + 6)

    candles = [
        builder.closed_5s_queue.get_nowait(),
        builder.closed_5s_queue.get_nowait(),
    ]
    other = next(candle for candle in candles if candle.symbol == OTHER_SYMBOL)
    assert other.is_partial is True
    assert "default_symbol_tick_gap" in other.partial_reason


def test_partial_reasons_are_combined(monkeypatch):
    builder = make_builder()
    tick_epoch = market_epoch(9, 15, 1)
    bucket_epoch = tick_epoch - (tick_epoch % 5)
    monkeypatch.setattr(candle_builder_module.time, "time", lambda: bucket_epoch + 2)

    builder.set_subscribe_epoch(SYMBOL, tick_epoch)
    builder.set_stream_disconnected(True, now_epoch=bucket_epoch + 2)
    builder.set_stream_disconnected(False, now_epoch=bucket_epoch + 4)
    builder.on_tick(
        {
            "symbol": SYMBOL,
            "ltp": 100.0,
            "exch_feed_time": tick_epoch,
            "vol_traded_today": 1000,
        }
    )
    builder.close_due_candles(bucket_epoch + 6)

    candle = builder.closed_5s_queue.get_nowait()
    assert candle.is_partial is True
    assert (
        candle.partial_reason
        == "subscribe_after_or_at_bucket_start|stream_disconnected"
    )


def test_partial_intervals_are_deduped_and_pruned(monkeypatch):
    builder = make_builder()
    tick_epoch = market_epoch(9, 15, 1)
    bucket_epoch = tick_epoch - (tick_epoch % 5)
    monkeypatch.setattr(candle_builder_module.time, "time", lambda: bucket_epoch + 2)

    builder._record_default_symbol_gap(bucket_epoch + 1, bucket_epoch + 4)
    builder._record_default_symbol_gap(bucket_epoch + 1, bucket_epoch + 4)
    builder.set_stream_disconnected(True, now_epoch=bucket_epoch + 1)
    builder.set_stream_disconnected(False, now_epoch=bucket_epoch + 3)
    builder.set_stream_disconnected(True, now_epoch=bucket_epoch + 1)
    builder.set_stream_disconnected(False, now_epoch=bucket_epoch + 3)

    assert len(builder.default_symbol_gap_intervals) == 1
    assert len(builder.stream_disconnect_intervals) == 1

    builder.on_tick(
        {
            "symbol": SYMBOL,
            "ltp": 100.0,
            "exch_feed_time": tick_epoch,
        }
    )
    builder.close_due_candles(bucket_epoch + 6)
    builder.closed_5s_queue.get_nowait()

    assert builder.default_symbol_gap_intervals == []
    assert builder.stream_disconnect_intervals == []
