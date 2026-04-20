
from __future__ import annotations

from typing import Callable, Iterable

from fyers_apiv3.FyersWebsocket import data_ws, order_ws

from .auth import generate_access_token
from ..models import LiveCandle, MarketTick
from ..settings import FYERS_CLIENT_ID, validate_settings


class FyersWebSocketManager:
    def __init__(self, candle_seconds: int = 60) -> None:
        self._access_token: str | None = None
        self._data_socket = None
        self._order_socket = None

        self._latest_ticks: dict[str, MarketTick] = {}
        self._latest_candles: dict[str, LiveCandle] = {}
        self._closed_candles: list[LiveCandle] = []

        self._candle_seconds = candle_seconds
        self._session_start_seconds = 9 * 3600 + 15 * 60  # 09:15

    def get_latest_tick(self, symbol: str) -> MarketTick | None:
        return self._latest_ticks.get(symbol)

    def get_all_latest_ticks(self) -> dict[str, MarketTick]:
        return dict(self._latest_ticks)

    def get_latest_candle(self, symbol: str) -> LiveCandle | None:
        return self._latest_candles.get(symbol)

    def get_closed_candles(self) -> list[LiveCandle]:
        return list(self._closed_candles)

    def pop_closed_candles(self) -> list[LiveCandle]:
        candles = list(self._closed_candles)
        self._closed_candles.clear()
        return candles

    def pop_complete_closed_candles(self) -> list[LiveCandle]:
        candles = self.pop_closed_candles()
        return [candle for candle in candles if candle.is_complete]

    def _get_ws_token(self) -> str:
        if self._access_token is None:
            validate_settings()
            token = generate_access_token()
            self._access_token = f"{FYERS_CLIENT_ID}:{token}"
        return self._access_token

    def refresh_token(self) -> str:
        validate_settings()
        token = generate_access_token()
        self._access_token = f"{FYERS_CLIENT_ID}:{token}"
        return self._access_token

    def _get_bucket_epoch(self, epoch: int) -> int:
        session_day_start = (epoch // 86400) * 86400
        session_anchor = session_day_start + self._session_start_seconds

        if epoch < session_anchor:
            return (epoch // self._candle_seconds) * self._candle_seconds

        offset = epoch - session_anchor
        return session_anchor + (offset // self._candle_seconds) * self._candle_seconds

    def _is_incomplete_start(self, epoch: int, bucket_epoch: int) -> bool:
        return epoch != bucket_epoch

    def _update_latest_tick(self, message: dict) -> MarketTick | None:
        symbol = str(message.get("symbol", "")).strip()
        if not symbol:
            return None

        tick = MarketTick.from_message(message)
        self._latest_ticks[symbol] = tick
        return tick

    def _update_candle_from_tick(self, tick: MarketTick) -> LiveCandle | None:
        if not tick.symbol or tick.exch_feed_time <= 0:
            return None

        bucket_epoch = self._get_bucket_epoch(tick.exch_feed_time)
        current = self._latest_candles.get(tick.symbol)

        if current is None:
            candle = LiveCandle(
                symbol=tick.symbol,
                bucket_epoch=bucket_epoch,
                timeframe_seconds=self._candle_seconds,
                open=tick.ltp,
                high=tick.ltp,
                low=tick.ltp,
                close=tick.ltp,
                volume=1,
                is_complete=not self._is_incomplete_start(
                    tick.exch_feed_time, bucket_epoch
                ),
            )
            self._latest_candles[tick.symbol] = candle
            return candle

        if current.bucket_epoch == bucket_epoch:
            current.update(tick.ltp)
            return current

        self._closed_candles.append(current)

        candle = LiveCandle(
            symbol=tick.symbol,
            bucket_epoch=bucket_epoch,
            timeframe_seconds=self._candle_seconds,
            open=tick.ltp,
            high=tick.ltp,
            low=tick.ltp,
            close=tick.ltp,
            volume=1,
            is_complete=True,
        )
        self._latest_candles[tick.symbol] = candle
        return candle


    def subscribe_symbols(self, symbols: list[str]) -> None:
        if not symbols:
            return

        unique_symbols = list(dict.fromkeys(symbols))
        self.data_socket.subscribe(
                                    symbol=unique_symbols,
                                    data_type="SymbolUpdate",)

    def connect_data_socket(
        self,
        symbols: Iterable[str],
        *,
        on_message: Callable[[dict], None],
        on_error: Callable[[object], None] | None = None,
        on_close: Callable[[object], None] | None = None,
        on_open: Callable[[], None] | None = None,
        litemode: bool = False,
        data_type: str = "SymbolUpdate",
    ):
        symbols = list(symbols)

        def _on_open():
            self._data_socket.subscribe(symbols=symbols, data_type=data_type)
            self._data_socket.keep_running()
            if on_open is not None:
                on_open()

        def _on_message(message: dict) -> None:
            tick = self._update_latest_tick(message)
            if tick is not None:
                self._update_candle_from_tick(tick)
            on_message(message)

        self._data_socket = data_ws.FyersDataSocket(
            access_token=self._get_ws_token(),
            log_path="",
            litemode=litemode,
            write_to_file=False,
            reconnect=True,
            on_connect=_on_open,
            on_close=on_close or (lambda message: print("DATA CLOSE:", message)),
            on_error=on_error or (lambda message: print("DATA ERROR:", message)),
            on_message=_on_message,
        )

        self._data_socket.connect()
        return self._data_socket

    def connect_order_socket(
        self,
        *,
        on_order: Callable[[dict], None] | None = None,
        on_trade: Callable[[dict], None] | None = None,
        on_position: Callable[[dict], None] | None = None,
        on_general: Callable[[dict], None] | None = None,
        on_error: Callable[[object], None] | None = None,
        on_close: Callable[[object], None] | None = None,
        on_open: Callable[[], None] | None = None,
    ):
        def _on_orders(message):
            if on_order is not None:
                on_order(message)
            elif on_general is not None:
                on_general(message)
            else:
                print("ORDER UPDATE:", message)

        def _on_trades(message):
            if on_trade is not None:
                on_trade(message)
            elif on_general is not None:
                on_general(message)
            else:
                print("TRADE UPDATE:", message)

        def _on_positions(message):
            if on_position is not None:
                on_position(message)
            elif on_general is not None:
                on_general(message)
            else:
                print("POSITION UPDATE:", message)

        self._order_socket = order_ws.FyersOrderSocket(
            access_token=self._get_ws_token(),
            write_to_file=False,
            log_path="",
            on_connect=on_open or (lambda: print("ORDER SOCKET CONNECTED")),
            on_close=on_close or (lambda message: print("ORDER CLOSE:", message)),
            on_error=on_error or (lambda message: print("ORDER ERROR:", message)),
            on_orders=_on_orders,
            on_trades=_on_trades,
            on_positions=_on_positions,
        )

        self._order_socket.connect()
        return self._order_socket