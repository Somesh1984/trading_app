
from __future__ import annotations

from trading_app.logger import get_logger, log_debug, log_error, log_info, log_warning

logger = get_logger(__name__)


import threading
import time
from queue import Queue

from trading_app.broker.auth import FyersAuthError
from trading_app.broker.websocket import (
    FyersWebSocketManager,
    RawMessage,
)


DEFAULT_DATA_TYPE = "SymbolUpdate"
DEFAULT_LITEMODE = False
RAW_DEBUG_MESSAGE_LIMIT = 5
MIN_RESTART_INTERVAL_SECONDS = 30


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
        self._lock = threading.RLock()
        self._generation = 0
        self.raw_message_count = 0
        self.tick_message_count = 0
        self.last_message_time: float | None = None
        self.last_error: str | None = None
        self.last_restart_time = 0.0
        self.restart_count = 0

    def _is_current_generation(self, generation: int) -> bool:
        return generation == self._generation

    def _on_data(self, message: RawMessage, generation: int) -> None:
        if not self._is_current_generation(generation):
            return

        raw_message = dict(message)
        self.raw_message_count += 1
        self.last_message_time = time.time()

        if self.raw_message_count <= RAW_DEBUG_MESSAGE_LIMIT:
            log_debug(logger, "Market stream raw message:", raw_message, flush=True)

        if raw_message.get("symbol") and raw_message.get("ltp"):
            self.tick_message_count += 1

        self.tick_queue.put(raw_message)

    def _on_open(self, generation: int) -> None:
        if not self._is_current_generation(generation):
            return

        log_info(logger,
            "Market stream websocket connected:",
            f"symbols={len(self.symbols)}",
            flush=True,
        )

    def _on_error(self, error: object, generation: int) -> None:
        if not self._is_current_generation(generation):
            return

        log_error(logger, "Market stream websocket error:", error, flush=True)

    def _on_close(self, message: object, generation: int) -> None:
        if not self._is_current_generation(generation):
            return

        log_warning(logger, "Market stream websocket closed:", message, flush=True)

    def _connect_socket(self, generation: int) -> None:
        try:
            self.ws.connect_data_socket(
                symbols=self.symbols,
                on_message=lambda message: self._on_data(message, generation),
                on_error=lambda error: self._on_error(error, generation),
                on_close=lambda message: self._on_close(message, generation),
                on_open=lambda: self._on_open(generation),
                litemode=DEFAULT_LITEMODE,
                data_type=DEFAULT_DATA_TYPE,
                reconnect=False,
            )
        except FyersAuthError as exc:
            if self._is_current_generation(generation):
                self.last_error = str(exc)
                log_error(logger, "Market stream auth failed:", exc, flush=True)
        except Exception as exc:
            if self._is_current_generation(generation):
                self.last_error = f"{type(exc).__name__}: {exc}"
                log_error(logger, "Market stream failed:", self.last_error, flush=True)

    def start(self) -> None:
        with self._lock:
            if self.is_alive():
                return

            self._generation += 1
            generation = self._generation

            self._thread = threading.Thread(
                target=self._connect_socket,
                args=(generation,),
                name="MarketStreamSocket",
                daemon=True,
            )

            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._generation += 1

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

    def message_age(self) -> float | None:
        if self.last_message_time is None:
            return None

        return time.time() - self.last_message_time

    def should_restart(
        self,
        *,
        stale_after_seconds: float,
    ) -> bool:
        now = time.time()

        if now - self.last_restart_time < MIN_RESTART_INTERVAL_SECONDS:
            return False

        age = self.message_age()

        if age is not None and age >= stale_after_seconds:
            return True

        return not self.is_connected() and age is not None

    def restart(self, reason: str) -> bool:
        now = time.time()

        if now - self.last_restart_time < MIN_RESTART_INTERVAL_SECONDS:
            return False

        self.last_restart_time = now
        self.restart_count += 1

        log_warning(logger,
            "Market stream watchdog restart:",
            f"reason={reason}",
            f"count={self.restart_count}",
            flush=True,
        )

        self.stop()
        self.ws = FyersWebSocketManager()
        self.start()

        return True
