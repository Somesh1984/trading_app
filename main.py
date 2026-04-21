

import time

from trading_app.broker.candle_manager import CandleManager
from trading_app.broker.candle_runner import CandleRunner
from trading_app.broker.market_stream import MarketStream


SYMBOL = "NSE:NIFTY50-INDEX"


def main() -> None:
    stream = MarketStream(symbols=[SYMBOL])
    stream.start()

    time.sleep(5)
    startup_epoch = int(time.time())

    candle_5s = CandleManager(
        timeframe_seconds=5,
        startup_epoch=startup_epoch,
    )
    candle_1m = CandleManager(
        timeframe_seconds=60,
        startup_epoch=startup_epoch,
    )

    candle_runner = CandleRunner(
        tick_queue=stream.tick_queue,
        candle_managers={
            "5s": candle_5s,
            "1m": candle_1m,
        },
        poll_interval=0.05,
    )
    candle_runner.start()

    print("STARTING MARKET STREAM", flush=True)
    print("SYMBOL:", SYMBOL, flush=True)
    print("TIMEFRAMES: 5s, 1m", flush=True)

    try:
        while True:
            candles_5s = candle_runner.pop_closed_candles("5s")
            for candle in candles_5s:
                print(
                    "5S CLOSED:",
                    candle.symbol,
                    candle.bucket_epoch,
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    flush=True,
                )

            candles_1m = candle_runner.pop_closed_candles("1m")
            for candle in candles_1m:
                print(
                    "1M CLOSED:",
                    candle.symbol,
                    candle.bucket_epoch,
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    flush=True,
                )

            time.sleep(0.1)

    except KeyboardInterrupt:
        candle_runner.stop()
        print("\nSTOPPING SYSTEM...", flush=True)


if __name__ == "__main__":
    main()