from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


SymbolKind = Literal["equity", "index_spot", "future", "option"]


@dataclass(slots=True)
class FyersBaseSymbol:
    symbol: str
    display_name: str
    exchange_code: str
    segment_code: str
    token: str
    short_symbol: str = ""
    lot_size: int = 0
    tick_size: float = 0.0
    last_updated: str = ""
    trading_session: str = ""
    fy_token_underlying: str = ""
    raw_exchange: str = ""
    raw_segment: str = ""

    @property
    def kind(self) -> SymbolKind:
        raise NotImplementedError


@dataclass(slots=True)
class FyersEquitySymbol(FyersBaseSymbol):
    isin: str = ""
    script_code: str = ""

    @property
    def kind(self) -> SymbolKind:
        return "equity"


@dataclass(slots=True)
class FyersIndexSpotSymbol(FyersBaseSymbol):
    script_code: str = ""

    @property
    def kind(self) -> SymbolKind:
        return "index_spot"


@dataclass(slots=True)
class FyersFutureSymbol(FyersBaseSymbol):
    underlying_symbol: str = ""
    underlying_script_code: str = ""
    expiry_epoch: int = 0
    instrument_type: str = ""

    @property
    def kind(self) -> SymbolKind:
        return "future"


@dataclass(slots=True)
class FyersOptionSymbol(FyersBaseSymbol):
    underlying_symbol: str = ""
    underlying_script_code: str = ""
    expiry_epoch: int = 0
    strike: float = 0.0
    option_type: str = ""
    instrument_type: str = ""

    @property
    def kind(self) -> SymbolKind:
        return "option"


# Temporary compatibility alias for old imports
FyersSymbol = FyersEquitySymbol


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
    tick_count: int = 0
    is_complete: bool = False
    first_tick_epoch: int = 0
    last_tick_epoch: int = 0
    is_partial: bool = False
    partial_reason: str = ""

    def update(self, price: float) -> None:
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        self.close = price
        self.volume += 1
        self.tick_count += 1


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
