from trading_app.broker.candle_manager import CandleManager


def test_basic_ohlc():
    cm = CandleManager(timeframe_seconds=5, startup_epoch=100, debug=False)

    ticks = [
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 100.0, "exch_feed_time": 101},
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 103.0, "exch_feed_time": 102},
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 99.0, "exch_feed_time": 103},
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 101.0, "exch_feed_time": 104},
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 102.0, "exch_feed_time": 105},
    ]

    for t in ticks:
        cm.process_tick_message(t)

    closed = cm.pop_closed_candles()
    assert len(closed) == 1

    c = closed[0]
    assert (c.open, c.high, c.low, c.close, c.volume) == (100.0, 103.0, 99.0, 101.0, 4)


def test_stale_tick_does_not_corrupt_candle():
    cm = CandleManager(timeframe_seconds=5, startup_epoch=100, debug=False)

    ticks = [
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 100.0, "exch_feed_time": 101},
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 103.0, "exch_feed_time": 102},
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 99.0, "exch_feed_time": 103},
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 105.0, "exch_feed_time": 102},  # stale tick
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 101.0, "exch_feed_time": 104},
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 102.0, "exch_feed_time": 105},
    ]

    for t in ticks:
        cm.process_tick_message(t)

    closed = cm.pop_closed_candles()
    assert len(closed) == 1

    c = closed[0]
    assert (c.open, c.high, c.low, c.close, c.volume) == (100.0, 103.0, 99.0, 101.0, 4)
    assert c.is_complete is True


def test_old_tick_after_new_bucket_does_not_corrupt_live_candle():
    cm = CandleManager(timeframe_seconds=5, startup_epoch=100, debug=False)

    ticks = [
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 100.0, "exch_feed_time": 101},
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 103.0, "exch_feed_time": 102},
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 99.0, "exch_feed_time": 103},
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 101.0, "exch_feed_time": 105},
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 110.0, "exch_feed_time": 104},  # old tick
        {"symbol": "NSE:NIFTY50-INDEX", "ltp": 102.0, "exch_feed_time": 106},
    ]

    for t in ticks:
        cm.process_tick_message(t)

    closed = cm.pop_closed_candles()
    assert len(closed) == 1

    closed_candle = closed[0]
    assert (closed_candle.open, closed_candle.high, closed_candle.low, closed_candle.close, closed_candle.volume) == (
        100.0,
        103.0,
        99.0,
        99.0,
        3,
    )
    assert closed_candle.is_complete is True

    live = cm.get_live_candle("NSE:NIFTY50-INDEX")
    assert live is not None
    assert (live.open, live.high, live.low, live.close, live.volume) == (
        101.0,
        102.0,
        101.0,
        102.0,
        2,
    )
    assert live.bucket_epoch == 105
    assert live.is_complete is False