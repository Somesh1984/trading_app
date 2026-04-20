from datetime import date, timedelta

from trading_app.broker.broker import Broker
from trading_app.broker.symbol_pd import FyersSymbolService
from trading_app.broker.websocket import FyersWebSocketManager
from trading_app.execution.paper_engine import PaperExecutionEngine
from trading_app.models import LiveCandle
from trading_app.pnf.test_strategy import PreviousCandleBreakoutStrategy
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo




MARKET_TZ = ZoneInfo("Asia/Kolkata")
MARKET_START_TIME = time(9, 15)


def get_market_now() -> datetime:
    return datetime.now(MARKET_TZ)


def is_live_trading_time() -> bool:
    return get_market_now().time() >= MARKET_START_TIME






def main() -> None:
    ws = FyersWebSocketManager(candle_seconds=60)
    engine = PaperExecutionEngine()
    strategy = PreviousCandleBreakoutStrategy()
    symbol_service = FyersSymbolService()
    broker = Broker()

    index_symbols = symbol_service.get_spot_index_symbols()

    today = date.today()
    start_date = today - timedelta(days=5)

    history_data = broker.get_history_for_symbols(
                                                symbols=index_symbols,
                                                resolution="1",
                                                date_from=start_date,
                                                date_to=today,
                                                )

    print("HISTORICAL SYMBOLS:")
    for symbol, payload in history_data.items():
        candles = payload if isinstance(payload, list) else payload.get("candles", [])
        print(symbol, len(candles))

    for symbol, payload in history_data.items():
        candles = payload if isinstance(payload, list) else payload.get("candles", [])

        for row in candles[:2]:
            print("HIST ROW:", row)

        for row in candles:
            candle = LiveCandle(
                                symbol=symbol,
                                bucket_epoch=int(row[0]),
                                timeframe_seconds=60,
                                open=float(row[1]),
                                high=float(row[2]),
                                low=float(row[3]),
                                close=float(row[4]),
                                )

            strategy.get_signal(candle)

    print("HISTORICAL WARMUP DONE")
    live_trading_enabled = is_live_trading_time()
    print("LIVE TRADING ENABLED:", live_trading_enabled)

    def on_data(message: dict) -> None:
        nonlocal live_trading_enabled

        symbol = str(message.get("symbol", ""))
        ltp = float(message.get("ltp", 0))
        exch_feed_time = int(message.get("exch_feed_time", 0))

        engine.process_tick(symbol, ltp, exch_feed_time)

        if not live_trading_enabled and is_live_trading_time():
            live_trading_enabled = True
            print("LIVE TRADING STARTED")

        closed_candles = ws.pop_complete_closed_candles()
        for candle in closed_candles:
            signal = strategy.get_signal(candle)

            if live_trading_enabled:
                engine.process_candle(candle, signal)

    ws.connect_data_socket(
                            symbols=index_symbols,
                            on_message=on_data,
                            litemode=False,
                            data_type="SymbolUpdate",
                            )


if __name__ == "__main__":
    main()