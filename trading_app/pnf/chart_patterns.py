# -*- coding: utf-8 -*-
"""Pattern and trendline helpers for PointFigureChart.

This module reads completed chart matrix data to detect breakouts and
trendlines. It does not build columns, calculate order targets, or place trades.
"""

from __future__ import annotations

from typing import Any
from warnings import warn

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle

from .chart_shared import BEARISH, BULLISH, BoxSize, DateTimeUnit, SIGNAL_TYPES, tabulate


class ChartPatternMixin:
    action_index_matrix: np.ndarray | None
    breakouts: Any
    matrix: np.ndarray
    time_step: DateTimeUnit | None
    trendlines: Any
    ts: dict[str, np.ndarray]

    def get_breakouts(self):
        """
        Gets the breakouts of an PointFigureChart object

        Returns:
        ========

        breakouts: dict
            The dict contains following keys:
        breakouts['trend']:
            Array of int: 1 for bullish breakouts and -1 for bearish breakouts
        breakouts['type']:
            Array of str: continuation; fulcrum, resistance or reversal
        breakouts['hits']:
            Array of int: Values represent number of how often the
            line has been hit before the breakout.
        breakouts['width']:
            elements contain int of how long the line is
            between the first hit and the breakout.
        breakouts['outer width']:
            elements contain int of how long the line is from the breakout to
            the last filled box in previous columns on the same level.
            If there is no filled column the signal is counted as conti signal
            and the first column of the PointFigureChart is used to calculate the
            outer width.
        """

        mtx = self.matrix
        action_index_matrix = self.action_index_matrix
        if action_index_matrix is None:
            raise RuntimeError('action_index_matrix has not been initialized.')

        a = np.zeros([np.size(mtx, 0), 1])
        b = mtx[:, 1:] - mtx[:, :-1]

        # find potential bullish breakouts
        T = np.concatenate((a, b), axis=1)
        T[(T < 1) | (mtx < 1)] = 0

        # row and col index of potential breakouts
        row_bull, col_bull = np.where(T == 1)

        # find potential bearish breakouts
        T = np.concatenate((a, b), axis=1)
        T[(T < -1) | (mtx > -1)] = 0

        # row and col index of potential breakouts
        row_bear, col_bear = np.where(T == -1)

        # initiate dictionary
        keys = ['ts index','trend', 'type', 'column index', 'box index', 'hits', 'width', 'outer width']
        bo = {}
        for key in keys:
            bo[key] = np.zeros(np.size(row_bull) + np.size(row_bear)).astype(int)
        bo['type'] = bo['type'].astype(str)

        if isinstance(self.ts['date'][0], np.datetime64):
            bo['ts index'] = bo['ts index'].astype(f'''datetime64[{self.time_step}]''')
        elif isinstance(self.ts['date'][0], str):
            bo['ts index'] = bo['ts index'].astype(f'''datetime64[{self.time_step}]''')
        else:
            bo['ts index'] = bo['ts index'].astype(int)

        # assign trends
        bo['trend'][0:np.size(row_bull)] = 1
        bo['trend'][np.size(row_bull):np.size(row_bull) + np.size(row_bear)] = -1

        # bullish breakouts
        if np.any(row_bull):

            for n in range(0, np.size(row_bull)):

                bo['box index'][n] = row_bull[n]
                bo['column index'][n] = col_bull[n]
                bo['ts index'][n] = self.ts['date'][action_index_matrix[row_bull[n], col_bull[n]]]

                hRL = mtx[row_bull[n] - 1, 0:col_bull[n] + 1]  # horizontal resistance line
                boL = mtx[row_bull[n], 0:col_bull[n] + 1]  # breakout line

                if np.any(np.where(hRL == -1)):
                    i = np.where(hRL == -1)[0][-1]
                else:
                    i = -1

                if np.any(np.where(hRL == 1)):
                    k = np.where(hRL == 1)[0]
                else:
                    k = np.array([], dtype=int)

                k = k[k > i]

                # find type of signal
                z = 0
                if np.any(np.where(boL[:-1] != 0)) and np.size(k) >= 2:
                    z = np.where(boL[:-1] != 0)[0][-1]
                    bo['outer width'][n] = k[-1] - z + 1

                elif np.size(k) >= 2:
                    bo['outer width'][n] = k[-1] + 1

                if z >= 1:

                    if mtx[row_bull[n], z - 1] == 0 and mtx[row_bull[n], z] == 1:
                        bo['type'][n] = 'resistance'

                    elif mtx[row_bull[n], z - 1] == 1 and mtx[row_bull[n], z] == 1:
                        bo['type'][n] = 'resistance'

                    elif mtx[row_bull[n], z - 1] == -1 and mtx[row_bull[n], z] == -1:
                        bo['type'][n] = 'fulcrum'

                    elif mtx[row_bull[n], z - 1] == -1 and mtx[row_bull[n], z] == 1:
                        bo['type'][n] = 'reversal'

                    elif mtx[row_bull[n], z - 1] == 0 and mtx[row_bull[n], z] == -1:
                        bo['type'][n] = 'reversal'

                    elif mtx[row_bull[n], z - 1] == 1 and mtx[row_bull[n], z] == -1:
                        bo['type'][n] = 'reversal'

                    elif mtx[row_bull[n], z - 1] == 0 and mtx[row_bull[n], z] == 0:
                        bo['type'][n] = 'conti'

                elif z == 0:

                    if mtx[row_bull[n], z] == 0:
                        bo['type'][n] = 'conti'

                    elif mtx[row_bull[n], z] == 1:
                        bo['type'][n] = 'conti'

                    elif mtx[row_bull[n], z] == -1:
                        bo['type'][n] = 'reversal'

                if np.size(k) >= 2:
                    bo['hits'][n] = np.size(k)
                    bo['width'][n] = k[-1] - k[0] + 1

                # find smaller breakouts within other breakouts
                if np.size(k) > 2:

                    for p in range(1, np.size(k) - 1):
                        bo['trend'] = np.append(bo['trend'], 1)
                        bo['type'] = np.append(bo['type'], bo['type'][n])
                        bo['column index'] = np.append(bo['column index'], bo['column index'][n])
                        bo['box index'] = np.append(bo['box index'], bo['box index'][n])
                        bo['hits'] = np.append(bo['hits'], np.sum(mtx[row_bull[n] - 1, k[p]:k[-1] + 1]))
                        bo['width'] = np.append(bo['width'], [k[-1] - k[p] + 1])
                        bo['outer width'] = np.append(bo['outer width'], bo['outer width'][n])
                        bo['ts index'] = np.append(bo['ts index'], bo['ts index'][n])

        # bearish breakouts
        if np.any(row_bear):

            for n in range(0, np.size(row_bear)):

                bo['box index'][np.size(row_bull) + n] = row_bear[n]
                bo['column index'][np.size(row_bull) + n] = col_bear[n]
              
                bo['ts index'][np.size(row_bull) + n] = \
                    self.ts['date'][
                        action_index_matrix[
                            row_bear[n],
                            col_bear[n]
                    ]]

                hRL = mtx[row_bear[n] + 1, 0:col_bear[n] + 1]  # horizontal resistance line
                boL = mtx[row_bear[n], 0:col_bear[n] + 1]  # breakout line

                if np.any(np.where(hRL == 1)):
                    i = np.where(hRL == 1)[0][-1]

                else:
                    i = -1

                if np.any(np.where(hRL == -1)):
                    k = np.where(hRL == -1)[0]

                else:
                    k = np.array([], dtype=int)

                k = k[k > i]

                # find type of signal
                z = 0
                if np.any(np.where(boL[:-1] != 0)) and np.size(k) >= 2:
                    z = np.where(boL[:-1] != 0)[0][-1]
                    bo['outer width'][np.size(row_bull) + n] = k[-1] - z + 1

                elif np.size(k) >= 2:
                    bo['outer width'][np.size(row_bull) + n] = k[-1] + 1

                if z >= 1:

                    if mtx[row_bear[n], z - 1] == 0 and mtx[row_bear[n], z] == -1:
                        bo['type'][np.size(row_bull) + n] = 'resistance'

                    elif mtx[row_bear[n], z - 1] == -1 and mtx[row_bear[n], z] == -1:
                        bo['type'][np.size(row_bull) + n] = 'resistance'

                    elif mtx[row_bear[n], z - 1] == 1 and mtx[row_bear[n], z] == 1:
                        bo['type'][np.size(row_bull) + n] = 'reversal'

                    elif mtx[row_bear[n], z - 1] == 1 and mtx[row_bear[n], z] == -1:
                        bo['type'][np.size(row_bull) + n] = 'reversal'

                    elif mtx[row_bear[n], z - 1] == 0 and mtx[row_bear[n], z] == 1:
                        bo['type'][np.size(row_bull) + n] = 'reversal'

                    elif mtx[row_bear[n], z - 1] == -1 and mtx[row_bear[n], z] == 1:
                        bo['type'][np.size(row_bull) + n] = 'reversal'

                    elif mtx[row_bear[n], z - 1] == 0 and mtx[row_bear[n], z] == 0:
                        bo['type'][np.size(row_bull) + n] = 'conti'

                elif z == 0:

                    if mtx[row_bear[n], z] == 0:
                        bo['type'][np.size(row_bull) + n] = 'conti'
                    elif mtx[row_bear[n], z] == -1:
                        bo['type'][np.size(row_bull) + n] = 'conti'
                    elif mtx[row_bear[n], z] == 1:
                        bo['type'][np.size(row_bull) + n] = 'reversal'

                if np.size(k) >= 2:
                    bo['hits'][np.size(row_bull) + n] = np.size(k)
                    bo['width'][np.size(row_bull) + n] = k[-1] - k[0] + 1

                # find smaller breakouts within other breakouts
                if np.size(k) > 2:

                    for p in range(1, np.size(k) - 1):
                        bo['trend'] = np.append(bo['trend'], -1)
                        bo['type'] = np.append(bo['type'], bo['type'][np.size(row_bull) + n])
                        bo['column index'] = np.append(bo['column index'], bo['column index'][np.size(row_bull) + n])
                        bo['box index'] = np.append(bo['box index'], bo['box index'][np.size(row_bull) + n])
                        bo['hits'] = np.append(bo['hits'], np.abs(np.sum(mtx[row_bear[n] + 1, k[p]:k[-1] + 1])))
                        bo['width'] = np.append(bo['width'], [k[-1] - k[p] + 1])
                        bo['outer width'] = np.append(bo['outer width'], bo['outer width'][np.size(row_bull) + n])
                        bo['ts index'] = np.append(bo['ts index'], bo['ts index'][np.size(row_bull) + n])

        # find index without entries:
        x = np.argwhere(bo['hits'] == 0)
        for key in bo.keys():
            bo[key] = np.delete(bo[key], x)

        # sort order: col , row, hits
        T = np.column_stack((bo['column index'], bo['box index'], bo['hits']))
        idx = np.lexsort((T[:, 2], T[:, 1], T[:, 0]))
        for key, value in bo.items():
            bo[key] = bo[key][idx]

        self.breakouts = bo

        return bo

    def get_trendlines(self, length=4, mode='strong'):
        """
        Gets trendlines of an PointfigChart object

        Parameter:
        ==========

        length: int
            minimum length for trendlines default(4).
        mode: str
            'strong' or 'weak' default('strong')
            Strong trendlines break is the line hits a filled box whereas weak lines
            break after a breakout in the other direction occurred above a bearish
            resistance line or below a bullish support line.

        Returns:
        ========

        trendlines: dict
            trendlines['bounded']:
                Array of str: Trendlines are bounded 'internal' or 'external'.
            trendlines['type']: str
                Array of str: Trendlines are 'bullish support' or 'bearish resistance' lines.
            trendlines['length']: int
                Array of int: Length of the trendline.
            trendlines['column index']: int
                Array of int: Index of column where the trendline starts.
            trendlines['box index']: int
                Array of int: Index of row where the trendline starts.
        """

        mtx = self.matrix.copy()

        # correct/initiate minimum length for trendlines:
        if mode == 'weak' and length <= 3:
            length = 4
            warn('Set trendline length to 4. Minimum Length for trendlines of mode=weak is 4.')

        elif mode == 'strong' and length <= 2:
            length = 3
            warn('Set trendline length to 3. Minimum Length for trendlines of mode=strong is 3.')

        # if there is just 1 box filled in first column of mtx add another one
        # to prevent letting trendlines run out of range.
        if np.sum(np.abs(mtx[:, 0])) == 1:

            if np.sum(mtx[:, 0]) > 0:
                idx = np.where(mtx[:, 0] != 0)[0][-1]
                mtx[idx - 1, 0] = 1

            elif np.sum(mtx[:, 0]) > 0:
                idx = np.where(mtx[:, 0] != 0)[0][0]
                mtx[idx + 1, 0] = 1

        # find high and low index for each column; sign indicates trend direction
        T = [np.repeat([np.arange(1, np.size(mtx, 0) + 1, 1)], np.size(mtx, 1), axis=0)][0].transpose() * mtx
        T = np.abs(T)

        ceil = np.zeros(np.size(T, 1)).astype(int)
        floor = np.zeros(np.size(T, 1)).astype(int)

        for n in range(0, np.size(T, 1)):

            high = np.max(T[:, n])
            low = np.min(T[np.where(T[:, n] != 0), n])

            ceil[n] = np.where(T[:, n] == high)[0][0]

            if np.sign(mtx[ceil[n], n]) < 0:
                ceil[n] = ceil[n] * (-1)

            floor[n] = np.where(T[:, n] == low)[0][0]

            if np.sign(mtx[floor[n], n]) < 0:
                floor[n] = floor[n] * (-1)

        # extent mtx in variable T to prevent that trendlines run out of the
        # matrix the offset will be later removed from the data
        offset = np.size(mtx, 1)

        T = np.vstack((np.zeros([np.size(mtx, 1), np.size(mtx, 1)]),
                       mtx,
                       np.zeros([np.size(mtx, 1), np.size(mtx, 1)])
                       )).astype(int)

        T = np.hstack((T, np.zeros([np.size(T, 0), length - 1])))

        # add ones in the last column to stop the latest trendlines
        T = np.hstack((T, np.ones([np.size(T, 0), 1])))

        # new indices after extension
        ceil[ceil > 0] = ceil[ceil > 0] + offset
        ceil[ceil < 0] = ceil[ceil < 0] - offset

        floor[floor > 0] = floor[floor > 0] + offset
        floor[floor < 0] = floor[floor < 0] - offset

        # initiate tl_mtx as matrix containing all possible trendlines
        tl_mtx = np.zeros([np.size(T, 0), np.size(T, 1)])

        if mode == 'weak':

            # initiate matrix for breakpoints for trendlines
            brkpt = np.zeros([np.size(T, 0), np.size(T, 1)])
            # brkpt[:,-1] = 1

            # check if breakouts have been initiated earlier
            if self.breakouts is None:
                bo = self.get_breakouts()

            else:
                bo = self.breakouts

            col = bo['column index'][bo['trend'] == 1]
            row = bo['box index'][bo['trend'] == 1] + offset
            brkpt[row, col] = 1

            col = bo['column index'][bo['trend'] == -1]
            row = bo['box index'][bo['trend'] == -1] + offset
            brkpt[row, col] = -1

            # fill tl_mtx with the length of the trendline at the position of
            # the starting point

            # bearish resistance line starts above every X-column and moves downwards
            # with an 45°-angle until a buy signal is hit or above the line
            for n in range(0, np.size(floor)):

                if ceil[n] > 0:
                    k = ceil[n] + 1
                    col = n

                    while np.sum(brkpt[k:-1, col]) <= 0 and col < np.size(brkpt, 1) - 1:
                        col = col + 1
                        k = k - 1

                    tl_mtx[np.abs(ceil[n]) + 1, n] = n - col

            # bullish support line starts below every O-column and moves upwards with
            # an 45°-angle until a sell signal is hit or below the line
            for n in range(0, np.size(ceil)):

                if floor[n] < 0:
                    k = np.abs(floor[n]) - 1
                    col = n

                    while np.sum(brkpt[0:k, col]) >= 0 and col < np.size(brkpt, 1) - 1:
                        col = col + 1
                        k = k + 1

                    tl_mtx[np.abs(floor[n]) - 1, n] = col - n

            tl_mtx = tl_mtx.astype(int)

            # set all trendlines to zero which are shorter than the minimum length
            tl_mtx[np.abs(tl_mtx) < length] = 0

        # find strong trendlines that will be broken once hit a filled box
        elif mode == 'strong':

            # bearish resistance line starts above every X-column and moves downwards
            # with an 45°-angle until there is any entry different from zero in trendline_mtx
            for n in range(0, np.size(floor)):

                if ceil[n] > 0:
                    k = ceil[n] + 1
                    col = n

                    while T[k, col] == 0:
                        col = col + 1
                        k = k - 1

                    tl_mtx[np.abs(ceil[n]) + 1, n] = n - col

            # bullish support line starts below every O-column and moves upwards with
            # an 45°-angle until there is any entry different from zero in trendline_mtx
            for n in range(0, np.size(ceil)):

                if floor[n] < 0:
                    k = np.abs(floor[n]) - 1
                    col = n

                    while T[k, col] == 0:
                        col = col + 1
                        k = k + 1

                    tl_mtx[np.abs(floor[n]) - 1, n] = col - n

            tl_mtx = tl_mtx.astype(int)
            tl_mtx[np.abs(tl_mtx) < length] = 0

        # counter for the loop to exit if an unexpected case occurred
        loop_run = 0

        # find first trendline
        col = 0
        while np.sum(np.abs(tl_mtx[:, col])) == 0:
            col = col + 1

        # initiate variables for the lookup of external trendlines
        iB = np.argwhere(tl_mtx[:, col] != 0)[0]  # index of last Box
        tF = np.sign(tl_mtx[iB, col])[0]  # TrendFlag
        span = np.abs(tl_mtx[iB, col])[0]  # length of trendline

        tl_vec = np.zeros(np.size(tl_mtx, 1))  # tl_vec: 1d vector of trendlines
        tl_vec[col] = span * tF

        while col + span <= np.size(T, 1) - length - 1 and loop_run <= np.size(T, 1):

            # v_down contains trendlines in the current interval moving downwards
            # v_up contains trendlines in the current interval moving upwards
            v_down = tl_mtx[:, col:col + span].copy()
            v_down[v_down > 0] = 0
            v_down = np.sum(v_down, 0)
            v_up = tl_mtx[:, col:col + span].copy()
            v_up[v_up < 0] = 0
            v_up = np.sum(v_up, 0)

            # remove possible trendlines which are touching occupied boxes within
            # the current interval (necessary for "weak" mode - no impact on strong
            # mode)
            if tF == 1:

                for x in range(0, np.size(v_down)):

                    if v_down[x] != 0:
                        a = np.size(v_down) - np.where(v_down == v_down[x])[0][0]
                        b = np.where(v_down == v_down[x])[0][0]
                        z = np.flipud(np.eye(a))
                        iB = np.argwhere(tl_mtx[:, col + b] != 0)[0][0]
                        check = T[iB - np.size(z, 0) + 1:iB + 1, col + b: col + b + np.size(z, 0)]

                        if np.any(check * z):
                            v_down[x] = 0

            elif tF == -1:

                for x in range(0, np.size(v_up)):

                    if v_up[x] != 0:

                        a = np.size(v_up) - np.where(v_up == v_up[x])[0][0]
                        b = np.where(v_up == v_up[x])[0][0]
                        z = np.eye(a)
                        iB = np.argwhere(tl_mtx[:, col + b] != 0)[0][0]  # index of last Box
                        check = T[iB - 1:iB + np.size(z, 0) - 1, col + b: col + b + np.size(z, 0)]

                        if np.any(check * z):
                            v_up[x] = 0

            if tF == 1:

                # direction of current trendline is up
                # create array containing the position(index+1) of elements of v_down
                # which are not zero. The length of the corresponding line is added to
                # the position. If the number is greater than length of variable, the
                # trendline does leave the interval
                check = (v_down < 0) * np.arange(1, np.size(v_down) + 1, 1) + np.abs(v_down)

                if np.any(v_down) == 1:  # there is a reversal trendline in the interval

                    # check if the reversal trendline leaves the interval
                    if np.any(check > np.size(v_down)) == 1:
                        col = col + np.where(check == np.max(check))[0][0]
                        span = np.sum(np.abs(tl_mtx[:, col]))
                        tF = np.sign(np.sum(tl_mtx[:, col]))
                        tl_vec[col] = span * tF

                    # the reversal trendline does not leave the interval
                    else:
                        tl_mtx[:, col + 1:col + span - 1] = 0

                # there is no reversal trendline in the interval
                elif np.any(check) == 0:

                    # go to next trendline regardless of their direction
                    col = col + np.size(check)
                    span = 1

                    while np.sum(np.sum(np.abs(tl_mtx[:, col:col + span]), 0)) == 0:
                        span = span + 1

                    col = col + span - 1
                    span = np.abs(np.sum(tl_mtx[:, col]))
                    tF = np.sign(np.sum(tl_mtx[:, col]))
                    tl_vec[col] = span * tF

            elif tF == -1:

                # direction of current trendline is down
                # create array containing the position(index+1) of elements of v_down
                # which are not zero. The length of the corresponding line is added to
                # the position. If the number is greater than length of variable, the
                # trendline does leave the interval
                check = (v_up > 0) * np.arange(1, np.size(v_up) + 1, 1) + v_up

                # there is a reversal trendline in the interval
                if np.any(v_up) == 1:

                    # check if the reversal trendline leaves the interval
                    if np.any(check > np.size(v_up)) == 1:
                        col = col + np.where(check == np.max(check))[0][0]
                        span = np.sum(np.abs(tl_mtx[:, col]))
                        tF = np.sign(np.sum(tl_mtx[:, col]))
                        tl_vec[col] = span * tF

                    # the reversal trendline does not leave the interval
                    else:
                        tl_mtx[:, col + 1:col + span - 1] = 0

                # there is no reversal trendline in the interval
                elif np.any(check) == 0:

                    # go to next trendline despite of their direction
                    col = col + np.size(check)
                    span = 1

                    while np.sum(np.sum(np.abs(tl_mtx[:, col:col + span]), 0)) == 0:
                        span = span + 1

                    col = col + span - 1
                    span = np.abs(np.sum(tl_mtx[:, col]))
                    tF = np.sign(np.sum(tl_mtx[:, col]))
                    tl_vec[col] = span * tF

            loop_run += 1

            if loop_run >= np.size(T, 1):
                # raise IndexError('An unexpected case occurred during evaluating the trendlines.')
                break

        # prepare returned variable for trendlines
        row, col = np.where(tl_mtx != 0)

        tlines = {'bounded': np.zeros(np.size(col)).astype(str),
                  'type': np.zeros(np.size(col)).astype(str),
                  'length': np.zeros(np.size(col)).astype(int),
                  'column index': np.zeros(np.size(col)).astype(int),
                  'box index': np.zeros(np.size(col)).astype(int)
                  }

        for n in range(0, np.size(col)):

            # check for bounding
            if tl_vec[col[n]] != 0:
                tlines['bounded'][n] = 'external'
            else:
                tlines['bounded'][n] = 'internal'

            tlines['column index'][n] = col[n]
            tlines['box index'][n] = row[n] - offset

            # the latest trendlines can be shorter than the minimum length.
            # correct the latest trendlines to the actual length.
            if np.abs(tl_mtx[row[n], col[n]]) + col[n] >= np.size(mtx, 1):
                tlines['length'][n] = np.abs(tl_mtx[row[n], col[n]]) - length + 1

            else:
                tlines['length'][n] = np.abs(tl_mtx[row[n], col[n]])

            if tl_mtx[row[n], col[n]] > 0:
                tlines['type'][n] = 'bullish support'

            else:
                tlines['type'][n] = 'bearish resistance'

        # find  and delete index without entries
        x = np.argwhere(tlines['length'] == 0)
        for key in tlines.keys():
            tlines[key] = np.delete(tlines[key], x)

        # sort columns
        idx = np.argsort(tlines['column index'])
        for key, value in tlines.items():
            tlines[key] = tlines[key][idx]

        self.trendlines = tlines

        return tlines

