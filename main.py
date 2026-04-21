

import time

from trading_app.broker.candle_manager import CandleManager
from trading_app.broker.market_stream import MarketStream


SYMBOL = "NSE:NIFTY50-INDEX"


def main() -> None:
    

    stream = MarketStream(symbols=[SYMBOL])
    stream.start()
    time.sleep(5) # to maintain websocket on 
    startup_epoch = int(time.time())

    candle_5s = CandleManager(timeframe_seconds=5,startup_epoch=startup_epoch,)
    candle_1m = CandleManager(timeframe_seconds=60,startup_epoch=startup_epoch,)

    print("STARTING MARKET STREAM", flush=True)
    print("SYMBOL:", SYMBOL, flush=True)
    print("TIMEFRAMES: 5s, 1m", flush=True)
    

    try:
        while True:
            while not stream.tick_queue.empty():
                message = stream.tick_queue.get()

                candle_5s.process_tick_message(message)
                candle_1m.process_tick_message(message)

            candles_5s = candle_5s.pop_closed_candles()
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

            candles_1m = candle_1m.pop_closed_candles()
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

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nSTOPPING SYSTEM...", flush=True)


if __name__ == "__main__":
    main()