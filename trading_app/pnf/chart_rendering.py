# -*- coding: utf-8 -*-
"""Text rendering helpers for PointFigureChart.

This module turns completed chart data into printable tables and summaries for
inspection. It does not change chart structure, signals, counts, or trading
state.
"""

from __future__ import annotations

from typing import Any
from warnings import warn

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle

from .chart_shared import BEARISH, BULLISH, BoxSize, DateTimeUnit, SIGNAL_TYPES, tabulate


class ChartRenderingMixin:
    boxscale: np.ndarray
    matrix: np.ndarray
    print_columns: int
    title: str
    trendlines: Any

    def __str__(self):

        mtx = self.matrix
        boxes = self.boxscale.copy()

        print_mtx = self.matrix.copy()
        last_trendline = []
        last_trendline_length = []

        if self.trendlines is not None:
            tlines = self.trendlines

            for n in range(0, np.size(tlines['column index'])):

                if tlines['bounded'][n] == 'external':

                    if tlines['type'][n] == 'bullish support':

                        last_trendline = 'bullish support'
                        last_trendline_length = tlines['length'][n]
                        c = tlines['column index'][n]
                        r = tlines['box index'][n]

                        if mtx[r, c] == 0:
                            print_mtx[r, c] = 2
                        k = 1

                        while k < tlines['length'][n] and c < np.shape(mtx)[1] - 1:

                            c = c + 1
                            r = r + 1
                            k = k + 1

                            if mtx[r, c] == 0:
                                print_mtx[r, c] = 2

                    elif tlines['type'][n] == 'bearish resistance':

                        last_trendline = 'bearish resistance'
                        last_trendline_length = tlines['length'][n]
                        c = tlines['column index'][n]
                        r = tlines['box index'][n]

                        if mtx[r, c] == 0:
                            print_mtx[r, c] = -2
                        k = 1

                        while k < tlines['length'][n] and c < np.shape(mtx)[1] - 1:

                            c = c + 1
                            r = r - 1
                            k = k + 1

                            if mtx[r, c] == 0:
                                print_mtx[r, c] = -2

        columns = self.print_columns
        total_columns = np.shape(mtx)[1]

        if columns >= total_columns:
            columns = total_columns

        print_mtx = print_mtx[:, -columns:]
        idx = np.where(np.sum(np.abs(mtx[:, -columns:]), axis=1) != 0)[0]
        boxes = boxes[idx]
        print_mtx = print_mtx[idx, :]

        print_mtx = np.flipud(print_mtx).astype(str)
        boxes = np.flipud(boxes).astype(str)

        n = 0
        table = []
        for m in range(len(boxes)):

            row = print_mtx[m, :]
            row = [s.replace('0', '.') for s in row]
            row = [s.replace('-1', 'O') for s in row]
            row = [s.replace('1', 'X') for s in row]
            row = [s.replace('-2', '*') for s in row]
            row = [s.replace('2', '*') for s in row]
            row = np.hstack((boxes[m], row, boxes[m]))

            if n == 0:
                table = row
            else:
                table = np.vstack((table, row))
            n += 1

        table = tabulate(table, tablefmt='simple')

        print(self.title)
        print(table)

        if self.trendlines is not None:
            print(f'last trendline: {last_trendline} line of length {last_trendline_length}')
        return f'printed {columns}/{total_columns} columns.'

