
from __future__ import annotations

import threading
from queue import Queue

from trading_app.broker.websocket import (
    FyersWebSocketManager,
    RawMessage,
)


DEFAULT_DATA_TYPE = "SymbolUpdate"
DEFAULT_LITEMODE = False


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

    def _on_data(self, message: RawMessage) -> None:
        self.tick_queue.put(dict(message))

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