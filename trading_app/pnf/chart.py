# -*- coding: utf-8 -*-
#
# pyPnF
# A Package for Point and Figure Charting
# https://github.com/swaschke/pypnf
#
# Copyright (C) 2021  Stefan Waschke
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.

"""Main PointFigureChart class.

This module combines the setup, engine, pattern, signal, count, rendering, and
plotting mixins into one chart object. It owns chart initialization only; broker,
storage, strategy execution, and order logic stay outside chart_pnf.
"""

from __future__ import annotations

from typing import Any, Literal

from matplotlib import pyplot as plt

from .chart_counts import ChartCountMixin
from .chart_engine import ChartEngineMixin
from .chart_indicators import ChartIndicatorMixin
from .chart_patterns import ChartPatternMixin
from .chart_plotting import ChartPlottingMixin
from .chart_rendering import ChartRenderingMixin
from .chart_setup import ChartSetupMixin
from .chart_shared import BoxSize, DateTimeUnit
from .chart_signals import ChartSignalMixin

ShowTrendlines = Literal["external", "internal", "both", False]


class PointFigureChart(
    ChartSetupMixin,
    ChartEngineMixin,
    ChartPatternMixin,
    ChartIndicatorMixin,
    ChartSignalMixin,
    ChartCountMixin,
    ChartPlottingMixin,
    ChartRenderingMixin,
):
    """ Class to build a Point and Figure Chart from time series data

    Required attributes:
    ====================

    ts: dict
        with keys ['date','open','high','low','close',volume']
    ts['date']:
        Optional. Array or value of type str
    ts['open']:
        Array or value of type float
    ts['high']:
        Array or value of type float
    ts['low']:
        Array or value of type float
    ts['close']:
        Array or value of type float
    ts['volume']:
        Optional. array or value of type int/float

    :method: str
        methods implemented: 'cl', 'h/l', 'l/h', 'hlc', 'ohlc' default('cl')
    scaling: str
        scales implemented:
            'abs', 'atr', 'cla', 'log', 'log_compounding' default('log')
        abs:
            absolute scaling with fixed box sizes.
        atr:
            absolute scaling with atr of last n periods
        log:
            step-frozen percentage box sizing.
        log_compounding:
            compatibility logarithmic scaling with a global compounding box grid.
        cla:
            classic scaling with semi-variable box sizes.
    boxsize: int/float/string
        Size of boxes with regards to the respective scaling default (1).
        Implemented box sizes for classic scaling are 0.02, 0.05, 0.1, 0.25, 1/3, 0.5, 1, 2.
        For classic scaling the box size serves as factor to scale the original scale.
        The minimum boxsize for logarithmic scaling is 0.01%.
        For atr scaling the number of last n periods to calculate from, 'total' for all periods.
    title: str
        user defined label for the chart default(None)
        label will be created inside the class.
        The label contains the chart parameters and the title.

    Methods:
    ========
    get_breakouts(): dict
        Gets breakout points for Point and Figure Charts.
        Detailed description in get_breakouts-method.
    get_trendlines(length, mode): dict
        Gets trendlines for Point and Figure Charts.
        Detailed description in get_trendlines-method.


    Returned attributes:
    ====================

    pnf_timeseries: dict
        pnf_timeseries['date']: str or int
            Array or value of type str if datetime
        pnf_timeseries['box value']: float
            Array with prices of the last filled box
        pnf_timeseries['box index']: float
            Array with indices of the last filled box.
        pnf_timeseries['column index']: float
            Array with indices of the current column.
        pnf_timeseries['trend']: float
            Array with values for the current trend.
            Uptrends:    1
            Downtrends: -1
        pnf_timeseries['filled boxes']: float
            Array with values for number of filled boxes in the current column.

        Note:
            Due to the usage of numpy.nan all indices are of type float instead of int.

    boxscale: numpy.ndarray
        1-dim numpy array with box values in increasing order.
    matrix: numpy.ndarray
        2-dim numpy array representing the Point and Figure Chart
        with values 0, 1 and -1. Zero represents an unfilled box,
        One a box filled with an X and neg. One filled with an O.
        Columns are equivalent to the chart columns, rows to the
        corresponding index in the boxscale.
    trendlines: dict
       Detailed description in get_trendline-method.
    title: str
        Label containing chart parameter and user-defined title.
    breakouts: dict
        Detailed description in get_breakouts-method.
    """


    def __init__(self, ts: dict[str, Any], method: str = 'cl', reversal: int = 3,
                 boxsize: BoxSize = 1, scaling: str = 'log', title: str | None = None):

        # chart parameter
        self.method = self._is_valid_method(method)
        self.reversal = self._is_valid_reversal(reversal)
        self.scaling = self._is_valid_scaling(scaling)
        self.boxsize = self._is_valid_boxsize(boxsize)

        # prepare timeseries
        self.time_step: DateTimeUnit | None = None  # calculated in _prepare_ts: 'm','D', None
        self.ts = self._prepare_ts(ts)

        # chart
        self.title = self._make_title(title)
        if self._uses_step_frozen_log_scaling():
            (
                self.boxscale,
                self.pnf_timeseries,
                self.matrix,
                self.action_index_matrix,
            ) = self._get_step_frozen_log_chart()
        else:
            self.boxscale = self._get_boxscale()
            self.pnf_timeseries = self._get_pnf_timeseries()
            self.action_index_matrix: Any = None  # assigned in _pnf_timeseries2matrix()
            self.matrix = self._pnf_timeseries2matrix()
        self.column_labels = self._get_column_entry_dates()

        # trendlines
        self.trendlines: Any = None
        self.show_trendlines: ShowTrendlines = False

        # signals
        self.breakouts: Any = None
        self.buys = {}
        self.sells = {}
        self.highs_lows_heights_trends: Any = None
        self.signals: Any = None
        self.ts_signals_map: Any = None
        self.show_breakouts: bool = False
        self.bullish_breakout_color = 'g'
        self.bearish_breakout_color = 'm'

        # indicator
        self.column_midpoints: Any = None
        self.indicator = {}
        self.vap = {}
        self.indicator_colors = plt.get_cmap('Set2')
        self.indicator_fillcolor_opacity = 0.2

        # plotting coordinates/adjusted indicator
        self.plot_boxscale: Any = None
        self.plot_matrix: Any = None
        self.plot_column_index: Any = None
        self.plot_column_label: Any = None
        self.plot_y_ticks: Any = None
        self.plot_y_ticklabels: Any = None
        self.matrix_top_cut_index: Any = None
        self.matrix_bottom_cut_index: Any = None
        self.plot_indicator = {}
        self.cut2indicator = False
        self.cut2indicator_length: Any = None

        # plotting options
        self.size = 'auto'
        self.max_figure_width = 10
        self.max_figure_height = 8
        self.left_axis = False
        self.right_axis = True
        self.column_axis = True

        self.add_empty_columns = 0
        self.print_columns = 30

        self.show_markers = True
        self.grid: Any = None
        self.x_marker_color = 'grey'
        self.o_marker_color = 'grey'
        self.grid_color = 'grey'

        self.figure_width: Any = None
        self.figure_height: Any = None
        self.matrix_min_width: Any = None

        self.margin_left: Any = None
        self.margin_right: Any = None
        self.margin_top = 0.3
        self.margin_bottom: Any = None
        self.box_height: Any = None

        self.marker_linewidth: Any = None
        self.grid_linewidth: Any = None

        self.x_label_step: Any = None
        self.y_label_step: Any = None

        self.label_fontsize = 8
        self.title_fontsize = 8
        self.legend_fontsize = 8

        self.legend = True
        self.legend_position: Any = None
        self.legend_entries: Any = None

        self.plotsize_options = {'size': ['huge', 'large', 'medium', 'small', 'tiny'],
                                 'grid': [True, True, True, False, False],
                                 'matrix_min_width': [12, 12, 27, 57, 117],
                                 'box_height': [0.2, 0.15, 0.1, 0.05, 0.025],
                                 'marker_linewidth': [1, 1, 1, 0.5, 0.5],
                                 'grid_linewidth': [0.5, 0.5, 0.5, 0.25, 0.125],
                                 'x_label_step': [1, 1, 2, 4, 8],
                                 'y_label_step': [1, 1, 2, 4, 8],
                                 }

        # Figure and axis objects
        self.fig: Any = None
        self.ax1: Any = None
        self.ax2: Any = None
        self.ax3: Any = None

