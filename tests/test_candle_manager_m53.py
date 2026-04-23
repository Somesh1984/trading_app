from trading_app.broker.candle_manager import CandleManager


def test_5s_bucket_aligns_to_915_session_anchor():
    cm = CandleManager(timeframe_seconds=5, startup_epoch=1745379907, debug=False)

    assert cm._get_bucket_epoch("NSE:NIFTY50-INDEX", 1745379907) == 1745379905
    assert cm._get_bucket_epoch("NSE:NIFTY50-INDEX", 1745379909) == 1745379905
    assert cm._get_bucket_epoch("NSE:NIFTY50-INDEX", 1745379910) == 1745379910


def test_1m_bucket_aligns_to_915_not_clock_hour():
    cm = CandleManager(timeframe_seconds=60, startup_epoch=1745379967, debug=False)

    assert cm._get_bucket_epoch("NSE:NIFTY50-INDEX", 1745379900) == 1745379900
    assert cm._get_bucket_epoch("NSE:NIFTY50-INDEX", 1745379959) == 1745379900
    assert cm._get_bucket_epoch("NSE:NIFTY50-INDEX", 1745379960) == 1745379960


def test_5m_aggregation_bucket_aligns_to_915_chain():
    cm_1m = CandleManager(timeframe_seconds=60, startup_epoch=1745379901, debug=False)
    cm_5m = CandleManager(timeframe_seconds=300, startup_epoch=1745379900, debug=False)

    cm_1m.downstream_managers.append(cm_5m)

    source_buckets = [
        1745379900,
        1745379960,
        1745380020,
        1745380080,
        1745380140,
        1745380200,
    ]

    for i, bucket in enumerate(source_buckets):
        cm_5m.aggregate_closed_candle(
            source_candle=type(
                "DummyCandle",
                (),
                {
                    "symbol": "NSE:NIFTY50-INDEX",
                    "bucket_epoch": bucket,
                    "timeframe_seconds": 60,
                    "open": 100 + i,
                    "high": 101 + i,
                    "low": 99 + i,
                    "close": 100 + i,
                    "volume": 1,
                    "is_complete": True,
                },
            )()
        )

    closed = cm_5m.pop_closed_candles()
    assert len(closed) == 1
    assert closed[0].bucket_epoch == 1745379900


def test_5m_alignment_via_live_tick_flow():
    cm_5s = CandleManager(timeframe_seconds=5, startup_epoch=1745379900, debug=False)
    cm_5m = CandleManager(timeframe_seconds=300, startup_epoch=1745379900, debug=False)

    # direct aggregation (no 1m in between)
    cm_5s.downstream_managers.append(cm_5m)

    symbol = "NSE:NIFTY50-INDEX"
    start_epoch = 1745379901
    end_epoch = 1745380266

    price = 100.0
    for epoch in range(start_epoch, end_epoch + 1, 5):
        cm_5s.process_tick_message(
            {
                "symbol": symbol,
                "ltp": price,
                "exch_feed_time": epoch,
            }
        )
        price += 1.0

    closed_5m = cm_5m.pop_closed_candles()
    assert len(closed_5m) == 1
    assert closed_5m[0].bucket_epoch == 1745379900


def test_5m_chain_emits_after_1m_chain_progresses():
    cm_5s = CandleManager(timeframe_seconds=5, startup_epoch=1745379900, debug=False)
    cm_1m = CandleManager(timeframe_seconds=60, startup_epoch=1745379900, debug=False)
    cm_5m = CandleManager(timeframe_seconds=300, startup_epoch=1745379900, debug=False)

    cm_5s.downstream_managers.append(cm_1m)
    cm_1m.downstream_managers.append(cm_5m)

    symbol = "NSE:NIFTY50-INDEX"
    start_epoch = 1745379901
    end_epoch = 1745380266

    price = 100.0
    for epoch in range(start_epoch, end_epoch + 1, 5):
        cm_5s.process_tick_message(
            {
                "symbol": symbol,
                "ltp": price,
                "exch_feed_time": epoch,
            }
        )
        price += 1.0

    closed_1m = cm_1m.pop_closed_candles()
    closed_5m = cm_5m.pop_closed_candles()

    assert len(closed_1m) >= 5
    assert len(closed_5m) == 1
    assert closed_5m[0].bucket_epoch == 1745379900