from __future__ import annotations

import csv
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from typing import Any
from zoneinfo import ZoneInfo

from trading_app.broker.auth import FyersAuthError
from trading_app.broker.candle_builder import Live5sCandleBuilder
from trading_app.broker.symbol_list import nifty_50
from trading_app.broker.websocket import FyersWebSocketManager, RawMessage
from trading_app.logger import get_logger, log_debug, log_error, log_info, log_warning
from trading_app.models import LiveCandle


logger = get_logger(__name__)

IST = ZoneInfo("Asia/Kolkata")

DEFAULT_SYMBOL = os.getenv("MAIN3_DEFAULT_SYMBOL", "NSE:NIFTY50-INDEX").strip()
CSV_FILE = Path(os.getenv("MAIN3_5S_CSV", "candles_5s.csv"))
STATUS_INTERVAL_SECONDS = float(os.getenv("MAIN3_STATUS_INTERVAL_SECONDS", "5"))
STREAM_STALE_RESTART_SECONDS = float(
    os.getenv("MAIN3_STREAM_STALE_RESTART_SECONDS", "25")
)
MIN_RESTART_INTERVAL_SECONDS = float(
    os.getenv("MAIN3_MIN_RESTART_INTERVAL_SECONDS", "30")
)
POLL_INTERVAL_SECONDS = float(os.getenv("MAIN3_POLL_INTERVAL_SECONDS", "0.05"))
DATA_TYPE = os.getenv("MAIN3_DATA_TYPE", "SymbolUpdate")
LITEMODE = os.getenv("MAIN3_LITEMODE", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

CSV_COLUMNS = [
    "symbol",
    "bucket_epoch",
    "ist_time",
    "bucket_close_ist",
    "open",
    "high",
    "low",
    "close",
    "tick_count",
    "is_complete",
    "first_tick_epoch",
    "first_tick_ist",
    "last_tick_epoch",
    "last_tick_ist",
    "is_partial",
    "partial_reason",
]


def epoch_to_ist_text(epoch: int | None) -> str:
    if epoch is None or epoch <= 0:
        return ""

    return datetime.fromtimestamp(epoch, IST).strftime("%Y-%m-%d %H:%M:%S")


def parse_symbols() -> list[str]:
    raw_symbols = os.getenv("MAIN3_SYMBOLS", "").strip()
    if not raw_symbols:
        symbols = list(nifty_50)
    else:
        symbols = [
            symbol.strip()
            for symbol in raw_symbols.replace("\n", ",").split(",")
            if symbol.strip()
        ]

    symbols = [DEFAULT_SYMBOL, *symbols]
    return list(dict.fromkeys(symbols)) or [DEFAULT_SYMBOL]


def candle_to_row(candle: LiveCandle) -> dict[str, Any]:
    bucket_close_epoch = candle.bucket_epoch + candle.timeframe_seconds
    first_tick_epoch = int(candle.first_tick_epoch or 0)
    last_tick_epoch = int(candle.last_tick_epoch or 0)

    return {
        "symbol": candle.symbol,
        "bucket_epoch": candle.bucket_epoch,
        "ist_time": epoch_to_ist_text(candle.bucket_epoch),
        "bucket_close_ist": epoch_to_ist_text(bucket_close_epoch),
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "tick_count": candle.tick_count,
        "is_complete": candle.is_complete,
        "first_tick_epoch": first_tick_epoch,
        "first_tick_ist": epoch_to_ist_text(first_tick_epoch),
        "last_tick_epoch": last_tick_epoch,
        "last_tick_ist": epoch_to_ist_text(last_tick_epoch),
        "is_partial": candle.is_partial,
        "partial_reason": candle.partial_reason,
    }


def load_last_written_buckets(csv_file: Path) -> dict[str, int]:
    if not csv_file.exists():
        return {}

    last_by_symbol: dict[str, int] = {}

    try:
        with csv_file.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                symbol = str(row.get("symbol", "")).strip()
                if not symbol:
                    continue

                try:
                    bucket_epoch = int(float(row.get("bucket_epoch", 0) or 0))
                except ValueError:
                    continue

                last_by_symbol[symbol] = max(
                    bucket_epoch,
                    last_by_symbol.get(symbol, 0),
                )
    except OSError as exc:
        log_warning(logger, "CSV read failed:", csv_file, exc, flush=True)

    return last_by_symbol


def append_candles_to_csv(csv_file: Path, candles: list[LiveCandle]) -> None:
    if not candles:
        return

    csv_file.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_file.exists() or csv_file.stat().st_size == 0
    fieldnames = CSV_COLUMNS

    if not write_header:
        try:
            with csv_file.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                existing_header = next(reader, None)
                if existing_header:
                    fieldnames = existing_header
        except OSError as exc:
            log_warning(logger, "CSV header read failed:", csv_file, exc, flush=True)

    with csv_file.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        if write_header:
            writer.writeheader()

        for candle in candles:
            row = candle_to_row(candle)
            if "volume" in fieldnames and "volume" not in row:
                row["volume"] = ""
            writer.writerow(row)


def drain_closed_candles(
    closed_queue: Queue[LiveCandle],
    *,
    last_written_by_symbol: dict[str, int],
) -> list[LiveCandle]:
    candles: list[LiveCandle] = []

    while True:
        try:
            candle = closed_queue.get_nowait()
        except Empty:
            break

        last_written = last_written_by_symbol.get(candle.symbol)
        if last_written is not None and candle.bucket_epoch <= last_written:
            log_debug(
                logger,
                "SKIP DUPLICATE 5S:",
                f"symbol={candle.symbol}",
                f"bucket={candle.bucket_epoch}",
                flush=True,
            )
            continue

        candles.append(candle)
        last_written_by_symbol[candle.symbol] = candle.bucket_epoch

    candles.sort(key=lambda item: (item.bucket_epoch, item.symbol))
    return candles


class BuilderWebSocketStream:
    def __init__(
        self,
        *,
        symbols: list[str],
        builder: Live5sCandleBuilder,
    ) -> None:
        self.symbols = list(dict.fromkeys(symbols))
        self.builder = builder
        self.ws = FyersWebSocketManager()
        self.raw_message_count = 0
        self.tick_message_count = 0
        self.last_message_time: float | None = None
        self.last_error: str | None = None
        self.restart_count = 0
        self.last_restart_time = 0.0

        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._generation = 0

    def start(self) -> None:
        with self._lock:
            if self.is_alive():
                return

            self._generation += 1
            generation = self._generation
            self._thread = threading.Thread(
                target=self._connect,
                args=(generation,),
                name="BuilderWebSocketStream",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._generation += 1
            self.builder.set_stream_disconnected(True)

            try:
                self.ws.disconnect_data_socket()
                if (
                    self._thread is not None
                    and self._thread is not threading.current_thread()
                ):
                    self._thread.join(timeout=2)
            finally:
                self._thread = None

    def restart(self, reason: str) -> bool:
        now = time.time()
        if now - self.last_restart_time < MIN_RESTART_INTERVAL_SECONDS:
            return False

        self.last_restart_time = now
        self.restart_count += 1
        log_warning(
            logger,
            "STREAM RESTART:",
            f"reason={reason}",
            f"count={self.restart_count}",
            flush=True,
        )

        self.stop()
        self.ws = FyersWebSocketManager()
        self.start()
        return True

    def should_restart(self) -> bool:
        age = self.message_age()
        if age is not None and age >= STREAM_STALE_RESTART_SECONDS:
            return True

        return not self.is_connected() and age is not None

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def is_connected(self) -> bool:
        return self.ws.is_data_connected()

    def latest_tick_count(self) -> int:
        return self.ws.get_latest_tick_count()

    def message_age(self) -> float | None:
        if self.last_message_time is None:
            return None

        return time.time() - self.last_message_time

    def _is_current_generation(self, generation: int) -> bool:
        return generation == self._generation

    def _connect(self, generation: int) -> None:
        try:
            self.ws.connect_data_socket(
                self.symbols,
                on_message=lambda message: self._on_message(message, generation),
                on_error=lambda error: self._on_error(error, generation),
                on_close=lambda message: self._on_close(message, generation),
                on_open=lambda: self._on_open(generation),
                litemode=LITEMODE,
                data_type=DATA_TYPE,
                reconnect=False,
            )
        except FyersAuthError as exc:
            if self._is_current_generation(generation):
                self.last_error = str(exc)
                log_error(logger, "FYERS AUTH ERROR:", exc, flush=True)
        except Exception as exc:
            if self._is_current_generation(generation):
                self.last_error = f"{type(exc).__name__}: {exc}"
                log_error(logger, "STREAM CONNECT FAILED:", self.last_error, flush=True)

    def _on_open(self, generation: int) -> None:
        if not self._is_current_generation(generation):
            return

        subscribe_epoch = int(time.time())
        for symbol in self.symbols:
            self.builder.set_subscribe_epoch(symbol, subscribe_epoch)

        self.builder.set_stream_disconnected(False)
        log_info(
            logger,
            "WEBSOCKET CONNECTED:",
            f"symbols={len(self.symbols)}",
            f"subscribe_ist={epoch_to_ist_text(subscribe_epoch)}",
            flush=True,
        )

    def _on_message(self, message: RawMessage, generation: int) -> None:
        if not self._is_current_generation(generation):
            return

        self.raw_message_count += 1
        self.last_message_time = time.time()

        if message.get("symbol") and message.get("ltp"):
            self.tick_message_count += 1

        self.builder.on_tick(dict(message))

    def _on_error(self, error: object, generation: int) -> None:
        if not self._is_current_generation(generation):
            return

        self.last_error = str(error)
        self.builder.set_stream_disconnected(True)
        log_error(logger, "WEBSOCKET ERROR:", error, flush=True)

    def _on_close(self, message: object, generation: int) -> None:
        if not self._is_current_generation(generation):
            return

        self.builder.set_stream_disconnected(True)
        log_warning(logger, "WEBSOCKET CLOSED:", message, flush=True)


def main() -> None:
    symbols = parse_symbols()
    closed_5s_queue: Queue[LiveCandle] = Queue()
    last_written_by_symbol = load_last_written_buckets(CSV_FILE)

    builder = Live5sCandleBuilder(
        closed_5s_queue=closed_5s_queue,
        default_symbol=DEFAULT_SYMBOL,
        timeframe_seconds=5,
        close_grace_seconds=1,
    )
    stream = BuilderWebSocketStream(symbols=symbols, builder=builder)

    total_written_5s = 0
    last_status_time = time.time()
    last_status_raw = 0
    last_status_ticks = 0
    last_status_written = 0

    log_info(logger, "MAIN3 5S BUILDER STARTING", flush=True)
    log_info(logger, "SYMBOL COUNT:", len(symbols), flush=True)
    log_info(logger, "DEFAULT SYMBOL:", DEFAULT_SYMBOL, flush=True)
    log_info(logger, "5S CSV:", CSV_FILE, flush=True)

    stream.start()

    try:
        while True:
            builder.close_due_candles()
            written_candles = drain_closed_candles(
                closed_5s_queue,
                last_written_by_symbol=last_written_by_symbol,
            )
            append_candles_to_csv(CSV_FILE, written_candles)
            total_written_5s += len(written_candles)

            if written_candles:
                latest = written_candles[-1]
                log_info(
                    logger,
                    "5S CSV WRITE:",
                    f"count={len(written_candles)}",
                    f"latest_symbol={latest.symbol}",
                    f"latest_open={epoch_to_ist_text(latest.bucket_epoch)}",
                    f"latest_close={epoch_to_ist_text(latest.bucket_epoch + 5)}",
                    flush=True,
                )

            stream_restarted = False
            if stream.should_restart():
                age = stream.message_age()
                reason = (
                    "stale_messages"
                    if age is not None and age >= STREAM_STALE_RESTART_SECONDS
                    else "disconnected"
                )
                stream_restarted = stream.restart(reason)

            now = time.time()
            if now - last_status_time >= STATUS_INTERVAL_SECONDS:
                builder_stats = builder.snapshot_stats()
                interval_raw = stream.raw_message_count - last_status_raw
                interval_ticks = stream.tick_message_count - last_status_ticks
                interval_written = total_written_5s - last_status_written
                last_msg_age = (
                    None
                    if stream.last_message_time is None
                    else round(now - stream.last_message_time, 2)
                )

                log_info(
                    logger,
                    "MAIN3 STATUS:",
                    f"connected={stream.is_connected()}",
                    f"last_msg_age={last_msg_age}",
                    f"raw={interval_raw}",
                    f"ticks={interval_ticks}",
                    f"latest_ticks={stream.latest_tick_count()}",
                    f"closed_queue={closed_5s_queue.qsize()}",
                    f"active_symbols={builder_stats['active_symbols']}",
                    f"pending_symbols={builder_stats['pending_symbols']}",
                    f"late_ticks={builder_stats['ignored_late_ticks']}",
                    f"stale_ticks={builder_stats['ignored_stale_ticks']}",
                    f"dropped_queue={builder_stats['dropped_tick_queue_messages']}",
                    f"dropped_closed={builder_stats['dropped_closed_candles']}",
                    f"written_5s={interval_written}",
                    f"total_5s={total_written_5s}",
                    f"restarts={stream.restart_count}",
                    f"restarted={stream_restarted}",
                    flush=True,
                )

                last_status_time = now
                last_status_raw = stream.raw_message_count
                last_status_ticks = stream.tick_message_count
                last_status_written = total_written_5s

            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        log_info(logger, "\nMAIN3 STOPPING...", flush=True)
    finally:
        stream.stop()


if __name__ == "__main__":
    main()
