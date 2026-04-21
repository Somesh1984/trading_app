

import time
import os
import pandas as pd

from trading_app.broker.candle_manager import CandleManager
from trading_app.broker.candle_runner import CandleRunner
from trading_app.broker.market_stream import MarketStream


SYMBOL = "NSE:NIFTY50-INDEX"


def append_candle_to_csv(filename: str, candle) -> None:
    row = pd.DataFrame(
        [{
            "symbol": candle.symbol,
            "bucket_epoch": candle.bucket_epoch,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
        }]
    )

    file_exists = os.path.exists(filename)

    row.to_csv(
        filename,
        mode="a",
        header=not file_exists,
        index=False,
    )


def main() -> None:
    stream = MarketStream(symbols=[SYMBOL])
    stream.start()

    time.sleep(5)
    startup_epoch = int(time.time())

    candle_5s = CandleManager(timeframe_seconds=5,startup_epoch=startup_epoch,)
    candle_1m = CandleManager(timeframe_seconds=60,startup_epoch=startup_epoch,)

    candle_runner = CandleRunner(tick_queue=stream.tick_queue,
                                 candle_managers={"5s": candle_5s,"1m": candle_1m,},poll_interval=0.05,)
    candle_runner.start()

    print("STARTING MARKET STREAM", flush=True)
    print("SYMBOL:", SYMBOL, flush=True)
    print("TIMEFRAMES: 5s, 1m", flush=True)

    candle_store_5s = []
    candle_store_1m = []

    try:
        while True:
            candles_5s = candle_runner.pop_closed_candles("5s")
            for candle in candles_5s:
                candle_store_5s.append(candle)
                append_candle_to_csv("candles_5s.csv", candle)

            candles_1m = candle_runner.pop_closed_candles("1m")
            for candle in candles_1m:
                candle_store_1m.append(candle)
                append_candle_to_csv("candles_1m.csv", candle)

            time.sleep(0.1)

    except KeyboardInterrupt:
        candle_runner.stop()
        print("\nSTOPPING SYSTEM...", flush=True)


if __name__ == "__main__":
    main()
