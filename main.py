import time

from trading_app.broker.candle_manager import CandleManager
from trading_app.broker.websocket import FyersWebSocketManager


SYMBOL = "NSE:NIFTY50-INDEX"
TIMEFRAME_SECONDS = 30


def main() -> None:
    startup_epoch = int(time.time())

    ws = FyersWebSocketManager()
    candle_manager = CandleManager(timeframe_seconds=TIMEFRAME_SECONDS,startup_epoch=startup_epoch,)

    def on_data(message: dict) -> None:
        symbol = str(message.get("symbol", ""))

        if symbol != SYMBOL:
            return

        candle_manager.put_tick_message(message)
        candle_manager.process_pending_ticks()

        closed_candles = candle_manager.pop_closed_candles()
        for candle in closed_candles:
            print(
                "CLOSED CANDLE:",
                candle.symbol,
                candle.bucket_epoch,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                flush=True,)

    print("STARTING 5-SECOND CANDLE DEBUG RUNNER", flush=True)
    print("SYMBOL:", SYMBOL, flush=True)
    print("TIMEFRAME_SECONDS:", TIMEFRAME_SECONDS, flush=True)
    print("STARTUP_EPOCH:", startup_epoch, flush=True)

    try:
        ws.connect_data_socket(
            symbols=[SYMBOL],
            on_message=on_data,
            litemode=False,
            data_type="SymbolUpdate",
        )
    except KeyboardInterrupt:
        print("\nSTOPPING SYSTEM...", flush=True)


if __name__ == "__main__":
    main()