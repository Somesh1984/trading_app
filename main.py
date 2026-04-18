
from trading_app.execution.paper_engine import PaperExecutionEngine
from trading_app.pnf.test_strategy import PreviousCandleBreakoutStrategy
from trading_app.broker.websocket import FyersWebSocketManager


def main() -> None:
    ws = FyersWebSocketManager(candle_seconds=60)
    engine = PaperExecutionEngine()
    strategy = PreviousCandleBreakoutStrategy()

    def on_data(message: dict) -> None:
        symbol = str(message.get("symbol", ""))
        ltp = float(message.get("ltp", 0))
        exch_feed_time = int(message.get("exch_feed_time", 0))

        engine.process_tick(symbol, ltp, exch_feed_time)

        closed_candles = ws.pop_complete_closed_candles()
        for candle in closed_candles:
            signal = strategy.get_signal(candle)
            engine.process_candle(candle, signal)

    ws.connect_data_socket(
        symbols=["NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX"],
        on_message=on_data,
        litemode=False,
        data_type="SymbolUpdate",
    )


if __name__ == "__main__":
    main()