from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


DEFAULT_LOG_FORMAT = "%(message)s"
FILE_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOGGER_NAME = "trading_app"
DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_BASENAME = "trading_app"
DEFAULT_LOG_MAX_BYTES = 5 * 1024 * 1024

_CONFIGURED = False


def _get_level(env_name: str, default: str) -> int:
    level_name = os.getenv(env_name, default).upper()
    return getattr(logging, level_name, logging.INFO)


def _env_flag(env_name: str, default: str) -> bool:
    value = os.getenv(env_name, default).strip().lower()
    return value not in {"0", "false", "no", "off"}


def _ordinal(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")

    return f"{value}{suffix}"


class DailySizeRotatingFileHandler(logging.Handler):
    terminator = "\n"

    def __init__(
        self,
        *,
        log_dir: Path,
        base_name: str,
        max_bytes: int,
        encoding: str = "utf-8",
    ) -> None:
        super().__init__()
        self.log_dir = log_dir
        self.base_name = base_name
        self.max_bytes = max(0, int(max_bytes))
        self.encoding = encoding
        self._current_date: str | None = None
        self._current_path: Path | None = None
        self._stream = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record) + self.terminator
            pending_size = len(message.encode(self.encoding, errors="replace"))
            self._ensure_stream(pending_size=pending_size)

            if self._stream is not None:
                self._stream.write(message)
                self.flush()
        except Exception:
            self.handleError(record)

    def flush(self) -> None:
        if self._stream is not None:
            self._stream.flush()

    def close(self) -> None:
        try:
            if self._stream is not None:
                self._stream.close()
        finally:
            self._stream = None
            super().close()

    def ensure_file(self) -> Path:
        self._ensure_stream(pending_size=0)
        if self._current_path is None:
            raise RuntimeError("Log file path was not initialized.")
        return self._current_path

    def _ensure_stream(self, *, pending_size: int) -> None:
        date_text = datetime.now().strftime("%Y-%m-%d")

        if date_text != self._current_date:
            self._close_stream()
            self._current_date = date_text

        if self._stream is None:
            self._open_stream(date_text)
            return

        if self._should_rollover(pending_size=pending_size):
            self._close_stream()
            self._open_stream(date_text)

    def _open_stream(self, date_text: str) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_path = self._select_log_path(date_text)
        self._stream = self._current_path.open(
            mode="a",
            encoding=self.encoding,
        )

    def _close_stream(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    def _should_rollover(self, *, pending_size: int) -> bool:
        if self.max_bytes <= 0 or self._current_path is None:
            return False

        current_size = (
            self._current_path.stat().st_size
            if self._current_path.exists()
            else 0
        )

        return current_size + pending_size > self.max_bytes

    def _select_log_path(self, date_text: str) -> Path:
        file_index = 1

        while True:
            suffix = "" if file_index == 1 else f"_{_ordinal(file_index)}"
            path = self.log_dir / f"{date_text}_{self.base_name}{suffix}.log"

            if (
                self.max_bytes <= 0
                or not path.exists()
                or path.stat().st_size < self.max_bytes
            ):
                return path

            file_index += 1


def configure_logging() -> None:
    global _CONFIGURED

    if _CONFIGURED:
        return

    load_dotenv()

    level = _get_level("TRADING_APP_LOG_LEVEL", "INFO")
    file_level = _get_level("TRADING_APP_FILE_LOG_LEVEL", "INFO")
    console_format = os.getenv("TRADING_APP_LOG_FORMAT", DEFAULT_LOG_FORMAT)

    root_logger = logging.getLogger(LOGGER_NAME)
    root_logger.setLevel(min(level, file_level))
    root_logger.propagate = False
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(console_format))
    root_logger.addHandler(console_handler)

    if _env_flag("TRADING_APP_LOG_TO_FILE", "1"):
        configured_file = os.getenv("TRADING_APP_LOG_FILE", "").strip()
        configured_path = Path(configured_file) if configured_file else None
        log_dir = Path(os.getenv("TRADING_APP_LOG_DIR", "") or DEFAULT_LOG_DIR)
        base_name = os.getenv("TRADING_APP_LOG_BASENAME", "") or DEFAULT_LOG_BASENAME

        if configured_path is not None:
            log_dir = configured_path.parent
            base_name = configured_path.stem

        file_handler = DailySizeRotatingFileHandler(
            log_dir=log_dir,
            base_name=base_name,
            max_bytes=int(
                os.getenv("TRADING_APP_LOG_MAX_BYTES", str(DEFAULT_LOG_MAX_BYTES))
            ),
        )
        file_handler.setLevel(file_level)
        file_handler.setFormatter(
            logging.Formatter(os.getenv("TRADING_APP_FILE_LOG_FORMAT", FILE_LOG_FORMAT))
        )
        file_handler.ensure_file()
        root_logger.addHandler(file_handler)

    _CONFIGURED = True


def get_logger(name: str | None = None) -> logging.Logger:
    configure_logging()

    if not name or name == LOGGER_NAME:
        return logging.getLogger(LOGGER_NAME)

    if name.startswith(f"{LOGGER_NAME}."):
        return logging.getLogger(name)

    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def _format_parts(parts: tuple[Any, ...], *, sep: str = " ", end: str = "") -> str:
    return sep.join(str(part) for part in parts) + end


def log_debug(
    logger: logging.Logger,
    *parts: Any,
    sep: str = " ",
    end: str = "",
    **_: Any,
) -> None:
    logger.debug(_format_parts(parts, sep=sep, end=end))


def log_info(
    logger: logging.Logger,
    *parts: Any,
    sep: str = " ",
    end: str = "",
    **_: Any,
) -> None:
    logger.info(_format_parts(parts, sep=sep, end=end))


def log_warning(
    logger: logging.Logger,
    *parts: Any,
    sep: str = " ",
    end: str = "",
    **_: Any,
) -> None:
    logger.warning(_format_parts(parts, sep=sep, end=end))


def log_error(
    logger: logging.Logger,
    *parts: Any,
    sep: str = " ",
    end: str = "",
    **_: Any,
) -> None:
    logger.error(_format_parts(parts, sep=sep, end=end))
