# -*- coding: utf-8 -*-
"""Signal helpers for PointFigureChart.

This module reads completed chart and breakout data to build raw signal arrays.
These arrays are for inspection and strategy validation; broker execution and
order approval stay outside chart_pnf.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING
from warnings import warn

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle

from .chart_shared import BEARISH, BULLISH, BoxSize, DateTimeUnit, SIGNAL_TYPES, tabulate


class ChartSignalMixin:
    action_index_matrix: np.ndarray
    boxscale: np.ndarray
    breakouts: Any
    buys: dict[str, Any]
    highs_lows_heights_trends: Any
    matrix: np.ndarray
    pnf_timeseries: dict[str, Any]
    reversal: int
    sells: dict[str, Any]
    signals: Any
    ts_signals_map: Any

    if TYPE_CHECKING:
        def get_breakouts(self) -> Any: ...

    @staticmethod
    def _signal_window_start(column_index: Any, width: Any) -> int:
        return max(0, int(column_index) - int(width))

    def _signal_ts_index(self, box_index: Any, column_index: Any) -> int:
        row_index = min(max(int(box_index), 0), np.size(self.action_index_matrix, 0) - 1)
        return int(self.action_index_matrix[row_index, int(column_index)])

    def next_simple_signal(self):

        next_buy = np.nan
        next_sell = np.nan

        # last trend need to be identified from pnfts
        idx = np.where(~np.isnan(self.pnf_timeseries['trend']))[0][-1]

        last_trend = int(self.pnf_timeseries['trend'][idx])

        if np.shape(self.matrix)[1] >= 3:

            mtx = self.matrix.copy()
            mtx = mtx[:, -3:]

            x_col_1 = np.where(mtx[:, 0] == 1)[0]
            x_col_2 = np.where(mtx[:, 1] == 1)[0]
            x_col_3 = np.where(mtx[:, 2] == 1)[0]

            o_col_1 = np.where(mtx[:, 0] == -1)[0]
            o_col_2 = np.where(mtx[:, 1] == -1)[0]
            o_col_3 = np.where(mtx[:, 2] == -1)[0]

            if last_trend == 1:

                if np.any(x_col_2):
                    idx = x_col_2[-1]
                else:
                    idx = x_col_1[-1]

                if idx + 1 > x_col_3[-1]:
                    # if idx  > x_col_3[-1]:
                    next_buy = self.boxscale[idx + 1]
                else:
                    next_buy = np.nan

                if np.any(o_col_3):
                    idx = o_col_3[0]
                else:
                    idx = o_col_2[0]

                next_sell = self.boxscale[idx - 1]

            elif last_trend == -1:

                if np.any(o_col_2):
                    idx = o_col_2[0]
                else:
                    idx = o_col_1[0]

                if idx - 1 < o_col_3[0]:
                    # if idx < o_col_3[0]:
                    next_sell = self.boxscale[idx - 1]
                else:
                    next_sell = np.nan

                if np.any(x_col_3):
                    idx = x_col_3[-1]
                else:
                    idx = x_col_2[-1]

                next_buy = self.boxscale[idx + 1]

        return next_buy, next_sell

    def multiple_top_buy(self, label, multiple):

        if not self.breakouts:
            self.get_breakouts()

        max_width = 2 * multiple - 1

        array = np.zeros(len(self.pnf_timeseries['box index']))
        array[:] = np.nan

        x = ((self.breakouts['trend'] == 1)
             & (self.breakouts['width'] <= max_width)
             & (self.breakouts['hits'] == multiple))

        col = self.breakouts['column index'][x]
        row = self.breakouts['box index'][x]

        for r, c in zip(row, col):
            col_idx = (self.pnf_timeseries['column index'] == c)
            row_idx = self.pnf_timeseries['box index'][col_idx]
            ts_idx = int(row_idx[row_idx >= r][0])
            x = ((self.pnf_timeseries['box index'] == ts_idx) & (self.pnf_timeseries['column index'] == c))
            array[x] = self.boxscale[r]

        self.buys[label] = array

    def multiple_bottom_sell(self, label, multiple):

        if not self.breakouts:
            self.get_breakouts()

        max_width = 2 * multiple - 1

        array = np.zeros(len(self.pnf_timeseries['box index']))
        array[:] = np.nan

        x = ((self.breakouts['trend'] == -1)
             & (self.breakouts['width'] <= max_width)
             & (self.breakouts['hits'] == multiple))

        col = self.breakouts['column index'][x]
        row = self.breakouts['box index'][x]

        for r, c in zip(row, col):
            col_idx = (self.pnf_timeseries['column index'] == c)
            row_idx = self.pnf_timeseries['box index'][col_idx]
            ts_idx = int(row_idx[row_idx <= r][0])
            x = ((self.pnf_timeseries['box index'] == ts_idx) & (self.pnf_timeseries['column index'] == c))
            array[x] = self.boxscale[r]

        self.sells[label] = array

    def double_top_buy(self):

        self.multiple_top_buy(label='DTB', multiple=2)

    def double_bottom_sell(self):

        self.multiple_bottom_sell(label='DBS', multiple=2)

    def triple_top_buy(self):

        self.multiple_top_buy(label='TTB', multiple=3)

    def triple_bottom_sell(self):

        self.multiple_bottom_sell(label='TBS', multiple=3)

    def get_highs_lows_heights_trends(self):
        """
        Helper function to get the highs, lows, heights and trends of the Point and Figure chart.
        """
        
        mtx = self.matrix
        # find high and low index for each column; sign indicates trend direction
        T = [np.repeat([np.arange(1, np.size(mtx, 0) + 1, 1)], np.size(mtx, 1), axis=0)][0].transpose() * mtx

        highs = np.zeros(np.size(mtx, 1), dtype=int)
        lows = np.zeros(np.size(mtx, 1), dtype=int)
        heights = np.zeros(np.size(mtx, 1))
        trends = np.zeros(np.size(mtx, 1))

        for n in range(0, np.size(mtx, 1)):
            column = T[np.where(T[:, n] != 0), n]
            abscolumn = np.abs(column)
            highs[n] = np.max(abscolumn)
            lows[n] = np.min(abscolumn)
            heights[n] = highs[n] - lows[n] + 1
            trends[n] = np.sign(column[0][0])

        self.highs_lows_heights_trends = (highs, lows, heights, trends)
        return self.highs_lows_heights_trends

    def get_buy_sell_signals(self):
        """
        Returns the buy and sell signals of the Point and Figure chart.
        """

        self._init_signals()

        if not self.highs_lows_heights_trends:
            self.get_highs_lows_heights_trends()

        highs, lows, heights, trends = self.highs_lows_heights_trends

        for n in range(2, np.size(highs), 1):
            colindex = n
            # don't overwrite existing signals
            if self.signals['width'][n] == 0:
                if trends[n] == 1:
                    if highs[n] > highs[n - 2]:
                        boxindex = highs[n]
                        self.signals['box index'][colindex] = boxindex
                        self.signals['width'][colindex] = 3
                        self.signals['type'][colindex] = 0
                        self.signals['top box index'][colindex] = highs[n]
                        self.signals['bottom box index'][colindex] = lows[n - 1]

                        ts_index = self._signal_ts_index(boxindex, colindex)
                        self.signals['ts index'][colindex] = ts_index
                        self.ts_signals_map[ts_index] = colindex

                if trends[n] == -1:
                    if lows[n] < lows[n - 2]:
                        boxindex = lows[n]
                        self.signals['box index'][colindex] = boxindex
                        self.signals['width'][colindex] = 3
                        self.signals['type'][colindex] = 1
                        self.signals['top box index'][colindex] = highs[n - 1]
                        self.signals['bottom box index'][colindex] = lows[n]

                        ts_index = self._signal_ts_index(boxindex, colindex)
                        self.signals['ts index'][colindex] = ts_index
                        self.ts_signals_map[ts_index] = colindex

        return self.signals

    def get_triangles(self, strict=False):
        """
        Returns the triangles of the Point and Figure chart.
        """

        self._init_signals()
        
        if not self.highs_lows_heights_trends:
            self.get_highs_lows_heights_trends()

        highs, lows, heights, trends = self.highs_lows_heights_trends

        if not self.breakouts:
            self.get_breakouts()
        for n in range(0, np.size(self.breakouts["trend"])):
            trend = self.breakouts["trend"][n]
            if self.breakouts["width"][n] == 3:
                i = self.breakouts["column index"][n] - 1
                height = heights[i] + 2
                high = highs[i] + 1
                i -= 1
                hits = 1
                if strict:
                    while (height == heights[i]) \
                        and (highs[i] == high) and (i > 0):
                            height = heights[i] + 2
                            high = highs[i] + 1
                            hits += 1
                            i -= 1
                else: 
                    while (height == heights[i] or height-1 == heights[i] or height+1 == heights[i]) \
                        and (highs[i] == high or highs[i] == high-1 or highs[i] == high + 1) and (i > 0):
                        height = heights[i] + 2
                        high = highs[i] + 1
                        hits += 1
                        i -= 1
        
                if hits > 3:
                    colindex = self.breakouts["column index"][n]
                    boxindex = self.breakouts["box index"][n]
                    self.signals['box index'][colindex] = boxindex
                    self.signals['width'][colindex] = hits
                    self.signals['type'][colindex] = trend == 1 and 14 or 15
                    self.signals['top box index'][colindex] = np.max(highs[colindex - hits:colindex])
                    self.signals['bottom box index'][colindex] = np.min(lows[colindex - hits:colindex])

                    ts_index = self._signal_ts_index(boxindex, colindex)
                    self.signals['ts index'][colindex] = ts_index
                    self.ts_signals_map[ts_index] = colindex

        return self.signals

    def get_high_low_poles(self):
        """
        Returns the high and low poles of the Point and Figure chart.
        """
        
        self._init_signals()

        if not self.highs_lows_heights_trends:
            self.get_highs_lows_heights_trends()

        highs, lows, heights, trends = self.highs_lows_heights_trends

        for n in np.arange(1, np.size(heights) - 1, 1):
            # high pole is any column that is three or more boxes higher than previous high column followed by a column that reverses 50% of the column
            if trends[n] == 1 and highs[n] > highs[n - 2] + 3 and heights[n]/heights[n + 1] > 0.5:
                colindex = n + 1
                boxindex = lows[n + 1]
                self.signals['box index'][colindex] = boxindex
                self.signals['width'][colindex] = 3
                self.signals['type'][colindex] = 21
                self.signals['top box index'][colindex] = highs[n]
                self.signals['bottom box index'][colindex] = lows[n - 1]

                ts_index = self._signal_ts_index(boxindex, colindex)
                self.signals['ts index'][colindex] = ts_index
                self.ts_signals_map[ts_index] = colindex

            # low pole is any column that is three or more boxes lower than previous low column followed by a column that reverses 50% of the column
            if trends[n] == -1 and lows[n] < lows[n - 2] - 3 and heights[n]/heights[n + 1] > 0.5:
                colindex = n + 1
                boxindex = highs[n + 1] - 1
                self.signals['box index'][colindex] = boxindex
                self.signals['width'][colindex] = 3
                self.signals['type'][colindex] = 22
                self.signals['top box index'][colindex] = highs[n - 1]
                self.signals['bottom box index'][colindex] = lows[n]

                ts_index = self._signal_ts_index(boxindex, colindex)
                self.signals['ts index'][colindex] = ts_index
                self.ts_signals_map[ts_index] = colindex

        return self.signals

    def get_traps(self):
        """
        Returns the traps of the Point and Figure chart.

        A bull trap is a triple top breakout with only one box breakout followed by a reversal
        A bear trap is a triple bottom breakdown with only one box breakdown followed by a reversal
        """

        
        self._init_signals()

        if not self.breakouts:
            self.get_breakouts()
        if not self.highs_lows_heights_trends:
            self.get_highs_lows_heights_trends()
        highs, lows, heights, trends = self.highs_lows_heights_trends

        for n in range(0, np.size(self.breakouts['column index']), 1):
            # is triple breakout
            if self.breakouts['hits'][n] == 3 and self.breakouts['width'][n] == 5:
                curcol = self.breakouts['column index'][n]
                prevcol = curcol - 2
                nextcol = curcol + 1

                if nextcol >= np.size(heights):
                    continue

                trend = self.breakouts['trend'][n]

                # if the breakout is one box and the next column reverses
                if trend == 1 and highs[curcol] - highs[prevcol] == 1.0 and heights[nextcol] >= self.reversal:
                    colindex = nextcol
                    boxindex = lows[nextcol]
                    self.signals['box index'][colindex] = boxindex
                    self.signals['width'][colindex] = 6
                    self.signals['type'][colindex] = 18
                    start = self._signal_window_start(nextcol, 5)
                    self.signals['top box index'][colindex] = np.max(highs[start: nextcol])
                    self.signals['bottom box index'][colindex] = np.min(lows[start: nextcol])

                    ts_index = self._signal_ts_index(boxindex, colindex)
                    self.signals['ts index'][colindex] = ts_index
                    self.ts_signals_map[ts_index] = colindex

                 # if the breakdown is one box and the next column reverses
                if trend == -1 and lows[prevcol] - lows[curcol] == 1 and heights[nextcol] >= self.reversal:
                    colindex = nextcol
                    boxindex = highs[nextcol]
                    self.signals['box index'][colindex] = boxindex
                    self.signals['width'][colindex] = 6
                    self.signals['type'][colindex] = 19
                    start = self._signal_window_start(nextcol, 5)
                    self.signals['top box index'][colindex] = np.max(highs[start: nextcol])
                    self.signals['bottom box index'][colindex] = np.min(lows[start: nextcol])

                    ts_index = self._signal_ts_index(boxindex, colindex)
                    self.signals['ts index'][colindex] = ts_index
                    self.ts_signals_map[ts_index] = colindex
                    
        return self.signals

    def get_asc_desc_triple_breakouts(self):
        """
        Returns the triple breakouts of the Point and Figure chart.
        """
        
        self._init_signals()

        if not self.breakouts:
            self.get_breakouts()
        if not self.highs_lows_heights_trends:
            self.get_highs_lows_heights_trends()

        highs, lows, heights, trends = self.highs_lows_heights_trends

        for n in np.arange(1, np.size(self.breakouts['column index']), 1):

            # two consecutive double breakouts in the same direction
            if self.breakouts['hits'][n] == 2 and self.breakouts['width'][n] == 3:
                if self.breakouts['trend'][n] == self.breakouts['trend'][n - 1] \
                    and self.breakouts['column index'][n] - 2 == self.breakouts['column index'][n - 1]:
                    colindex = self.breakouts['column index'][n]
                    boxindex = self.breakouts['box index'][n]
                    self.signals['box index'][colindex] = boxindex
                    self.signals['width'][colindex] = 5
                    self.signals['type'][colindex] = self.breakouts['trend'][n] == 1 and 9 or 10
                    start = self._signal_window_start(colindex, 4)
                    self.signals['top box index'][colindex] = np.max(highs[start: colindex])
                    self.signals['bottom box index'][colindex] = np.min(lows[start: colindex])

                    ts_index = self._signal_ts_index(boxindex, colindex)
                    self.signals['ts index'][colindex] = ts_index
                    self.ts_signals_map[ts_index] = colindex
                    
        return self.signals

    def get_catapults(self):
        """
        Returns the catapults of the Point and Figure chart.
        """
        
        self._init_signals()

        if not self.breakouts:
            self.get_breakouts()
        if not self.highs_lows_heights_trends:
            self.get_highs_lows_heights_trends()

        highs, lows, heights, trends = self.highs_lows_heights_trends

        for n in np.arange(1, np.size(self.breakouts['column index']), 1):
            # one triple breakout followed by a double in the same direction
            if self.breakouts['hits'][n-1] == 3 and self.breakouts['width'][n-1] == 5:
                if self.breakouts['hits'][n] == 2 and self.breakouts['width'][n] == 3 \
                    and self.breakouts['trend'][n] == self.breakouts['trend'][n - 1] \
                    and self.breakouts['column index'][n] - 2 == self.breakouts['column index'][n - 1]:

                    colindex = self.breakouts['column index'][n]
                    boxindex = self.breakouts['box index'][n]
                    self.signals['box index'][colindex] = boxindex
                    self.signals['width'][colindex] = 7
                    self.signals['type'][colindex] = self.breakouts['trend'][n] == 1 and 11 or 12
                    start = self._signal_window_start(colindex, 6)
                    self.signals['top box index'][colindex] = np.max(highs[start: colindex])
                    self.signals['bottom box index'][colindex] = np.min(lows[start: colindex])

                    ts_index = self._signal_ts_index(boxindex, colindex)
                    self.signals['ts index'][colindex] = ts_index
                    self.ts_signals_map[ts_index] = colindex
                    
        return self.signals

    def get_reversed_signals(self):
 
        self._init_signals()

        if not self.breakouts:
            self.get_breakouts()
        if not self.highs_lows_heights_trends:
            self.get_highs_lows_heights_trends()
        
        highs, lows, heights, trends = self.highs_lows_heights_trends

        for n in np.arange(0, np.size(self.breakouts['column index']), 1):
            if self.breakouts['hits'][n] == 2 and self.breakouts['width'][n] == 3:
                if self.breakouts['trend'][n] == 1:
                    colindex = self.breakouts['column index'][n]
                    i = colindex - 1
                    c = 1
                    while(i - 2 > 0 and lows[i] == lows[i - 2] - 1 and highs[i - 1] == highs[i - 3] - 1):
                        i -= 2
                        c += 2
                    if c >= 3:
                        boxindex = self.breakouts['box index'][n]
                        self.signals['box index'][colindex] = boxindex
                        self.signals['width'][colindex] = colindex - i + 1
                        self.signals['type'][colindex] = 13
                        self.signals['top box index'][colindex] = highs[colindex]
                        self.signals['bottom box index'][colindex] = lows[i - 2]

                        ts_index = self._signal_ts_index(boxindex, colindex)
                        self.signals['ts index'][colindex] = ts_index
                        self.ts_signals_map[ts_index] = colindex
                        

                if self.breakouts['trend'][n] == -1:
                    colindex = self.breakouts['column index'][n]
                    i = colindex - 1
                    c = 1
                    while(i - 2 > 0 and highs[i] == highs[i - 2] + 1 and lows[i - 1] == lows[i - 3] + 1):
                        i -= 2
                        c += 2
                    if c >= 3:
                        boxindex = self.breakouts['box index'][n]
                        self.signals['box index'][colindex] = boxindex
                        self.signals['width'][colindex] = colindex - i + 1
                        self.signals['type'][colindex] = 14
                        self.signals['top box index'][colindex] = highs[i - 2]
                        self.signals['bottom box index'][colindex] = lows[colindex]

                        ts_index = self._signal_ts_index(boxindex, colindex)
                        self.signals['ts index'][colindex] = ts_index
                        self.ts_signals_map[ts_index] = colindex
                    
        return self.signals

    def get_double_breakouts(self):
        """
        Returns the double breakouts of the Point and Figure chart.
        """
        
        self._init_signals()

        if not self.breakouts:
            self.get_breakouts()
        if not self.highs_lows_heights_trends:
            self.get_highs_lows_heights_trends()

        highs, lows, heights, trends = self.highs_lows_heights_trends

        for n in np.arange(0, np.size(self.breakouts['column index']), 1):
            if self.breakouts['hits'][n] == 2 and self.breakouts['width'][n] == 3:
                colindex = self.breakouts['column index'][n]
                # don't overwrite more complex signals
                if self.signals['width'][colindex] == 0:
                    boxindex = self.breakouts['box index'][n]
                    self.signals['box index'][colindex] = boxindex
                    self.signals['width'][colindex] = self.breakouts['width'][n]

                    ts_index = self._signal_ts_index(boxindex, colindex)
                    self.signals['ts index'][colindex] = ts_index
                    self.ts_signals_map[ts_index] = colindex
                    
                    if self.breakouts['trend'][n] == 1:
                        self.signals['type'][colindex] = 2
                        self.signals['top box index'][colindex] = highs[colindex]
                        start = self._signal_window_start(colindex, self.breakouts['width'][n])
                        self.signals['bottom box index'][colindex] = np.min(lows[start: colindex])

                    if self.breakouts['trend'][n] == -1:
                        self.signals['type'][colindex] = 3
                        start = self._signal_window_start(colindex, self.breakouts['width'][n])
                        self.signals['top box index'][colindex] = np.max(highs[start: colindex])
                        self.signals['bottom box index'][colindex] = lows[colindex]

        return self.signals

    def get_triple_breakouts(self):
        """
        Returns the triple breakouts of the Point and Figure chart.
        """
        
        self._init_signals()

        if not self.breakouts:
            self.get_breakouts()
        if not self.highs_lows_heights_trends:
            self.get_highs_lows_heights_trends()

        highs, lows, heights, trends = self.highs_lows_heights_trends

        for n in np.arange(0, np.size(self.breakouts['column index']), 1):
            if self.breakouts['hits'][n] == 3 and self.breakouts['width'][n] == 5:
                colindex = self.breakouts['column index'][n]
                boxindex = self.breakouts['box index'][n]
                self.signals['box index'][colindex] = boxindex
                self.signals['width'][colindex] = self.breakouts['width'][n]

                ts_index = self._signal_ts_index(boxindex, colindex)
                self.signals['ts index'][colindex] = ts_index
                self.ts_signals_map[ts_index] = colindex
                
                if self.breakouts['trend'][n] == 1:
                    self.signals['type'][colindex] = 4
                    self.signals['top box index'][colindex] = highs[colindex]
                    start = self._signal_window_start(colindex, self.breakouts['width'][n])
                    self.signals['bottom box index'][colindex] = np.min(lows[start: colindex])

                if self.breakouts['trend'][n] == -1:
                    self.signals['type'][colindex] = 5
                    start = self._signal_window_start(colindex, self.breakouts['width'][n])
                    self.signals['top box index'][colindex] = np.max(highs[start: colindex])
                    self.signals['bottom box index'][colindex] = lows[colindex]

        return self.signals

    def get_spread_triple_breakouts(self):
        """
        Returns the split triple breakouts of the Point and Figure chart.
        """
        
        self._init_signals()

        if not self.breakouts:
            self.get_breakouts()
        if not self.highs_lows_heights_trends:
            self.get_highs_lows_heights_trends()

        highs, lows, heights, trends = self.highs_lows_heights_trends

        for n in np.arange(0, np.size(self.breakouts['column index']), 1):
            if self.breakouts['hits'][n] == 3 and (self.breakouts['width'][n] == 7 or self.breakouts['width'][n] == 9):
                colindex = self.breakouts['column index'][n]
                boxindex = self.breakouts['box index'][n]
                self.signals['box index'][colindex] = boxindex
                self.signals['width'][colindex] = self.breakouts['width'][n]

                ts_index = self._signal_ts_index(boxindex, colindex)
                self.signals['ts index'][colindex] = ts_index
                self.ts_signals_map[ts_index] = colindex
                
                if self.breakouts['trend'][n] == 1:
                    self.signals['type'][colindex] = 19
                    self.signals['top box index'][colindex] = highs[colindex]
                    start = self._signal_window_start(colindex, self.breakouts['width'][n] - 1)
                    self.signals['bottom box index'][colindex] = np.min(lows[start: colindex])

                if self.breakouts['trend'][n] == -1:
                    self.signals['type'][colindex] = 20
                    start = self._signal_window_start(colindex, self.breakouts['width'][n] - 1)
                    self.signals['top box index'][colindex] = np.max(highs[start: colindex])
                    self.signals['bottom box index'][colindex] = lows[colindex]

        return self.signals

    def get_quadruple_breakouts(self):
        """
        Returns the quadruple breakouts of the Point and Figure chart.
        """
        
        self._init_signals()

        if not self.breakouts:
            self.get_breakouts()
        if not self.highs_lows_heights_trends:
            self.get_highs_lows_heights_trends()

        highs, lows, heights, trends = self.highs_lows_heights_trends

        for n in np.arange(0, np.size(self.breakouts['column index']), 1):
            if self.breakouts['hits'][n] == 4 and self.breakouts['width'][n] == 7:
                colindex = self.breakouts['column index'][n]
                boxindex = self.breakouts['box index'][n]
                self.signals['box index'][colindex] = boxindex
                self.signals['width'][colindex] = self.breakouts['width'][n]

                ts_index = self._signal_ts_index(boxindex, colindex)
                self.signals['ts index'][colindex] = ts_index
                self.ts_signals_map[ts_index] = colindex
                
                if self.breakouts['trend'][n] == 1:
                    self.signals['type'][colindex] = 6
                    self.signals['top box index'][colindex] = highs[colindex]
                    start = self._signal_window_start(colindex, self.breakouts['width'][n])
                    self.signals['bottom box index'][colindex] = np.min(lows[start: colindex])

                if self.breakouts['trend'][n] == -1:
                    self.signals['type'][colindex] = 7
                    start = self._signal_window_start(colindex, self.breakouts['width'][n])
                    self.signals['top box index'][colindex] = np.max(highs[start: colindex])
                    self.signals['bottom box index'][colindex] = lows[colindex]

        return self.signals

    def _init_signals(self):
        """
        Initializes the signals of the Point and Figure chart.
        """
        if not self.signals:
            self.signals = {
                'box index': np.zeros(np.size(self.matrix, 1), dtype=int),
                'top box index': np.zeros(np.size(self.matrix, 1), dtype=int),
                'bottom box index': np.zeros(np.size(self.matrix, 1), dtype=int),
                'type': np.zeros(np.size(self.matrix, 1), dtype=int),
                'width': np.zeros(np.size(self.matrix, 1), dtype=int),
                'ts index': np.zeros(np.size(self.matrix, 1), dtype=int)
            }
            self.ts_signals_map = np.zeros(np.size(self.pnf_timeseries['box index']), dtype=int)

    def get_signals(self):
        """
        https://school.stockcharts.com/doku.php?id=chart_analysis:pnf_charts:pnf_alerts

        Returns the patterns of the Point and Figure chart.
        """

        self.get_triangles()
        self.get_high_low_poles()
        self.get_traps()
        self.get_asc_desc_triple_breakouts()
        self.get_catapults()
        self.get_reversed_signals()
        self.get_spread_triple_breakouts()
        self.get_triple_breakouts()
        self.get_quadruple_breakouts()
        # get double breakouts after more complex signals so they don't overwrite more complex signals
        self.get_double_breakouts()
        # get simple signals last so they don't overwrite more complex signals
        self.get_buy_sell_signals()

        return self.signals

