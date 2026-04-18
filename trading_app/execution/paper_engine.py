

from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from trading_app.models import ClosedPaperTrade, LiveCandle, PaperTrade


class PaperExecutionEngine:
    def __init__(self) -> None:
        self.positions: Dict[str, PaperTrade] = {}
        self.closed_trades: List[ClosedPaperTrade] = []
        self.live_mtm: Dict[str, float] = {}
        self.default_stop_loss = 10.0
        self.default_take_profit = 20.0

    def _calculate_pnl(self, position: PaperTrade, exit_price: float) -> float:
        if position.side == "BUY":
            return (exit_price - position.entry_price) * position.qty
        return (position.entry_price - exit_price) * position.qty

    def get_realized_pnl(self) -> float:
        return sum(t.pnl for t in self.closed_trades)

    def get_unrealized_pnl(self) -> float:
        return sum(self.live_mtm.values())

    def get_total_pnl(self) -> float:
        return self.get_realized_pnl() + self.get_unrealized_pnl()

    def _r(self, value: float) -> float:
        return round(value, 2)

    def _fmt_epoch(self, epoch: int) -> str:
        return datetime.fromtimestamp(epoch).strftime("%H:%M:%S")

    def _fmt_range(self, start: int, timeframe: int) -> str:
        end = start + timeframe - 1
        return f"{self._fmt_epoch(start)} → {self._fmt_epoch(end)}"

    def print_open_positions(self) -> None:
        print("OPEN POSITIONS:")
        if not self.positions:
            print("NONE")
            return

        for symbol, position in self.positions.items():
            live_pnl = self._r(self.live_mtm.get(symbol, 0.0))
            print(
                symbol,
                position.side,
                position.qty,
                position.entry_price,
                "MTM=",
                live_pnl,
            )

    def print_summary(self) -> None:
        print("SUMMARY:")
        print("REALIZED PNL:", self._r(self.get_realized_pnl()))
        print("UNREALIZED PNL:", self._r(self.get_unrealized_pnl()))
        print("TOTAL PNL:", self._r(self.get_total_pnl()))
        print("CLOSED TRADES:", len(self.closed_trades))

    def update_mtm(self, symbol: str, ltp: float) -> None:
        position = self.positions.get(symbol)
        if position is None:
            self.live_mtm.pop(symbol, None)
            return

        if position.side == "BUY":
            pnl = (ltp - position.entry_price) * position.qty
        else:
            pnl = (position.entry_price - ltp) * position.qty

        self.live_mtm[symbol] = pnl
        print("LIVE MTM:", symbol, self._r(pnl))
        print("TOTAL PORTFOLIO PNL:", self._r(self.get_total_pnl()))

    def process_candle(self, candle: LiveCandle, signal: str) -> None:
        print(
            "CANDLE:",
            candle.symbol,
            self._fmt_range(candle.bucket_epoch, candle.timeframe_seconds),
            candle,
        )
        print("SIGNAL:", candle.symbol, signal)

        if signal == "NONE":
            return

        existing = self.positions.get(candle.symbol)

        if existing is not None:
            if existing.side == signal:
                print("POSITION EXISTS:", existing)
                self.print_open_positions()
                self.print_summary()
                return

            pnl = self._calculate_pnl(existing, candle.close)

            closed = ClosedPaperTrade(
                symbol=existing.symbol,
                side=existing.side,
                qty=existing.qty,
                entry_price=existing.entry_price,
                exit_price=candle.close,
                entry_minute_epoch=existing.entry_minute_epoch,
                exit_minute_epoch=candle.bucket_epoch,
                pnl=pnl,
            )

            self.closed_trades.append(closed)
            del self.positions[candle.symbol]
            self.live_mtm.pop(candle.symbol, None)

            print("TRADE CLOSED:", closed)
            print("TOTAL CLOSED:", len(self.closed_trades))
            print("TOTAL PNL:", self._r(self.get_total_pnl()))

        new_trade = PaperTrade(
            symbol=candle.symbol,
            side=signal,
            qty=1,
            entry_price=candle.close,
            entry_minute_epoch=candle.bucket_epoch,
            stop_loss=(
                candle.close - self.default_stop_loss
                if signal == "BUY"
                else candle.close + self.default_stop_loss
            ),
            take_profit=(
                candle.close + self.default_take_profit
                if signal == "BUY"
                else candle.close - self.default_take_profit
            ),
        )

        self.positions[candle.symbol] = new_trade
        self.live_mtm[candle.symbol] = 0.0

        print("TRADE OPENED:", new_trade)
        self.print_open_positions()
        self.print_summary()

    def _should_exit_on_price(self, position: PaperTrade, ltp: float) -> bool:
        if position.side == "BUY":
            if position.stop_loss and ltp <= position.stop_loss:
                return True
            if position.take_profit and ltp >= position.take_profit:
                return True
            return False

        if position.stop_loss and ltp >= position.stop_loss:
            return True
        if position.take_profit and ltp <= position.take_profit:
            return True
        return False

    def process_tick(self, symbol: str, ltp: float, exch_feed_time: int) -> None:
        position = self.positions.get(symbol)
        if position is None:
            self.live_mtm.pop(symbol, None)
            return

        self.update_mtm(symbol, ltp)

        if not self._should_exit_on_price(position, ltp):
            return

        pnl = self._calculate_pnl(position, ltp)

        closed = ClosedPaperTrade(
            symbol=position.symbol,
            side=position.side,
            qty=position.qty,
            entry_price=position.entry_price,
            exit_price=ltp,
            entry_minute_epoch=position.entry_minute_epoch,
            exit_minute_epoch=exch_feed_time,
            pnl=pnl,
        )

        self.closed_trades.append(closed)
        del self.positions[symbol]
        self.live_mtm.pop(symbol, None)

        print("SL/TP TRADE CLOSED:", closed)
        print("TOTAL CLOSED:", len(self.closed_trades))
        print("TOTAL PNL:", self._r(self.get_total_pnl()))
        self.print_open_positions()
        self.print_summary()