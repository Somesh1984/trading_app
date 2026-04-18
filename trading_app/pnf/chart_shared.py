# -*- coding: utf-8 -*-
"""Shared constants and lightweight helpers for chart_pnf.

This module holds common type aliases, bullish/bearish constants, signal labels,
and the optional tabulate fallback. It must stay free of chart state and trading
side effects.
"""

from __future__ import annotations

from typing import Any, Literal

DateTimeUnit = Literal['m', 'D']
BoxSize = int | float | str

try:
    from tabulate import tabulate as _tabulate_impl
except ModuleNotFoundError:
    _tabulate_impl = None


def tabulate(rows: Any, tablefmt: str = 'simple') -> str:
    if _tabulate_impl is not None:
        return _tabulate_impl(rows, tablefmt=tablefmt)

    return '\n'.join(' '.join(str(cell) for cell in row) for row in rows)


SIGNAL_TYPES = [
    'Buy Signal',
    'Sell Signal',
    'Double Top Breakout',
    'Double Bottom Breakdown',
    'Triple Top Breakout',
    'Triple Bottom Breakdown',
    'Quadruple Top Breakout',
    'Quadruple Bottom Breakdown',
    'Ascending Triple Top Breakout',
    'Descending Triple Bottom Breakdown',
    'Bullish Catapult Breakout',
    'Bearish Catapult Breakdown',
    'Bullish Signal Reversed',
    'Bearish Signal Reversed',
    'Bullish Triangle Breakout',
    'Bearish Triangle Breakdown',
    'Long Tail Down Reversal',
    'Bull Trap',
    'Bear Trap',
    'Spread Triple Top Breakout',
    'Spread Triple Bottom Breakdown',
    'High Pole',
    'Low Pole',
]

BULLISH = 1
BEARISH = -1
