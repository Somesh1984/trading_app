


from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FyersSymbol:
    symbol: str
    display_name: str = ""
    exchange: str = ""
    segment: str = ""
    token: str = ""


@dataclass(frozen=True)
class FyersAuthTokens:
    access_token: str
    refresh_token: str = ""


@dataclass
class MarketTick:
    symbol: str = ""
    ltp: float = 0.0
    prev_close_price: float = 0.0
    ch: float = 0.0
    chp: float = 0.0
    exch_feed_time: int = 0
    high_price: float = 0.0
    low_price: float = 0.0
    open_price: float = 0.0
    type: str = ""

    @classmethod
    def from_message(cls, message: dict[str, Any]) -> "MarketTick":
        return cls(
            symbol=str(message.get("symbol", "")),
            ltp=float(message.get("ltp", 0.0) or 0.0),
            prev_close_price=float(message.get("prev_close_price", 0.0) or 0.0),
            ch=float(message.get("ch", 0.0) or 0.0),
            chp=float(message.get("chp", 0.0) or 0.0),
            exch_feed_time=int(message.get("exch_feed_time", 0) or 0),
            high_price=float(message.get("high_price", 0.0) or 0.0),
            low_price=float(message.get("low_price", 0.0) or 0.0),
            open_price=float(message.get("open_price", 0.0) or 0.0),
            type=str(message.get("type", "")),
        )


@dataclass
class LiveCandle:
    symbol: str
    bucket_epoch: int
    timeframe_seconds: int
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    is_complete: bool = True

    def update(self, price: float) -> None:
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        self.close = price
        self.volume += 1


@dataclass
class PaperTrade:
    symbol: str
    side: str
    qty: int
    entry_price: float
    entry_minute_epoch: int
    stop_loss: float = 0.0
    take_profit: float = 0.0


@dataclass
class ClosedPaperTrade:
    symbol: str
    side: str
    qty: int
    entry_price: float
    exit_price: float
    entry_minute_epoch: int
    exit_minute_epoch: int
    pnl: float