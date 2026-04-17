from __future__ import annotations

from broker.models import LiveCandle


class PreviousCandleBreakoutStrategy:
    def __init__(self) -> None:
        self._previous_by_symbol: dict[str, LiveCandle] = {}

    def get_signal(self, candle: LiveCandle) -> str:
        previous = self._previous_by_symbol.get(candle.symbol)
        self._previous_by_symbol[candle.symbol] = candle

        if previous is None:
            return "NONE"

        if candle.close > previous.high:
            return "BUY"

        if candle.close < previous.low:
            return "SELL"

        return "NONE"