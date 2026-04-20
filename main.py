# from datetime import date, datetime, time, timedelta
# from zoneinfo import ZoneInfo

# from trading_app.broker.broker import Broker
# from trading_app.broker.symbol_pd import FyersSymbolService
# from trading_app.broker.websocket import FyersWebSocketManager
# from trading_app.execution.paper_engine import PaperExecutionEngine
# from trading_app.models import LiveCandle
# from trading_app.pnf.test_strategy import PreviousCandleBreakoutStrategy


# MARKET_TZ = ZoneInfo("Asia/Kolkata")
# MARKET_START_TIME = time(9, 15)


# def get_market_now() -> datetime:
#     return datetime.now(MARKET_TZ)


# def is_live_trading_time() -> bool:
#     return get_market_now().time() >= MARKET_START_TIME


# def main() -> None:
#     ws = FyersWebSocketManager(candle_seconds=60)
#     engine = PaperExecutionEngine()
#     strategy = PreviousCandleBreakoutStrategy()
#     symbol_service = FyersSymbolService()
#     broker = Broker()

#     index_prices = broker.get_index_spot_prices()

#     final_symbols = symbol_service.build_subscription_symbols(
#                                                             index_prices=index_prices,
#                                                             include_spot=True,
#                                                             base_count=5,
#                                                             )

#     subscribed_symbols = set(final_symbols)
#     historical_loaded_symbols = set(final_symbols)

#     index_state: dict[str, dict] = {
#                                     "NIFTY": {
#                                                 "spot_symbol": "NSE:NIFTY50-INDEX",
#                                                 "day_open_price": index_prices["NIFTY"]["open"],
#                                                 "subscribed_strikes": set(),
#                                                 },
#                                     "SENSEX": {
#                                                 "spot_symbol": "BSE:SENSEX-INDEX",
#                                                 "day_open_price": index_prices["SENSEX"]["open"],
#                                                 "subscribed_strikes": set(),
#                                                 },
#                                     }

#     initial_nifty = symbol_service.expand_subscription_range(
#                                                             index_name="NIFTY",
#                                                             day_open_price=index_state["NIFTY"]["day_open_price"],
#                                                             current_spot_price=index_prices["NIFTY"]["current"],
#                                                             subscribed_strikes=set(),
#                                                             base_count=5,
#                                                             )
#     index_state["NIFTY"]["subscribed_strikes"] = set(initial_nifty["all_strikes"])

#     initial_sensex = symbol_service.expand_subscription_range(
#                                                             index_name="SENSEX",
#                                                             day_open_price=index_state["SENSEX"]["day_open_price"],
#                                                             current_spot_price=index_prices["SENSEX"]["current"],
#                                                             subscribed_strikes=set(),
#                                                             base_count=5,
#                                                             )
#     index_state["SENSEX"]["subscribed_strikes"] = set(initial_sensex["all_strikes"])

#     def backfill_symbols(symbols: list[str]) -> None:
#         if not symbols:
#             return

#         print("BACKFILL START:", symbols)

#         today = date.today()
#         start_date = today - timedelta(days=5)

#         history_data = broker.get_history_for_symbols(
#                                                     symbols=symbols,
#                                                     resolution="1",
#                                                     date_from=start_date,
#                                                     date_to=today,
#                                                     )

#         for symbol, payload in history_data.items():
#             candles = payload if isinstance(payload, list) else payload.get("candles", [])

#             for row in candles:
#                 candle = LiveCandle(
#                                     symbol=symbol,
#                                     bucket_epoch=int(row[0]),
#                                     timeframe_seconds=60,
#                                     open=float(row[1]),
#                                     high=float(row[2]),
#                                     low=float(row[3]),
#                                     close=float(row[4]),
#                                     )

#                 strategy.get_signal(candle)

#         historical_loaded_symbols.update(symbols)

#         print("BACKFILL DONE:", symbols)

#     today = date.today()
#     start_date = today - timedelta(days=5)

#     history_data = broker.get_history_for_symbols(
#                                                 symbols=final_symbols,
#                                                 resolution="1",
#                                                 date_from=start_date,
#                                                 date_to=today,
#                                                 )

#     print("HISTORICAL SYMBOLS:")
#     for symbol, payload in history_data.items():
#         candles = payload if isinstance(payload, list) else payload.get("candles", [])
#         print(symbol, len(candles))

#     # for symbol, payload in history_data.items():
#     #     candles = payload if isinstance(payload, list) else payload.get("candles", [])

#     #     for row in candles[:2]:
#     #         print("HIST ROW:", row)

#     #     for row in candles:
#     #         candle = LiveCandle(
#     #                             symbol=symbol,
#     #                             bucket_epoch=int(row[0]),
#     #                             timeframe_seconds=60,
#     #                             open=float(row[1]),
#     #                             high=float(row[2]),
#     #                             low=float(row[3]),
#     #                             close=float(row[4]),
#     #                             )

#     #         strategy.get_signal(candle)
#     for symbol, payload in history_data.items():
#         candles = payload if isinstance(payload, list) else payload.get("candles", [])

#         if candles:
#             print("LAST HIST CANDLE:", symbol, candles[-1])

#         for row in candles:
#             candle = LiveCandle(
#                                 symbol=symbol,
#                                 bucket_epoch=int(row[0]),
#                                 timeframe_seconds=60,
#                                 open=float(row[1]),
#                                 high=float(row[2]),
#                                 low=float(row[3]),
#                                 close=float(row[4]),
#                                 )

#             strategy.get_signal(candle)

#     print("HISTORICAL WARMUP DONE")

#     live_trading_enabled = is_live_trading_time()
#     print("LIVE TRADING ENABLED:", live_trading_enabled)

#     def on_data(message: dict) -> None:
#         nonlocal live_trading_enabled

#         symbol = str(message.get("symbol", ""))
#         ltp = float(message.get("ltp", 0))
#         exch_feed_time = int(message.get("exch_feed_time", 0))

#         engine.process_tick(symbol, ltp, exch_feed_time)

#         if symbol == index_state["NIFTY"]["spot_symbol"]:
#             expand_result = symbol_service.expand_subscription_range(
#                                                                     index_name="NIFTY",
#                                                                     day_open_price=float(index_state["NIFTY"]["day_open_price"]),
#                                                                     current_spot_price=ltp,
#                                                                     subscribed_strikes=set(index_state["NIFTY"]["subscribed_strikes"]),
#                                                                     base_count=5,
#                                                                     )

#             if expand_result["range_expanded"]:
#                 new_symbols = [s for s in expand_result["new_symbols"] if s not in subscribed_symbols]

#                 if new_symbols:
#                     print("NEW NIFTY SYMBOLS ADDED:", new_symbols)
#                     ws.subscribe_symbols(new_symbols)
#                     subscribed_symbols.update(new_symbols)

#                     missing_backfill = [s for s in new_symbols if s not in historical_loaded_symbols]
#                     backfill_symbols(missing_backfill)

#                 index_state["NIFTY"]["subscribed_strikes"] = set(expand_result["all_strikes"])

#         elif symbol == index_state["SENSEX"]["spot_symbol"]:
#             expand_result = symbol_service.expand_subscription_range(
#                                                                     index_name="SENSEX",
#                                                                     day_open_price=float(index_state["SENSEX"]["day_open_price"]),
#                                                                     current_spot_price=ltp,
#                                                                     subscribed_strikes=set(index_state["SENSEX"]["subscribed_strikes"]),
#                                                                     base_count=5,
#                                                                     )

#             if expand_result["range_expanded"]:
#                 new_symbols = [s for s in expand_result["new_symbols"] if s not in subscribed_symbols]

#                 if new_symbols:
#                     print("NEW SENSEX SYMBOLS ADDED:", new_symbols)
#                     ws.subscribe_symbols(new_symbols)
#                     subscribed_symbols.update(new_symbols)

#                     missing_backfill = [s for s in new_symbols if s not in historical_loaded_symbols]
#                     backfill_symbols(missing_backfill)

#                 index_state["SENSEX"]["subscribed_strikes"] = set(expand_result["all_strikes"])

#         if not live_trading_enabled and is_live_trading_time():
#             live_trading_enabled = True
#             print("LIVE TRADING STARTED")

#         closed_candles = ws.pop_complete_closed_candles()
#         for candle in closed_candles:
#             signal = strategy.get_signal(candle)

#             if live_trading_enabled:
#                 engine.process_candle(candle, signal)

#     try:
#         ws.connect_data_socket(
#                                 symbols=final_symbols,
#                                 on_message=on_data,
#                                 litemode=False,
#                                 data_type="SymbolUpdate",
#                                 )
#     except KeyboardInterrupt:
#         print("\nSTOPPING SYSTEM...")


# if __name__ == "__main__":
#     main()


from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from trading_app.broker.broker import Broker
from trading_app.broker.symbol_pd import FyersSymbolService
from trading_app.broker.websocket import FyersWebSocketManager
from trading_app.execution.paper_engine import PaperExecutionEngine
from trading_app.models import LiveCandle
from trading_app.pnf.test_strategy import PreviousCandleBreakoutStrategy


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

    index_prices = broker.get_index_spot_prices()

    final_symbols = symbol_service.build_subscription_symbols(
                                                            index_prices=index_prices,
                                                            include_spot=True,
                                                            base_count=5,
                                                            )

    subscribed_symbols = set(final_symbols)
    historical_loaded_symbols = set(final_symbols)

    index_state: dict[str, dict] = {
                                    "NIFTY": {
                                                "spot_symbol": "NSE:NIFTY50-INDEX",
                                                "day_open_price": index_prices["NIFTY"]["open"],
                                                "subscribed_strikes": set(),
                                                },
                                    "SENSEX": {
                                                "spot_symbol": "BSE:SENSEX-INDEX",
                                                "day_open_price": index_prices["SENSEX"]["open"],
                                                "subscribed_strikes": set(),
                                                },
                                    }

    initial_nifty = symbol_service.expand_subscription_range(
                                                            index_name="NIFTY",
                                                            day_open_price=index_state["NIFTY"]["day_open_price"],
                                                            current_spot_price=index_prices["NIFTY"]["current"],
                                                            subscribed_strikes=set(),
                                                            base_count=5,
                                                            )
    index_state["NIFTY"]["subscribed_strikes"] = set(initial_nifty["all_strikes"])

    initial_sensex = symbol_service.expand_subscription_range(
                                                            index_name="SENSEX",
                                                            day_open_price=index_state["SENSEX"]["day_open_price"],
                                                            current_spot_price=index_prices["SENSEX"]["current"],
                                                            subscribed_strikes=set(),
                                                            base_count=5,
                                                            )
    index_state["SENSEX"]["subscribed_strikes"] = set(initial_sensex["all_strikes"])

    def backfill_symbols(symbols: list[str]) -> None:
        if not symbols:
            return

        print("BACKFILL START:", symbols)

        today = date.today()
        start_date = today - timedelta(days=5)

        history_data = broker.get_history_for_symbols(
                                                    symbols=symbols,
                                                    resolution="1",
                                                    date_from=start_date,
                                                    date_to=today,
                                                    )

        for symbol, df in history_data.items():
            if not isinstance(df, pd.DataFrame) or df.empty:
                continue

            for row in df.itertuples(index=False):
                candle = LiveCandle(
                                    symbol=str(row.symbol),
                                    bucket_epoch=int(row.timestamp),
                                    timeframe_seconds=60,
                                    open=float(row.open),
                                    high=float(row.high),
                                    low=float(row.low),
                                    close=float(row.close),
                                    )

                strategy.get_signal(candle)

        historical_loaded_symbols.update(symbols)

        print("BACKFILL DONE:", symbols)

    today = date.today()
    start_date = today - timedelta(days=5)

    history_data = broker.get_history_for_symbols(
                                                symbols=final_symbols,
                                                resolution="1",
                                                date_from=start_date,
                                                date_to=today,
                                                )

    print("HISTORICAL SYMBOLS:")
    for symbol, df in history_data.items():
        candles_count = len(df) if isinstance(df, pd.DataFrame) else 0
        print(symbol, candles_count)

    for symbol, df in history_data.items():
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue

        print("LAST HIST CANDLE:", symbol, df.iloc[-1].to_dict())

        for row in df.itertuples(index=False):
            candle = LiveCandle(
                                symbol=str(row.symbol),
                                bucket_epoch=int(row.timestamp),
                                timeframe_seconds=60,
                                open=float(row.open),
                                high=float(row.high),
                                low=float(row.low),
                                close=float(row.close),
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

        if symbol == index_state["NIFTY"]["spot_symbol"]:
            expand_result = symbol_service.expand_subscription_range(
                                                                    index_name="NIFTY",
                                                                    day_open_price=float(index_state["NIFTY"]["day_open_price"]),
                                                                    current_spot_price=ltp,
                                                                    subscribed_strikes=set(index_state["NIFTY"]["subscribed_strikes"]),
                                                                    base_count=5,
                                                                    )

            if expand_result["range_expanded"]:
                new_symbols = [s for s in expand_result["new_symbols"] if s not in subscribed_symbols]

                if new_symbols:
                    print("NEW NIFTY SYMBOLS ADDED:", new_symbols)
                    ws.subscribe_symbols(new_symbols)
                    subscribed_symbols.update(new_symbols)

                    missing_backfill = [s for s in new_symbols if s not in historical_loaded_symbols]
                    backfill_symbols(missing_backfill)

                index_state["NIFTY"]["subscribed_strikes"] = set(expand_result["all_strikes"])

        elif symbol == index_state["SENSEX"]["spot_symbol"]:
            expand_result = symbol_service.expand_subscription_range(
                                                                    index_name="SENSEX",
                                                                    day_open_price=float(index_state["SENSEX"]["day_open_price"]),
                                                                    current_spot_price=ltp,
                                                                    subscribed_strikes=set(index_state["SENSEX"]["subscribed_strikes"]),
                                                                    base_count=5,
                                                                    )

            if expand_result["range_expanded"]:
                new_symbols = [s for s in expand_result["new_symbols"] if s not in subscribed_symbols]

                if new_symbols:
                    print("NEW SENSEX SYMBOLS ADDED:", new_symbols)
                    ws.subscribe_symbols(new_symbols)
                    subscribed_symbols.update(new_symbols)

                    missing_backfill = [s for s in new_symbols if s not in historical_loaded_symbols]
                    backfill_symbols(missing_backfill)

                index_state["SENSEX"]["subscribed_strikes"] = set(expand_result["all_strikes"])

        if not live_trading_enabled and is_live_trading_time():
            live_trading_enabled = True
            print("LIVE TRADING STARTED")

        closed_candles = ws.pop_complete_closed_candles()
        for candle in closed_candles:
            signal = strategy.get_signal(candle)

            if live_trading_enabled:
                engine.process_candle(candle, signal)

    try:
        ws.connect_data_socket(
                                symbols=final_symbols,
                                on_message=on_data,
                                litemode=False,
                                data_type="SymbolUpdate",
                                )
    except KeyboardInterrupt:
        print("\nSTOPPING SYSTEM...")


if __name__ == "__main__":
    main()