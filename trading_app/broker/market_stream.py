
from __future__ import annotations

import threading
import time
from queue import Queue

from trading_app.broker.websocket import (
    FyersWebSocketManager,
    RawMessage,
)


DEFAULT_DATA_TYPE = "SymbolUpdate"
DEFAULT_LITEMODE = False
RAW_DEBUG_MESSAGE_LIMIT = 5


class MarketStream:
    """
    Raw market stream.

    Responsibility:
    - websocket ko background thread me start karna
    - raw messages ko tick_queue me daalna
    """

    def __init__(self, *, symbols: list[str]) -> None:
        self.symbols = list(dict.fromkeys(symbols))
        self.ws = FyersWebSocketManager()
        self.tick_queue: Queue[RawMessage] = Queue()
        self._thread: threading.Thread | None = None
        self.raw_message_count = 0
        self.tick_message_count = 0
        self.last_message_time: float | None = None

    def _on_data(self, message: RawMessage) -> None:
        raw_message = dict(message)
        self.raw_message_count += 1
        self.last_message_time = time.time()

        if self.raw_message_count <= RAW_DEBUG_MESSAGE_LIMIT:
            print("Market stream raw message:", raw_message, flush=True)

        if raw_message.get("symbol") and raw_message.get("ltp"):
            self.tick_message_count += 1

        self.tick_queue.put(raw_message)

    def _on_open(self) -> None:
        print(
            "Market stream websocket connected:",
            f"symbols={len(self.symbols)}",
            flush=True,
        )

    def _on_error(self, error: object) -> None:
        print("Market stream websocket error:", error, flush=True)

    def _on_close(self, message: object) -> None:
        print("Market stream websocket closed:", message, flush=True)

    def _connect_socket(self) -> None:
        self.ws.connect_data_socket(
            symbols=self.symbols,
            on_message=self._on_data,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open,
            litemode=DEFAULT_LITEMODE,
            data_type=DEFAULT_DATA_TYPE,
        )

    def start(self) -> None:
        if self.is_alive():
            return

        self._thread = threading.Thread(
            target=self._connect_socket,
            name="MarketStreamSocket",
            daemon=True,
        )

        self._thread.start()

    def stop(self) -> None:
        try:
            self.ws.disconnect_data_socket()

            if (
                self._thread is not None
                and self._thread is not threading.current_thread()
            ):
                self._thread.join(timeout=2)

        finally:
            self._thread = None

    def is_alive(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
        )

    def is_connected(self) -> bool:
        return self.ws.is_data_connected()

    def latest_tick_count(self) -> int:
        return self.ws.get_latest_tick_count()
