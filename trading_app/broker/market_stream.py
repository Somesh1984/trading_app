from __future__ import annotations

import threading
from queue import Queue
from typing import Any

from trading_app.broker.websocket import FyersWebSocketManager


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
        self.tick_queue: Queue[dict[str, Any]] = Queue()
        self._thread: threading.Thread | None = None

    def _on_data(self, message: dict[str, Any]) -> None:
        self.tick_queue.put(message)

    def _run_socket(self) -> None:
        self.ws.connect_data_socket(
            symbols=self.symbols,
            on_message=self._on_data,
            litemode=False,
            data_type="SymbolUpdate",
        )

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._thread = threading.Thread(
            target=self._run_socket,
            name="market-stream-thread",
            daemon=True,
        )
        self._thread.start()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()