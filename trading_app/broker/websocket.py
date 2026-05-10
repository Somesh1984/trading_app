
from __future__ import annotations

from typing import Callable, Iterable,TypeAlias

from fyers_apiv3.FyersWebsocket import data_ws, order_ws

from .auth import generate_access_token
from ..models import MarketTick
from ..settings import FYERS_CLIENT_ID, validate_settings

RawMessage = dict[str, object]
DataMessageHandler = Callable[[RawMessage], None]
SocketEventHandler = Callable[[object], None]
SocketOpenHandler = Callable[[], None]
AnyCallback = Callable[..., None]


class FyersWebSocketManager:
    def __init__(self) -> None:
        self._access_token: str | None = None
        self._data_socket = None
        self._order_socket = None
        self._latest_ticks: dict[str, MarketTick] = {}

    # ---------------------------
    # Public read helpers
    # ---------------------------
    def get_latest_tick(self, symbol: str) -> MarketTick | None:
        return self._latest_ticks.get(symbol)

    def get_all_latest_ticks(self) -> dict[str, MarketTick]:
        return dict(self._latest_ticks)

    def clear_latest_ticks(self) -> None:
        self._latest_ticks.clear()

    # ---------------------------
    # Internal utility helpers
    # ---------------------------
    def _normalize_symbols(self, symbols: Iterable[str]) -> list[str]:
        return list(
            dict.fromkeys(
                str(symbol).strip()
                for symbol in symbols
                if str(symbol).strip()
            )
        )

    def _run_callback(
        self,
        callback: AnyCallback | None,
        *args,
    ) -> None:
        if callback is not None:
            callback(*args)

    # ---------------------------
    # Default socket handlers
    # ---------------------------
    def _default_data_close(self, message: object) -> None:
        print("DATA CLOSE:", message, flush=True)

    def _default_data_error(self, message: object) -> None:
        print("DATA ERROR:", message, flush=True)

    def _default_order_open(self) -> None:
        print("ORDER SOCKET CONNECTED", flush=True)

    def _default_order_close(self, message: object) -> None:
        print("ORDER CLOSE:", message, flush=True)

    def _default_order_error(self, message: object) -> None:
        print("ORDER ERROR:", message, flush=True)

    # ---------------------------
    # Data socket internal handlers
    # ---------------------------
    def _handle_data_message(
        self,
        message: dict,
        callback: DataMessageHandler,
    ) -> None:
        self._update_latest_tick(message)
        self._run_callback(callback, message)

    def _handle_data_open(
        self,
        symbols: list[str],
        data_type: str,
        callback: SocketOpenHandler | None,
    ) -> None:
        if symbols:
            self._data_socket.subscribe(
                symbols=symbols,
                data_type=data_type,
            )

        self._data_socket.keep_running()
        self._run_callback(callback)

    def _update_latest_tick(
        self,
        message: dict,
    ) -> MarketTick | None:
        symbol = str(message.get("symbol", "")).strip()

        if not symbol:
            return None

        tick = MarketTick.from_message(message)
        self._latest_ticks[symbol] = tick

        return tick

    # ---------------------------
    # Order socket internal handlers
    # ---------------------------
    def _handle_order_message(
        self,
        message: dict,
        specific_handler: DataMessageHandler | None,
        general_handler: DataMessageHandler | None,
        default_label: str,
    ) -> None:
        if specific_handler is not None:
            self._run_callback(specific_handler, message)
        elif general_handler is not None:
            self._run_callback(general_handler, message)
        else:
            print(f"{default_label}:", message, flush=True)

    # ---------------------------
    # Auth / token helpers
    # ---------------------------
    def _get_ws_token(self) -> str:
        if self._access_token is None:
            validate_settings()
            token = generate_access_token()
            self._access_token = f"{FYERS_CLIENT_ID}:{token}"

        return self._access_token

    def refresh_token(self) -> str:
        validate_settings()
        token = generate_access_token(force_refresh=True)
        self._access_token = f"{FYERS_CLIENT_ID}:{token}"

        return self._access_token

    # ---------------------------
    # Subscription helpers
    # ---------------------------
    def subscribe_symbols(
        self,
        symbols: Iterable[str],
        *,
        data_type: str = "SymbolUpdate",
    ) -> None:
        if self._data_socket is None:
            raise RuntimeError("Data socket is not connected yet.")

        unique_symbols = self._normalize_symbols(symbols)
        if not unique_symbols:
            return

        self._data_socket.subscribe(
            symbols=unique_symbols,
            data_type=data_type,
        )

    def unsubscribe_symbols(
        self,
        symbols: Iterable[str],
        *,
        data_type: str = "SymbolUpdate",
    ) -> None:
        if self._data_socket is None:
            raise RuntimeError("Data socket is not connected yet.")

        unique_symbols = self._normalize_symbols(symbols)
        if not unique_symbols:
            return

        self._data_socket.unsubscribe(
            symbols=unique_symbols,
            data_type=data_type,
        )

    # ---------------------------
    # Data socket
    # ---------------------------
    def connect_data_socket(
        self,
        symbols: Iterable[str],
        *,
        on_message: DataMessageHandler,
        on_error: SocketEventHandler | None = None,
        on_close: SocketEventHandler | None = None,
        on_open: SocketOpenHandler | None = None,
        litemode: bool = False,
        data_type: str = "SymbolUpdate",
    ):
        initial_symbols = self._normalize_symbols(symbols)

        def _on_open() -> None:
            self._handle_data_open(
                initial_symbols,
                data_type,
                on_open,
            )

        def _on_message(message: dict) -> None:
            self._handle_data_message(message, on_message)

        self._data_socket = data_ws.FyersDataSocket(
            access_token=self._get_ws_token(),
            log_path="",
            litemode=litemode,
            write_to_file=False,
            reconnect=True,
            on_connect=_on_open,
            on_close=on_close or self._default_data_close,
            on_error=on_error or self._default_data_error,
            on_message=_on_message,
        )

        self._data_socket.connect()
        return self._data_socket

    def disconnect_data_socket(self) -> None:
        if self._data_socket is not None:
            self._data_socket.close_connection()
            self._data_socket = None

        self.clear_latest_ticks()

    # ---------------------------
    # Order socket
    # ---------------------------
    def connect_order_socket(
        self,
        *,
        on_order: DataMessageHandler | None = None,
        on_trade: DataMessageHandler | None = None,
        on_position: DataMessageHandler | None = None,
        on_general: DataMessageHandler | None = None,
        on_error: SocketEventHandler | None = None,
        on_close: SocketEventHandler | None = None,
        on_open: SocketOpenHandler | None = None,
    ):
        def _on_orders(message: dict) -> None:
            self._handle_order_message(
                message,
                on_order,
                on_general,
                "ORDER UPDATE",
            )

        def _on_trades(message: dict) -> None:
            self._handle_order_message(
                message,
                on_trade,
                on_general,
                "TRADE UPDATE",
            )

        def _on_positions(message: dict) -> None:
            self._handle_order_message(
                message,
                on_position,
                on_general,
                "POSITION UPDATE",
            )

        self._order_socket = order_ws.FyersOrderSocket(
            access_token=self._get_ws_token(),
            write_to_file=False,
            log_path="",
            on_connect=on_open or self._default_order_open,
            on_close=on_close or self._default_order_close,
            on_error=on_error or self._default_order_error,
            on_orders=_on_orders,
            on_trades=_on_trades,
            on_positions=_on_positions,
        )

        self._order_socket.connect()
        return self._order_socket

    def disconnect_order_socket(self) -> None:
        if self._order_socket is not None:
            self._order_socket.close_connection()
            self._order_socket = None

