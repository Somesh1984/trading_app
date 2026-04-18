# -*- coding: utf-8 -*-
"""Chart building engine for PointFigureChart.

This module converts prepared time series data into boxscale, PnF time series,
and matrix output. It owns step-frozen log chart construction and compatibility
grid construction; pattern, signal, count, broker, and order logic live
elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP
from math import isfinite
from typing import Any, Iterable, Iterator, TYPE_CHECKING
from warnings import warn

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle

from .chart_shared import BEARISH, BULLISH, BoxSize, DateTimeUnit, SIGNAL_TYPES, tabulate


_STEP_CONTEXT = Context(prec=34)
_STEP_TICK_SIZE = Decimal("0.01")


@dataclass(frozen=True)
class _StepFrozenConfig:
    box_pct: Decimal
    reversal: int
    method: str
    tick_size: Decimal = _STEP_TICK_SIZE


@dataclass(frozen=True)
class _StepFrozenColumn:
    type: str
    start_index: int
    end_index: int
    boxes: tuple[Decimal, ...]

    @property
    def high(self) -> Decimal:
        return max(self.boxes)

    @property
    def low(self) -> Decimal:
        return min(self.boxes)

    @property
    def last_box(self) -> Decimal:
        return self.high if self.type == 'X' else self.low

    @property
    def box_count(self) -> int:
        return len(self.boxes)


@dataclass(frozen=True)
class _StepFrozenUpdate:
    index: int
    open: Decimal | None = None
    close: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None


def _to_step_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, float):
        if not isfinite(value):
            return None
        result = Decimal(str(value))
    else:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    if not result.is_finite():
        return None
    return result


def _require_step_price(value: Any) -> Decimal | None:
    result = _to_step_decimal(value)
    if result is None:
        return None
    if result <= 0:
        raise ValueError("prices must be positive")
    return result


def _round_step_price(price: Decimal, config: _StepFrozenConfig) -> Decimal:
    units = _STEP_CONTEXT.divide(price, config.tick_size)
    rounded_units = units.to_integral_value(rounding=ROUND_HALF_UP)
    rounded = _STEP_CONTEXT.multiply(rounded_units, config.tick_size)
    return rounded.quantize(config.tick_size, rounding=ROUND_HALF_UP)


def _step_box_size(reference: Decimal, config: _StepFrozenConfig) -> Decimal:
    box_size = _STEP_CONTEXT.multiply(reference, config.box_pct)
    if box_size <= 0:
        raise ValueError("box size must be positive")
    return box_size


def _step_boxes_above(price: Decimal, reference: Decimal, box_size: Decimal) -> int:
    if price <= reference:
        return 0
    distance = _STEP_CONTEXT.subtract(price, reference)
    return int(_STEP_CONTEXT.divide(distance, box_size).to_integral_value(rounding=ROUND_FLOOR))


def _step_boxes_below(price: Decimal, reference: Decimal, box_size: Decimal) -> int:
    if price >= reference:
        return 0
    distance = _STEP_CONTEXT.subtract(reference, price)
    return int(_STEP_CONTEXT.divide(distance, box_size).to_integral_value(rounding=ROUND_FLOOR))


def _step_box_values(
    reference: Decimal,
    count: int,
    direction: str,
    box_size: Decimal,
    config: _StepFrozenConfig,
) -> tuple[Decimal, ...]:
    if direction == 'up':
        return tuple(
            _round_step_price(_STEP_CONTEXT.add(reference, _STEP_CONTEXT.multiply(box_size, Decimal(step))), config)
            for step in range(1, count + 1)
        )
    return tuple(
        _round_step_price(_STEP_CONTEXT.subtract(reference, _STEP_CONTEXT.multiply(box_size, Decimal(step))), config)
        for step in range(1, count + 1)
    )


def _build_step_frozen_columns(
    data: Iterable[dict[str, Any]],
    config: _StepFrozenConfig,
) -> list[_StepFrozenColumn]:
    columns: list[_StepFrozenColumn] = []
    initial_reference: Decimal | None = None
    initial_index: int | None = None
    initial_box_size: Decimal | None = None

    for update in _iter_step_frozen_updates(data, config):
        if not columns:
            for price in _initial_step_prices(update, config):
                if initial_reference is None:
                    initial_reference = price
                    initial_index = update.index
                    initial_box_size = _step_box_size(initial_reference, config)
                    continue
                assert initial_index is not None
                assert initial_box_size is not None
                column = _try_initial_step_column(
                    price=price,
                    index=update.index,
                    initial_index=initial_index,
                    reference=initial_reference,
                    box_size=initial_box_size,
                    config=config,
                )
                if column is not None:
                    columns.append(column)
                    break
            continue

        active = columns[-1]
        updated = _process_step_update(active, update, config)
        if updated is active:
            continue
        if updated.type == active.type:
            columns[-1] = updated
        else:
            columns.append(updated)

    return columns


def _iter_step_frozen_updates(
    data: Iterable[dict[str, Any]],
    config: _StepFrozenConfig,
) -> Iterator[_StepFrozenUpdate]:
    for index, item in enumerate(data):
        open_ = _require_step_price(item.get('open'))
        close = _require_step_price(item.get('close'))
        high = _require_step_price(item.get('high'))
        low = _require_step_price(item.get('low'))

        open_ = _round_step_price(open_, config) if open_ is not None else None
        close = _round_step_price(close, config) if close is not None else None
        high = _round_step_price(high, config) if high is not None else None
        low = _round_step_price(low, config) if low is not None else None

        if high is not None and low is not None and high < low:
            raise ValueError("high must be greater than or equal to low")
        if config.method in {'hlc', 'ohlc'} and close is not None and high is not None and close > high:
            raise ValueError("close must be less than or equal to high")
        if config.method in {'hlc', 'ohlc'} and close is not None and low is not None and close < low:
            raise ValueError("close must be greater than or equal to low")
        if config.method == 'ohlc' and open_ is not None and high is not None and open_ > high:
            raise ValueError("open must be less than or equal to high")
        if config.method == 'ohlc' and open_ is not None and low is not None and open_ < low:
            raise ValueError("open must be greater than or equal to low")

        if open_ is None and close is None and high is None and low is None:
            continue
        yield _StepFrozenUpdate(index=index, open=open_, close=close, high=high, low=low)


def _initial_step_prices(update: _StepFrozenUpdate, config: _StepFrozenConfig) -> tuple[Decimal, ...]:
    if config.method == 'cl':
        return () if update.close is None else (update.close,)
    if config.method == 'ohlc':
        return _step_ohlc_prices(update)
    if config.method == 'l/h':
        return tuple(price for price in (update.low, update.high) if price is not None)
    values = [update.high, update.low]
    if config.method == 'hlc':
        values.append(update.close)
    return tuple(price for price in values if price is not None)


def _try_initial_step_column(
    price: Decimal,
    index: int,
    initial_index: int,
    reference: Decimal,
    box_size: Decimal,
    config: _StepFrozenConfig,
) -> _StepFrozenColumn | None:
    up_boxes = _step_boxes_above(price, reference, box_size)
    if up_boxes >= config.reversal:
        boxes = _step_box_values(reference, up_boxes, 'up', box_size, config)
        return _StepFrozenColumn('X', initial_index, index, boxes)

    down_boxes = _step_boxes_below(price, reference, box_size)
    if down_boxes >= config.reversal:
        boxes = _step_box_values(reference, down_boxes, 'down', box_size, config)
        return _StepFrozenColumn('O', initial_index, index, boxes)

    return None


def _process_step_update(
    active: _StepFrozenColumn,
    update: _StepFrozenUpdate,
    config: _StepFrozenConfig,
) -> _StepFrozenColumn:
    reference = active.last_box
    box_size = _step_box_size(reference, config)

    if config.method == 'hlc':
        return _process_step_hlc_update(active, update, reference, box_size, config)

    for price in _step_update_prices(active, update, config):
        updated = _process_step_price(active, price, update.index, reference, box_size, config)
        if updated is not active:
            return updated

    return active


def _process_step_hlc_update(
    active: _StepFrozenColumn,
    update: _StepFrozenUpdate,
    reference: Decimal,
    box_size: Decimal,
    config: _StepFrozenConfig,
) -> _StepFrozenColumn:
    if update.close is None:
        return active

    if active.type == 'X':
        boxes = _step_boxes_above(update.close, reference, box_size)
        if boxes >= 1 and update.high is not None:
            return _process_step_price(active, update.high, update.index, reference, box_size, config)

        boxes = _step_boxes_below(update.close, reference, box_size)
        if boxes >= config.reversal and update.low is not None:
            return _process_step_price(active, update.low, update.index, reference, box_size, config)
        return active

    boxes = _step_boxes_below(update.close, reference, box_size)
    if boxes >= 1 and update.low is not None:
        return _process_step_price(active, update.low, update.index, reference, box_size, config)

    boxes = _step_boxes_above(update.close, reference, box_size)
    if boxes >= config.reversal and update.high is not None:
        return _process_step_price(active, update.high, update.index, reference, box_size, config)
    return active


def _step_update_prices(
    active: _StepFrozenColumn,
    update: _StepFrozenUpdate,
    config: _StepFrozenConfig,
) -> tuple[Decimal, ...]:
    if config.method == 'ohlc':
        return _step_ohlc_prices(update)
    return tuple(
        price
        for price in (getattr(update, price_name) for price_name in _step_update_order(active, config))
        if price is not None
    )


def _step_update_order(active: _StepFrozenColumn, config: _StepFrozenConfig) -> tuple[str, ...]:
    if config.method == 'cl':
        return ('close',)
    if config.method == 'h/l':
        return ('high', 'low')
    if config.method == 'l/h':
        return ('low', 'high')
    raise ValueError(f"Unsupported step-frozen method: {config.method}")


def _step_ohlc_prices(update: _StepFrozenUpdate) -> tuple[Decimal, ...]:
    if update.open is None or update.high is None or update.low is None or update.close is None:
        return tuple(price for price in (update.open, update.high, update.low, update.close) if price is not None)
    if update.open <= update.close:
        return (update.open, update.low, update.high, update.close)
    return (update.open, update.high, update.low, update.close)


def _process_step_price(
    active: _StepFrozenColumn,
    price: Decimal,
    index: int,
    reference: Decimal,
    box_size: Decimal,
    config: _StepFrozenConfig,
) -> _StepFrozenColumn:
    if active.type == 'X':
        boxes = _step_boxes_above(price, reference, box_size)
        if boxes >= 1:
            return _extend_step_column(active, boxes, 'up', box_size, index, config)
        boxes = _step_boxes_below(price, reference, box_size)
        if boxes >= config.reversal:
            return _new_step_column('O', reference, boxes, 'down', box_size, index, config)
        return active

    boxes = _step_boxes_below(price, reference, box_size)
    if boxes >= 1:
        return _extend_step_column(active, boxes, 'down', box_size, index, config)
    boxes = _step_boxes_above(price, reference, box_size)
    if boxes >= config.reversal:
        return _new_step_column('X', reference, boxes, 'up', box_size, index, config)
    return active


def _extend_step_column(
    active: _StepFrozenColumn,
    count: int,
    direction: str,
    box_size: Decimal,
    index: int,
    config: _StepFrozenConfig,
) -> _StepFrozenColumn:
    boxes = active.boxes + _step_box_values(active.last_box, count, direction, box_size, config)
    return _StepFrozenColumn(active.type, active.start_index, index, boxes)


def _new_step_column(
    kind: str,
    reference: Decimal,
    count: int,
    direction: str,
    box_size: Decimal,
    index: int,
    config: _StepFrozenConfig,
) -> _StepFrozenColumn:
    boxes = _step_box_values(reference, count, direction, box_size, config)
    return _StepFrozenColumn(kind, index, index, boxes)


class ChartEngineMixin:
    action_index_matrix: Any
    boxscale: np.ndarray
    boxsize: BoxSize
    method: str
    pnf_timeseries: dict[str, Any]
    reversal: int
    scaling: str
    ts: dict[str, np.ndarray]

    if TYPE_CHECKING:
        def _datetime_unit(self) -> DateTimeUnit | None: ...

    def _uses_step_frozen_log_scaling(self) -> bool:
        return self.scaling == 'log'

    def _get_step_frozen_log_chart(self):
        data = self._iter_step_frozen_log_input()
        config = _StepFrozenConfig(
            box_pct=Decimal(str(float(self.boxsize) / 100.0)),
            reversal=self.reversal,
            method=self.method,
        )
        columns = _build_step_frozen_columns(data, config)
        if not columns:
            raise ValueError('Choose a smaller box size. There is no trend using the current parameter.')

        box_values = sorted({float(box) for column in columns for box in column.boxes})
        boxscale = np.asarray(box_values, dtype=np.float64)
        box_index = {value: index for index, value in enumerate(box_values)}

        matrix = np.zeros([np.size(boxscale), len(columns)], dtype=int)
        action_index_matrix = np.zeros([np.size(boxscale), len(columns)], dtype=int)

        pnf_steps = np.full([len(self.ts['date']), 5], np.nan)

        for column_index, column in enumerate(columns):
            trend = BULLISH if column.type == 'X' else BEARISH
            for box in column.boxes:
                row = box_index[float(box)]
                matrix[row, column_index] = trend
                action_index_matrix[row, column_index] = column.end_index

            last_box = column.last_box
            row = box_index[float(last_box)]
            pnf_steps[column.end_index, :] = [
                float(last_box),
                row,
                column_index,
                trend,
                column.box_count,
            ]

        pftseries = {
            'date': self.ts['date'],
            'box value': pnf_steps[:, 0],
            'box index': pnf_steps[:, 1],
            'column index': pnf_steps[:, 2],
            'trend': pnf_steps[:, 3],
            'filled boxes': pnf_steps[:, 4],
        }

        return boxscale, pftseries, matrix, action_index_matrix

    def _iter_step_frozen_log_input(self):
        if self.method == 'cl':
            for close in self.ts['close']:
                yield {'close': close}
            return

        if self.method in {'h/l', 'l/h'}:
            for high, low in zip(self.ts['high'], self.ts['low']):
                yield {'high': high, 'low': low}
            return

        if self.method == 'hlc':
            for high, low, close in zip(self.ts['high'], self.ts['low'], self.ts['close']):
                yield {'high': high, 'low': low, 'close': close}
            return

        if self.method == 'ohlc':
            for open_, high, low, close in zip(self.ts['open'], self.ts['high'], self.ts['low'], self.ts['close']):
                yield {'open': open_, 'high': high, 'low': low, 'close': close}
            return

        raise ValueError('Unsupported step-frozen log method')

    def _get_first_trend(self):
        """
        Determines the first box and trend
        """

        if self.method == 'cl' or self.method == 'ohlc':
            H = self.ts['close']
            L = self.ts['close']
        else:
            H = self.ts['high']
            L = self.ts['low']

        Boxes = self.boxscale

        iBu = np.where(Boxes >= H[0])[0][0]

        if H[0] != Boxes[iBu]:
            iBu = iBu - 1

        iBd = np.where(Boxes <= L[0])[0][-1]

        k = 1
        uTF = 0  # uptrend flag
        dTF = 0  # downtrend flag

        while uTF == 0 and dTF == 0 and k <= np.size(H) - 1:
            if H[k] >= Boxes[iBu + 1]:
                uTF = 1
            else:
                if L[k] <= Boxes[iBd - 1]:
                    dTF = -1
            k += 1

        # first trend is up
        if uTF > 0:
            TF = uTF
            iB = iBu

        # first trend is down
        elif dTF < 0:
            TF = dTF
            iB = iBd

        # no trend
        else:
            TF = 0
            iB = 0

        iC = 0  # column index
        fB = 1  # number of filled Boxes
        box = Boxes[iB]

        iD = k - 1  # index of date with first entry

        if TF == 0:
            raise ValueError('Choose a smaller box size. There is no trend using the current parameter.')

        return iD, box, iB, iC, TF, fB

    def _basic(self, P, iB, iC, TF, fB):
        """
        basic logic to build point and figure charts
        """

        Boxes = self.boxscale
        reversal = self.reversal

        iBp = iB  # Box index from previous iteration
        fBp = fB  # number of filled Boxes from previous iteration

        if TF == 1:

            # check if there is a further 'X' in the trend
            if P >= Boxes[iB + 1]:

                # increase box index until the price reaches the next box level
                while P >= Boxes[iB + 1]:
                    iB = iB + 1

                # calculate number of filled Boxes
                fB = fB + iB - iBp

            # the Box index can not be zero
            if iB - reversal < 1:
                iB = 1 + reversal

            # check for reversal
            if P <= Boxes[iB - reversal]:

                # set Box index to the bottom box
                iB = np.where(Boxes >= P)[0][0]

                TF = -1  # trend becomes negative
                iC = iC + 1  # go to next column
                fB = iBp - iB  # calculate number of filled Boxes

                # check for one-step-back
                if reversal == 1 and fBp == 1:
                    iC = iC - 1  # set column to previous column
                    fB = fB + 1  # calculate number of filled Boxes

        elif TF == -1:

            # the Box index can not be zero
            if iB - 1 < 1:
                iB = 1 + 1

            # check if there is a further 'O' in the trend
            if P <= Boxes[iB - 1]:

                # decrease box index until the price falls down under the next box level
                while P <= Boxes[iB - 1]:
                    iB = iB - 1

                # calculate number of filled Boxes
                fB = fB + iBp - iB

            # check for reversal
            if P >= Boxes[iB + reversal]:

                # set Box index to the top box
                iB = np.where(Boxes <= P)[0][-1]

                TF = 1  # trend becomes positive
                iC = iC + 1  # go to next column
                fB = iB - iBp  # calculate number of filled Boxes

                # check for one-step-back
                if reversal == 1 and fBp == 1:
                    iC = iC - 1  # set column to previous column
                    fB = fB + 1  # calculate number of filled Boxes

        Box = Boxes[iB]

        return Box, iB, iC, TF, fB

    def _close(self, iD, Box, iB, iC, TF, fB):
        """
        logic for point and figure charts based on closing prices
        """

        C = self.ts['close']

        ts = np.zeros([np.size(C), 5])

        # make the first entry right before the first change
        # otherwise filled boxes can be not correctly determined
        # in next iteration.
        ts[0: iD, :] = [Box, iB, iC, TF, fB]

        C = C[iD:]

        for n, C in enumerate(C):
            [Box, iB, iC, TF, fB] = self._basic(C, iB, iC, TF, fB)
            ts[iD + n, :] = [Box, iB, iC, TF, fB]

        return ts

    def _hilo(self, iD, Box, iB, iC, TF, fB):
        """
        logic for point and figure charts adapting the high/low method
        """

        H = self.ts['high']
        L = self.ts['low']

        Boxes = self.boxscale
        reversal = self.reversal

        ts = np.zeros([np.size(H), 5])

        # make the first entry right before the first change
        # otherwise filled boxes can be not correctly determined
        # in next iteration.
        ts[0: iD, :] = [Box, iB, iC, TF, fB]

        for n in range(iD, np.size(H)):

            iBp = iB  # Box index from previous iteration
            fBp = fB  # number of filled Boxes from previous iteration

            if TF == 1:

                # check if there is a further 'X' in the trend
                if H[n] >= Boxes[iB + 1]:
                    [Box, iB, iC, TF, fB] = self._basic(H[n], iB, iC, TF, fB)

                else:

                    # the Box index can not be zero
                    if iB - reversal < 1:
                        iB = 1 + reversal

                    # check low for reversal
                    if L[n] <= Boxes[iB - reversal]:
                        TF = -1
                        [Box, iB, iC, TF, _] = self._basic(L[n], iB, iC, TF, fB)
                        iC = iC + 1  # go to next column
                        fB = iBp - iB  # calculate number of filled Boxes

                        # check for one-step-back
                        if reversal == 1 and fBp == 1:
                            iC = iC - 1  # set column to previous column
                            fB = fB + 1  # calculate number of filled Boxes

                ts[n, :] = [Box, iB, iC, TF, fB]

            elif TF == -1:

                # the Box index can not be zero
                if iB - 1 < 1:
                    iB = 1 + 1

                # check if there is a further 'O' in the trend
                if L[n] <= Boxes[iB - 1]:
                    [Box, iB, iC, TF, fB] = self._basic(L[n], iB, iC, TF, fB)

                else:

                    # check high for reversal
                    if H[n] >= Boxes[iB + reversal]:
                        TF = 1
                        [Box, iB, iC, TF, _] = self._basic(H[n], iB, iC, TF, fB)
                        iC = iC + 1  # go to next column
                        fB = iB - iBp  # calculate number of filled Boxes

                        # check for one-step-back
                        if reversal == 1 and fBp == 1:
                            iC = iC - 1  # set column to previous column
                            fB = fB + 1  # calculate number of filled Boxes

            ts[n, :] = [Box, iB, iC, TF, fB]

        return ts

    def _lohi(self, iD, Box, iB, iC, TF, fB):
        """
        logic for point and figure charts adapting the low/high method
        """
        H = self.ts['high']
        L = self.ts['low']

        Boxes = self.boxscale
        reversal = self.reversal

        ts = np.zeros([np.size(H), 5])

        # make the first entry right before the first change
        # otherwise filled boxes can be not correctly determined
        # in next iteration.
        ts[0: iD, :] = [Box, iB, iC, TF, fB]

        for n in range(iD, np.size(H)):

            iBp = iB  # Box index from previous iteration
            fBp = fB  # number of filled Boxes from previous iteration

            if TF == 1:

                # the Box index can not be zero
                if iB - reversal < 1:
                    iB = 1 + reversal

                # check for reversal
                if L[n] <= Boxes[iB - reversal]:
                    TF = -1
                    [Box, iB, iC, TF, _] = self._basic(L[n], iB, iC, TF, fB)
                    iC = iC + 1  # go to next column
                    fB = iBp - iB  # calculate number of filled Boxes

                    # check for one-step-back
                    if reversal == 1 and fBp == 1:
                        iC = iC - 1  # set column to previous column
                        fB = fB + 1  # calculate number of filled Boxes
                else:

                    # check if there is a further 'X' in the trend
                    if H[n] >= Boxes[iB + 1]:
                        [Box, iB, iC, TF, fB] = self._basic(H[n], iB, iC, TF, fB)

            elif TF == -1:

                # check for reversal
                if H[n] >= Boxes[iB + reversal]:
                    TF = 1
                    [Box, iB, iC, TF, _] = self._basic(H[n], iB, iC, TF, fB)
                    iC = iC + 1  # go to next column
                    fB = iB - iBp  # calculate number of filled Boxes

                    # check for one-step-back
                    if reversal == 1 and fBp == 1:
                        iC = iC - 1  # set column to previous column
                        fB = fB + 1  # calculate number of filled Boxes

                else:

                    # check if there is a further 'O' in the trend
                    if L[n] <= Boxes[iB - 1]:
                        [Box, iB, iC, TF, fB] = self._basic(L[n], iB, iC, TF, fB)

                    # else:  # do nothing
                    #   pass

            ts[n, :] = [Box, iB, iC, TF, fB]

        return ts

    def _hlc(self, iD, Box, iB, iC, TF, fB):
        """
        logic for point and figure charts adapting the high/low/close method
        """

        H = self.ts['high']
        L = self.ts['low']
        C = self.ts['close']

        Boxes = self.boxscale
        reversal = self.reversal

        ts = np.zeros([np.size(H), 5])

        # make the first entry right before the first change
        # otherwise filled boxes can be not correctly determined
        # in next iteration.
        ts[0: iD, :] = [Box, iB, iC, TF, fB]

        for n in range(iD, np.size(H)):

            iBp = iB  # Box index from previous iteration
            fBp = fB  # number of filled Boxes from previous iteration

            # trend is up
            if TF == 1:

                # check if there is a further 'X' in the trend
                if C[n] >= Boxes[iB + 1]:
                    [Box, iB, iC, TF, fB] = self._basic(H[n], iB, iC, TF, fB)

                else:

                    # the Box index can not be zero
                    if iB - reversal < 1:
                        iB = 1 + reversal

                    # check for reversal
                    if C[n] <= Boxes[iB - reversal]:
                        TF = -1
                        [Box, iB, iC, TF, _] = self._basic(L[n], iB, iC, TF, fB)
                        iC = iC + 1  # go to next column
                        fB = iBp - iB  # calculate number of filled Boxes

                        if reversal == 1 and fBp == 1:  # check for one-step-back
                            iC = iC - 1  # set column to previous column
                            fB = fB + 1  # calculate number of filled Boxes

                ts[n, :] = [Box, iB, iC, TF, fB]

            # trend is down
            elif TF == -1:

                # the Box index can not be zero
                if iB - 1 < 1:
                    iB = 1 + 1

                # check if there is a further 'O' in the trend
                if C[n] <= Boxes[iB - 1]:
                    [Box, iB, iC, TF, fB] = self._basic(L[n], iB, iC, TF, fB)

                else:

                    # check close for reversal
                    if C[n] >= Boxes[iB + reversal]:
                        TF = 1
                        [Box, iB, iC, TF, _] = self._basic(H[n], iB, iC, TF, fB)
                        iC = iC + 1  # go to next column
                        fB = iB - iBp  # calculate number of filled Boxes

                        # check for one-step-back
                        if reversal == 1 and fBp == 1:
                            iC = iC - 1  # set column to previous column
                            fB = fB + 1  # calculate number of filled Boxes

                ts[n, :] = [Box, iB, iC, TF, fB]

        return ts

    def _ohlc(self):
        """
        logic for point and figure charts adapting the open/high/low/close method
        """

        O = self.ts['open']
        H = self.ts['high']
        L = self.ts['low']
        C = self.ts['close']

        P = np.zeros(4 * np.size(C))

        tP = []
        counter = 0
        for n in range(counter, np.size(C)):

            if C[n] > O[n]:
                tP = [O[n], L[n], H[n], C[n]]

            elif C[n] < O[n]:
                tP = [O[n], H[n], L[n], C[n]]

            elif C[n] == O[n] and C[n] == L[n]:
                tP = [O[n], H[n], L[n], C[n]]

            elif C[n] == O[n] and C[n] == H[n]:
                tP = [O[n], L[n], H[n], C[n]]

            elif C[n] == O[n] and (H[n] + L[n]) / 2 > C[n]:
                tP = [O[n], H[n], L[n], C[n]]

            elif C[n] == O[n] and (H[n] + L[n]) / 2 < C[n]:
                tP = [O[n], L[n], H[n], C[n]]

            elif C[n] == O[n] and (H[n] + L[n]) / 2 == C[n]:

                if n > 1:
                    # if trend is uptrend
                    if C[n - 1] < C[n]:
                        tP = [O[n], H[n], L[n], C[n]]

                    # downtrend
                    elif C[n - 1] > C[n]:
                        tP = [O[n], L[n], H[n], C[n]]

                else:
                    tP = [O[n], H[n], L[n], C[n]]

            P[counter:counter + 4] = tP

            counter += 4

        # store initial close values temporary
        close = self.ts['close'].copy()

        # set the new time-series as close
        self.ts['close'] = P

        # determine the fist box entry
        [iD, Box, iB, iC, TF, fB] = self._get_first_trend()

        # restore initial close
        self.ts['close'] = close

        ts = np.zeros([np.size(P), 5])

        ts[0: iD, :] = [Box, iB, iC, TF, fB]

        for n in range(iD, len(P)):
            [Box, iB, iC, TF, fB] = self._basic(P[n], iB, iC, TF, fB)
            ts[n, :] = [Box, iB, iC, TF, fB]

        return ts

    def _get_pnf_timeseries(self):
        """
        builds time-series for point and figure chart
        """

        source_ts = self.ts

        date = source_ts['date']
        pfdate = date.copy()

        [iD, Box, iB, iC, TF, fB] = self._get_first_trend()

        if self.method == 'cl':
            pnf_steps = self._close(iD, Box, iB, iC, TF, fB)

        elif self.method == 'h/l':
            pnf_steps = self._hilo(iD, Box, iB, iC, TF, fB)

        elif self.method == 'l/h':
            pnf_steps = self._lohi(iD, Box, iB, iC, TF, fB)

        elif self.method == 'hlc':
            pnf_steps = self._hlc(iD, Box, iB, iC, TF, fB)

        elif self.method == 'ohlc':
            pnf_steps = self._ohlc()

            # reset the index and calculate missing datetimes
            if isinstance(self.ts['date'][0], np.datetime64):

                # extend initial index by 4 times and convert to seconds
                pfdate = np.repeat(pfdate, 4).astype('datetime64[s]')

                # find minimum in timedelta and assign to timestep
                timestep = np.min(np.diff(date))
                timestep = np.timedelta64(timestep, 's')

                # re-index the data
                counter = 0

                for n in range(0, np.size(date)):
                    pfdate[counter:counter + 4] = np.array([date[n],
                                                            date[n] + timestep * 0.25,
                                                            date[n] + timestep * 0.5,
                                                            date[n] + timestep * 0.75], dtype='datetime64[s]')
                    counter = counter + 4

            # date is not in datetime format, set index to integers
            else:
                pfdate = np.arange(0, np.shape(pnf_steps)[0])
        else:
            raise ValueError("Unknown point and figure method.")

        iTc = np.diff(np.append(0, pnf_steps[:, 3])).astype(bool)  # index of Trend change
        iBc = np.diff(np.append(0, pnf_steps[:, 1])).astype(bool)  # index of Box changes

        ic = np.logical_or(iBc, iTc)  # index of steps with changes

        pnf_steps[~ic, :] = np.nan  # set elements without action to NaN

        # index values cant be integer because of the nans in the arrays.
        pftseries = {'date': pfdate,
                     'box value': pnf_steps[:, 0],
                     'box index': pnf_steps[:, 1],
                     'column index': pnf_steps[:, 2],
                     'trend': pnf_steps[:, 3],
                     'filled boxes': pnf_steps[:, 4]}

        return pftseries

    def _get_column_entry_dates(self):

        date = self.pnf_timeseries['date']
        column_index = self.pnf_timeseries['column index']

        unit = self._datetime_unit()
        if unit is not None:
            n = 0
            column_date_labels = []

            for d, c in zip(date, column_index):
                if c == n:
                    n = n + 1
                    d = np.datetime_as_string(d, unit=unit)
                    d = d.replace('T', ' ')
                    column_date_labels.append(d)
        else:
            column_date_labels = None

        return column_date_labels

    def _pnf_timeseries2matrix(self):
        """
        builds Point and Figure matrix from Point and Figure time-series.
        """

        ts = self.pnf_timeseries
        boxes = self.boxscale

        iTS = np.arange(len(ts['box index']))
        iB = ts['box index'].copy()
        iC = ts['column index'].copy()
        TF = ts['trend'].copy()

        iNaN = np.isnan(iB)  # find indices of nan entries

        # remain entries without NaNs qne convert to int
        iB = iB[~iNaN].astype(int)
        iC = iC[~iNaN].astype(int)
        TF = TF[~iNaN].astype(int)
        iTS = iTS[~iNaN]

        mtx = np.zeros([np.size(boxes), iC[-1] + 1], dtype=int)
        self.action_index_matrix = np.zeros([np.size(boxes), iC[-1] + 1], dtype=int)

        # mark first box
        if TF[0] == 1:
            mtx[iB[0], 0] = 1
            self.action_index_matrix[iB[0], 0] = iTS[0]
        elif TF[0] == -1:
            mtx[iB[1], 0] = -1
            self.action_index_matrix[iB[0], 0] = iTS[0]

        # mark the other boxes
        for n in range(1, np.size(iB)):

            # positive trend goes on
            if TF[n - 1] == 1 and TF[n] == 1:
                mtx[iB[n - 1]:iB[n] + 1, iC[n]] = TF[n]
                self.action_index_matrix[iB[n - 1]:iB[n] + 1, iC[n]] = iTS[n]

            # positive trend reverses
            elif TF[n - 1] == 1 and TF[n] == -1:
                mtx[iB[n]:iB[n - 1], iC[n]] = TF[n]
                self.action_index_matrix[iB[n]:iB[n - 1], iC[n]] = iTS[n]

            # negative trend goes on
            elif TF[n - 1] == -1 and TF[n] == -1:
                mtx[iB[n]:iB[n - 1] + 1, iC[n]] = TF[n]
                self.action_index_matrix[iB[n]:iB[n - 1] + 1, iC[n]] = iTS[n]

            # negative trend reverses
            elif TF[n - 1] == -1 and TF[n] == 1:
                mtx[iB[n - 1] + 1:iB[n] + 1, iC[n]] = TF[n]
                self.action_index_matrix[iB[n - 1] + 1:iB[n] + 1, iC[n]] = iTS[n]

        return mtx

