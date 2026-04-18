# -*- coding: utf-8 -*-
"""Setup and validation helpers for PointFigureChart.

This module validates chart options, normalizes input time series data, and
builds box scales for non-step-frozen paths. It does not detect patterns,
signals, counts, or execute trades.
"""

from __future__ import annotations

from typing import Any
from warnings import warn

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle

from .chart_shared import BEARISH, BULLISH, BoxSize, DateTimeUnit, SIGNAL_TYPES, tabulate


class ChartSetupMixin:
    boxsize: BoxSize
    method: str
    reversal: int
    scaling: str
    time_step: DateTimeUnit | None
    ts: dict[str, np.ndarray]

    @staticmethod
    def _is_valid_method(method):

        if method not in ['cl', 'h/l', 'l/h', 'hlc', 'ohlc']:
            raise ValueError("Not a valid method. Valid methods are: cl, h/l, l/h, hlc, ohlc")

        return method

    @staticmethod
    def _is_valid_reversal(reversal):

        if not isinstance(reversal, int):
            raise ValueError('Value for reversal must be an integer. Reversal is usually between 1 and 5.')
        if reversal < 1:
            raise ValueError('Value for reversal must be greater than or equal to 1.')

        return reversal

    @staticmethod
    def _is_valid_scaling(scaling):

        if scaling not in ['abs', 'log', 'log_compounding', 'cla', 'atr']:
            raise ValueError("Not a valid scaling. Valid scales are: abs, log, log_compounding, cla and atr")

        return scaling

    def _datetime_unit(self) -> DateTimeUnit | None:
        if self.time_step == 'm':
            return 'm'
        if self.time_step == 'D':
            return 'D'
        return None

    def _is_valid_boxsize(self, boxsize: BoxSize) -> BoxSize:

        if self.scaling == 'cla':

            valid_boxsize = [0.02, 0.05, 0.1, 0.25, 1 / 3, 0.5, 1, 2]

            if boxsize not in valid_boxsize:
                msg = 'ValueError: For cla scaling valid values for boxsize are 0.02, 0.05, 0.1, 0.25, 1/3, 0.5, 1, 2'
                raise ValueError(msg)

        elif self.scaling in {'log', 'log_compounding'}:
            if isinstance(boxsize, str):
                raise ValueError('ValueError: The boxsize must be numeric for log scaling.')
            if boxsize < 0.01:
                raise ValueError('ValueError: The smallest possible boxsize for log-scaled axis is 0.01%')

        elif self.scaling == 'abs':
            if isinstance(boxsize, str):
                raise ValueError('ValueError: The boxsize must be numeric for abs scaling.')
            if boxsize < 0:
                raise ValueError('ValueError: The boxsize must be a value greater than 0.')
                
        elif self.scaling == 'atr':
            if boxsize != 'total' and int(boxsize) != boxsize:
                raise ValueError('ValueError: The boxsize must be a integer of periods or \'total\' for atr box scaling.')
                
            if boxsize != 'total':
                atr_boxsize = int(boxsize)
                if atr_boxsize < 0:
                    raise ValueError('ValueError: The boxsize must be a value greater than 0.')

        return boxsize

    def _make_title(self, title):

        if title is None:

            if self.scaling in {'log', 'log_compounding'}:
                title = f'Point & Figure ({self.scaling}|{self.method}) {self.boxsize}% x {self.reversal}'

            elif self.scaling == 'cla':
                title = f'Point & Figure ({self.scaling}|{self.method}) {self.boxsize}@50 x {self.reversal}'

            elif self.scaling == 'abs' or self.scaling == 'atr':
                title = f'Point & Figure ({self.scaling}|{self.method}) {self.boxsize} x {self.reversal}'

        else:

            if self.scaling in {'log', 'log_compounding'}:
                title = f'Point & Figure ({self.scaling}|{self.method}) {self.boxsize}% x {self.reversal} | {title}'

            elif self.scaling == 'cla':
                title = f'Point & Figure ({self.scaling}|{self.method}) {self.boxsize}@50 x {self.reversal} | {title}'

            elif self.scaling == 'abs' or self.scaling == 'atr':
                title = f'Point & Figure ({self.scaling}|{self.method}) {self.boxsize} x {self.reversal} | {title}'

        return title

    def _prepare_ts(self, ts):
        """
        Initiates the time series data and adjust to the required format.
        """

        # bring all keys to lowercase characters
        ts = {key.lower(): val for key, val in ts.items()}
        
        # check if all required keys are available
        if self.method == 'cl':

            if 'close' not in ts:
                raise KeyError("The required key 'close' was not found in ts")

        elif self.method == 'h/l' or self.method == 'l/h':

            if 'low' not in ts:
                raise KeyError("The required key 'low' was not found in ts")

            if 'high' not in ts:
                raise KeyError("The required key 'high' was not found in ts")

        elif self.method == 'hlc':

            if 'close' not in ts:
                raise KeyError("The required key 'close' was not found in ts")

            if 'low' not in ts:
                raise KeyError("The required key 'low' was not found in ts")

            if 'high' not in ts:
                raise KeyError("The required key 'high' was not found in ts")

        elif self.method == 'ohlc':

            if 'close' not in ts:
                raise KeyError("The required key 'close' was not found in ts")

            if 'low' not in ts:
                raise KeyError("The required key 'low' was not found in ts")

            if 'high' not in ts:
                raise KeyError("The required key 'high' was not found in ts")

            if 'open' not in ts:
                raise KeyError("The required key 'open' was not found in ts")
                
        if self.scaling == 'atr':

            if 'close' not in ts:
                raise KeyError("The required key 'close' was not found in ts")

            if 'low' not in ts:
                raise KeyError("The required key 'low' was not found in ts")

            if 'high' not in ts:
                raise KeyError("The required key 'high' was not found in ts")

            if self.boxsize != 'total':
                atr_period = int(self.boxsize)
                if atr_period + 1 > len(ts['close']):
                    raise IndexError("ATR boxsize is larger than length of data.")
                
        # bring all inputs to the final format as dict with numpy.ndarrays.
        for key in ts.keys():
            if isinstance(ts[key], list):
                ts[key] = np.array(ts[key])
            if not type(ts[key]) == np.ndarray:
                if type(ts[key]) == str or float or int:
                    ts[key] = np.array([ts[key]])

        # if ts['date'] exist check for the type, if it's a string convert
        # to datetime64 else create index of integers.
        # If the string can't converted to datetime64 create index of integers.
        if 'date' not in ts:
            first_key = next(iter(ts))
            ts['date'] = np.arange(0, ts[first_key].shape[0])

        if isinstance(ts['date'][0], str):

            try:
                ts['date'] = ts['date'].astype('datetime64')

                datetime_diff = ts['date'][0:-1] - ts['date'][1:]

                if any(np.mod(datetime_diff / np.timedelta64(1, "D"), 1) != 0):
                    self.time_step = 'm'
                elif any(np.mod(datetime_diff / np.timedelta64(1, "D"), 1) == 0):
                    self.time_step = 'D'
                else:
                    self.time_step = None

            except ValueError:
                warn('Date string can`t be converted to datetime64. Date is set to index of integers')
                ts['date'] = np.arange(0, ts['close'].shape[0])

        # if date is datetime64 check if last date in array is the latest and
        # flip the array if not.
        if isinstance(ts['date'][0], np.datetime64):
            if ts['date'][0] > ts['date'][-1]:
                for key in ts.keys():
                    ts[key] = np.flip(ts[key])

            datetime_diff = ts['date'][0:-1] - ts['date'][1:]

            if any(np.mod(datetime_diff / np.timedelta64(1, "D"), 1) != 0):
                self.time_step = 'm'
            elif any(np.mod(datetime_diff / np.timedelta64(1, "D"), 1) == 0):
                self.time_step = 'D'
            else:
                self.time_step = None

        if not isinstance(ts['date'][0], np.datetime64):
            ts['date'] = np.arange(0, ts['date'].shape[0])

        # check if all arrays have the same length
        length = [x.shape[0] for x in ts.values()]
        if not all(x == length[0] for x in length):
            raise IOError('All arrays in the time-series must have the same length')

        return ts

    def _get_boxscale(self, overscan=None):
        """
        creates the box scale for Point and Figure Chart
        """

        if self.method == 'cl':
            minimum = np.min(self.ts['close'])
            maximum = np.max(self.ts['close'])
        else:
            minimum = np.min(self.ts['low'])
            maximum = np.max(self.ts['high'])

        # initiate variable for boxscale
        boxes = np.array([])

        # initiate overscan range for top and bottom of the scale
        overscan_top = 0
        overscan_bot = 0

        # define range for overscan. If no value is given take the reversal
        if overscan is None:
            overscan = 20  # self.reversal

        if type(overscan) == int:
            overscan_bot = overscan
            overscan_top = overscan
        elif type(overscan) == list or type(overscan) == tuple:
            overscan_bot = overscan[0]
            overscan_top = overscan[1]

        # make scale for absolute scaling
        if self.scaling == 'abs' or self.scaling == 'atr':
            if self.scaling == 'atr':
                
                # Calculate components of the True Range
                if self.boxsize == 'total':
                    p = len(self.ts['close']) - 1
                else:
                    p = int(self.boxsize)
                high_low = self.ts['high'][-p:] - self.ts['low'][-p:]
                high_close_prev = np.abs(self.ts['high'][-p:] - self.ts['close'][-p-1:-1])
                low_close_prev = np.abs(self.ts['low'][-p:] - self.ts['close'][-p-1:-1])
                
                # Combine and find the maximum for each day to get the True Range, excluding the first day due to shift
                true_range = np.maximum(np.maximum(high_low, high_close_prev), low_close_prev)
                
                # Calculate a single average value for the True Range, to be used as the box size
                self.boxsize = float(np.mean(true_range))
                
                self.scaling = 'abs'
                
            decimals = len(str(self.boxsize).split(".")[-1])

            boxes = np.array([0.0], dtype=np.float64)
            boxsize = np.round(np.float64(self.boxsize), decimals)

            while boxes[0] <= minimum - (overscan_bot + 1) * boxsize:
                boxes[0] = np.round(boxes[0] + boxsize, decimals)

            n = 0
            while boxes[n] <= maximum + (overscan_top - 1) * boxsize:
                boxes = np.append(boxes, np.round(boxes[n] + boxsize, decimals))
                n += 1

        # make scale for logarithmic scaling
        elif self.scaling in {'log', 'log_compounding'}:

            boxsize = np.float64(self.boxsize)
            minval = 0.0001  # minimum value for log-scaled axis

            boxes = np.array([np.log(minval)])
            log_boxsize = np.log(1 + boxsize / 100)

            while boxes[0] <= np.log(minimum) - (overscan_bot + 1) * log_boxsize:
                boxes[0] = boxes[0] + log_boxsize

            n = 0
            while boxes[n] <= np.log(maximum) + (overscan_top - 1) * log_boxsize:
                boxes = np.append(boxes, boxes[n] + log_boxsize)
                n += 1

            boxes = np.exp(boxes)

            if boxsize >= 0.1:
                boxes = np.where((boxes >= 0.1) & (boxes < 1), np.round(boxes, 5), boxes)
                boxes = np.where((boxes >= 1) & (boxes < 10), np.round(boxes, 4), boxes)
                boxes = np.where((boxes >= 10) & (boxes < 100), np.round(boxes, 3), boxes)
                boxes = np.where(boxes >= 100, np.round(boxes, 2), boxes)

        # make scale for classic scaling
        elif self.scaling == 'cla':

            f = float(self.boxsize)
            s = np.array([0.2, 0.5, 1], dtype=np.float64) * f

            b1 = np.arange(6, 14 - s[0], s[0])
            b2 = np.arange(14, 29 - s[1], s[1])
            b3 = np.arange(29, 60 - s[2], s[2])

            b0 = np.asarray(np.hstack((b1, b2, b3)), dtype=np.float64) / 10000.0

            g = np.array([1])
            boxes = np.append(0, b0 * g)

            while boxes[-overscan_top - 1] < maximum:
                g = g * 10
                boxes = np.append(boxes, np.round(b0 * g, 5))

            start = np.where(boxes <= minimum)[0][-1] - overscan_bot
            if start < 0:
                start = 0
            end = np.where(boxes > maximum)[-1][0] + overscan_top

            boxes = boxes[start:end]

        return boxes

