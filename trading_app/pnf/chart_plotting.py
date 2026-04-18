# -*- coding: utf-8 -*-
"""Plotting helpers for PointFigureChart.

This module prepares matplotlib views from completed chart, signal, count, and
indicator data. Plotting is read-only and must not change PnF calculations.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING
from warnings import warn

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle

from .chart_shared import BEARISH, BULLISH, BoxSize, DateTimeUnit, SIGNAL_TYPES, tabulate


class ChartPlottingMixin:
    add_empty_columns: int
    ax1: Any
    ax2: Any
    ax3: Any
    bearish_breakout_color: str
    box_height: Any
    boxscale: np.ndarray
    boxsize: BoxSize
    breakouts: Any
    bullish_breakout_color: str
    column_axis: bool
    column_labels: Any
    cut2indicator: bool
    cut2indicator_length: Any
    fig: Any
    figure_height: Any
    figure_width: Any
    grid: Any
    grid_color: str
    grid_linewidth: Any
    indicator: dict[str, Any]
    indicator_colors: Any
    indicator_fillcolor_opacity: float
    label_fontsize: int
    left_axis: bool
    legend_entries: Any
    legend_fontsize: int
    legend_position: Any
    margin_bottom: Any
    margin_left: Any
    margin_right: Any
    margin_top: Any
    marker_linewidth: Any
    matrix: np.ndarray
    matrix_bottom_cut_index: Any
    matrix_min_width: Any
    matrix_top_cut_index: Any
    max_figure_height: int
    max_figure_width: int
    o_marker_color: str
    plot_boxscale: Any
    plot_column_index: Any
    plot_column_label: Any
    plot_indicator: dict[str, Any]
    plot_matrix: Any
    plot_y_ticklabels: Any
    plot_y_ticks: Any
    plotsize_options: dict[str, Any]
    right_axis: bool
    scaling: str
    show_breakouts: bool
    show_markers: bool
    show_trendlines: Any
    size: str
    time_step: DateTimeUnit | None
    title: str
    title_fontsize: int
    trendlines: Any
    vap: dict[Any, Any]
    x_label_step: Any
    x_marker_color: str
    y_label_step: Any

    if TYPE_CHECKING:
        def get_breakouts(self) -> Any: ...

    def _coordinates2plot_grid(self, array):
        """
        Converts price coordinates to the plot grid.
        """

        coords_on_grid = np.full(len(array), np.nan)
        boxscale = self.boxscale
        scaling = self.scaling

        if scaling == 'log':
            base = 1 + float(self.boxsize) / 100

        for num, val in enumerate(array):

            if not np.isnan(val):
                if any(np.argwhere(boxscale <= val)):
                    index = np.argwhere(boxscale <= val)[-1]
                else:
                    index = 0

                point_1 = boxscale[index]
                point_2 = boxscale[index + 1]
                point_3 = val

                if scaling == 'log':
                    dist = np.log(point_3 / point_1) / np.log(base)
                else:
                    dist = (point_3 - point_1) / (point_2 - point_1)

                coords_on_grid[num] = np.round(index + dist, 3)[0]

        return coords_on_grid

    def _change_color_opacity(self, index):
        """
        Change the opacity of a color from a Matplotlib color scale defined in self.indicator_colors.
        """

        color = list(self.indicator_colors(index))
        color[3] = self.indicator_fillcolor_opacity
        color = tuple(color)

        return color

    def _indicator_plotting_preparations(self):
        """
        Converts the indicator coordinates to the plotting grid and cuts off nan from
        the indicator arrays and adjust the matrix length if cut2indicator is True.
        """

        plot_indicator = self.indicator.copy()

        # find latest starting indicator
        indicator_cut_length = 0
        if self.cut2indicator is True:

            non_nan_pos = []
            for key in plot_indicator:
                array = plot_indicator[key]
                index = np.argwhere(~np.isnan(array))[0]
                non_nan_pos.append(index)

            indicator_cut_length = np.max(non_nan_pos)

        # convert indicator coordinates to the plotting grid
        for key in plot_indicator:

            plot_indicator[key] = plot_indicator[key][indicator_cut_length:]

            if 'pSAR' not in key:
                plot_indicator[key] = self._coordinates2plot_grid(plot_indicator[key])

            if 'pSAR' in key:
                sign = np.sign(plot_indicator[key])
                plot_indicator[key] = self._coordinates2plot_grid(np.abs(plot_indicator[key])) * sign

        self.plot_indicator = plot_indicator
        self.cut2indicator_length = indicator_cut_length

    def _set_margins(self):
        """
        Sets the margins for th eplot figure based on the length of the x- and y-ticks
        """

        # separate method for margin determination
        if self.margin_bottom is None:
            if self.column_axis is True:
                if self.time_step == 'D':
                    self.margin_bottom = 0.85
                elif self.time_step == 'm':
                    self.margin_bottom = 1.42
                elif self.time_step is None:
                    self.margin_bottom = 0.1
            else:
                self.margin_bottom = 0.1

        # calculate side margins based on number of max y-label characters

        # if margins_left or margin_right is True

        if self.left_axis is True or self.right_axis is True:
            y_ticks = np.arange(0, np.shape(self.plot_matrix)[0], 1)
            y_ticklabels = self.plot_boxscale[y_ticks].astype('str')
            max_y_tick_length = np.max(list(map(len, y_ticklabels)))

        if self.margin_left is None:
            if self.left_axis is True:
                self.margin_left = (max_y_tick_length + 0.5) / 10
            else:
                self.margin_left = 0.1

        if self.margin_right is None:
            if self.right_axis is True:
                self.margin_right = (max_y_tick_length + 0.5) / 10
            else:
                self.margin_right = 0.1

    def _evaluate_figure_size_and_set_plot_options(self):
        """
        Calculates the figure size and sets the parameters for the plot based on the size of the matrix
        """

        # figure height based on matrix dim-0 length and margins
        figure_height_array = (np.array(self.plotsize_options['box_height']) * np.shape(self.plot_matrix)[0]
                               + self.margin_bottom + self.margin_top)

        # figure size based on matrix dim-1 length and margins
        figure_width_array = (np.array(self.plotsize_options['box_height']) * (np.shape(self.plot_matrix)[1]
                                                                               + self.add_empty_columns) + self.margin_left + self.margin_right)

        # figure size based on matrix_min_width
        figure_width_matrix_min_width_array = (np.multiply(np.array(self.plotsize_options['box_height']),
                                                           np.array(self.plotsize_options['matrix_min_width'])
                                                           + self.add_empty_columns)
                                               + self.margin_left + self.margin_right)

        index = np.array(self.plotsize_options['matrix_min_width']) > np.shape(self.plot_matrix)[1]

        figure_width_array[index] = figure_width_matrix_min_width_array[index]

        n = 0
        if self.size == 'auto':

            while figure_width_array[n] >= self.max_figure_width or figure_height_array[n] >= self.max_figure_height:
                n = n + 1
                if n == len(figure_width_array):
                    n = n - 1
                    break

        elif self.size == 'huge':
            n = 0

        elif self.size == 'large':
            n = 1

        elif self.size == 'medium':
            n = 2

        elif self.size == 'small':
            n = 3

        elif self.size == 'tiny':
            n = 4

        if self.size != 'auto':
            self.size = self.plotsize_options['size'][n]

        self.figure_height = figure_height_array[n]
        self.figure_width = figure_width_array[n]

        if self.box_height is None:
            self.box_height = self.plotsize_options['box_height'][n]

        if self.marker_linewidth is None:
            self.marker_linewidth = self.plotsize_options['marker_linewidth'][n]

        if self.grid_linewidth is None:
            self.grid_linewidth = self.plotsize_options['grid_linewidth'][n]

        if self.x_label_step is None:
            self.x_label_step = self.plotsize_options['x_label_step'][n]

        if self.y_label_step is None:
            self.y_label_step = self.plotsize_options['y_label_step'][n]

        self.matrix_min_width = self.plotsize_options['matrix_min_width'][n]

        if self.grid is None:
            self.grid = self.plotsize_options['grid'][n]

    def _evaluate_optimal_legend_position(self):

        legend_matrix = np.hstack((self.plot_matrix,
                                   np.zeros([np.shape(self.plot_matrix)[0], self.add_empty_columns])))

        h1 = np.floor(np.shape(legend_matrix)[0] / 2).astype('int')
        w1 = np.floor(np.shape(legend_matrix)[1] / 2).astype('int')

        mod_h = np.mod(np.shape(legend_matrix)[0] / 2, 1)
        mod_w = np.mod(np.shape(legend_matrix)[1] / 2, 1)

        if mod_h == 0 and mod_w == 0:
            h2 = h1 + 1
            w2 = w1 + 1

        elif mod_h != 0 and mod_w != 0:
            h2 = h1
            w2 = w1

        elif mod_h == 0 and mod_w != 0:
            h2 = h1 + 1
            w2 = w1

        elif mod_h != 0 and mod_w == 0:
            h2 = h1
            w2 = w1 + 1

        bot_left = np.abs(legend_matrix)[0:h1, 0:w1]
        bot_right = np.abs(legend_matrix)[0:h1, w2:]
        top_left = np.abs(legend_matrix)[h2:, 0:w1]
        top_right = np.abs(legend_matrix)[h1:, w2:]

        matrix_quadrant_sums = [np.sum(top_left), np.sum(top_right), np.sum(bot_left), np.sum(bot_right)]

        quadrant = np.argmin(matrix_quadrant_sums)  # returns the first occurrence of a min value

        legend_positions = ['upper left', 'upper right', 'lower left', 'lower right']

        self.legend_position = legend_positions[quadrant]

    def _prepare_variables_for_plotting(self):
        """
        Prepares matrix and indicator for plotting. Stores the cut_off_indices in attributes.
        The cut_off indices are needed to plot signals and trendlines
        """

        self._indicator_plotting_preparations()

        if self.cut2indicator is True:
            self.plot_matrix = self.matrix[:, self.cut2indicator_length:]
        else:
            self.plot_matrix = self.matrix

        if np.nonzero(np.sum(np.abs(self.plot_matrix), 1))[0][0] - 3 <= 0:
            self.matrix_bottom_cut_index = 0
        else:
            self.matrix_bottom_cut_index = np.nonzero(np.sum(np.abs(self.matrix), 1))[0][0] - 3

        self.matrix_top_cut_index = np.nonzero(np.sum(np.abs(self.matrix), 1))[0][-1] + 4

        self.plot_matrix = self.plot_matrix[self.matrix_bottom_cut_index: self.matrix_top_cut_index, :]
        self.plot_boxscale = self.boxscale[self.matrix_bottom_cut_index: self.matrix_top_cut_index]

        self._set_margins()
        self._evaluate_figure_size_and_set_plot_options()

        if np.shape(self.plot_matrix)[1] < self.matrix_min_width:
            extension_length = self.matrix_min_width - np.shape(self.plot_matrix)[1]
        else:
            extension_length = 0

        # extend the matrix with zeros if dim-1 is too short
        self.plot_matrix = np.hstack((self.plot_matrix, np.zeros([np.shape(self.plot_matrix)[0], extension_length])))

        # extend indicator with np.nan by extension_length
        extension = np.full([1, extension_length], np.nan)[0]

        for key in self.plot_indicator:

            if 'pSAR' not in key:
                self.plot_indicator[key] = np.hstack(
                    (self.plot_indicator[key], extension)) - self.matrix_bottom_cut_index

            if 'pSAR' in key:
                sign = np.sign(self.plot_indicator[key])
                sign = np.hstack((sign, extension))
                self.plot_indicator[key] = (np.abs(
                    np.hstack((self.plot_indicator[key], extension))) - self.matrix_bottom_cut_index) * sign

        # calculate ticks and ticklabels

        # prepare y-ticks
        self.plot_y_ticks = np.arange(0, np.shape(self.plot_matrix)[0], self.y_label_step)
        self.plot_y_ticklabels = self.plot_boxscale[self.plot_y_ticks]

        # prepare x-ticks
        if self.column_labels is not None:
            self.plot_column_label = self.column_labels[::-self.x_label_step]

            x_ticks = np.arange(np.size(self.column_labels))
            self.plot_column_index = x_ticks[::-self.x_label_step] + 0.5

        if self.legend_position is None:
            self._evaluate_optimal_legend_position()

    def _create_figure_and_axis(self):
        """
        Creates the figure and axis objects.
        """

        # plt.ioff()  # necessary to supress output in jupyter notebooks

        # calculate axis positioning
        left = self.margin_left / self.figure_width
        right = self.margin_right / self.figure_width
        bottom = self.margin_bottom / self.figure_height
        top = self.margin_top / self.figure_height
        width = 1 - left - right
        height = 1 - bottom - top

        # initiate figure
        self.fig = plt.figure(self.title, figsize=(self.figure_width, self.figure_height))

        # first axis creates the frame for the chart.
        self.ax1 = self.fig.add_axes((0, 0, 1, 1))
        self.ax1.axis('off')
        self.ax1.set_yticks([])
        self.ax1.set_xticks([])
        self.ax1.get_tightbbox()

        # second axis is where the plotting takes place
        self.ax2 = self.fig.add_axes((left, bottom, width, height))

        if self.left_axis is True:
            self.ax2.set_yticks(self.plot_y_ticks)
            self.ax2.set_yticklabels(self.plot_y_ticklabels, fontsize=self.label_fontsize)
        else:
            self.ax2.set_yticks([])
            self.ax2.set_yticklabels([])

        self.ax2.set_ylim(bottom=-0.5, top=np.shape(self.plot_matrix)[0] - 0.5)

        # third axis is to allow y-ticks with labels on the ight of the chart
        self.ax3 = self.ax2.twinx()
        self.ax3.set_xticks([])

        if self.right_axis is True:
            self.ax3.set_yticks(self.plot_y_ticks)
            self.ax3.set_yticklabels(self.plot_y_ticklabels, fontsize=self.label_fontsize)
        else:
            self.ax3.set_yticks([])
            self.ax3.set_yticklabels([])

        self.ax3.set_ylim(bottom=-0.5, top=np.shape(self.plot_matrix)[0] - 0.5)

        if self.column_axis is True and self.plot_column_label is not None:
            self.ax2.set_xticks(self.plot_column_index)
            self.ax2.set_xticklabels(self.plot_column_label, rotation=90, ha='center', fontsize=self.label_fontsize)
        else:
            self.ax2.set_xticks([])
            self.ax2.set_xticklabels([])

        self.ax2.set_xlim(left=0, right=np.shape(self.plot_matrix)[1] + self.add_empty_columns)

    def _plot_grid(self):
        """
        Plots a grid to the PointFigureChart figure
        """

        for n in np.arange(np.shape(self.plot_matrix)[0]):
            x1 = 0
            x2 = np.shape(self.plot_matrix)[1] + self.add_empty_columns
            self.ax2.plot((x1, x2), (n + 0.5, n + 0.5), color=self.grid_color, lw=self.grid_linewidth)

        for n in np.arange(np.shape(self.plot_matrix)[1] + self.add_empty_columns):
            y1 = 0 - 0.5
            y2 = np.shape(self.plot_matrix)[0] - 0.5
            self.ax2.plot((n, n), (y1, y2), color=self.grid_color, lw=self.grid_linewidth)

    def _plot_markers(self):
        """
        Plots Point and Figure symbols (X and O) to the PointFigureChart figure
        """

        x_box, x_col = np.where(self.plot_matrix > 0)
        o_box, o_col = np.where(self.plot_matrix < 0)

        x_col = x_col + 0.5
        o_col = o_col + 0.5

        space = 0.4  # spacer between symbols

        if self.show_markers is True:
            for n in range(0, np.size(x_col)):
                self.ax2.plot((x_col[n] - space, x_col[n] + space), (x_box[n] - space, x_box[n] + space),
                              color=self.x_marker_color,
                              lw=self.marker_linewidth)
                self.ax2.plot((x_col[n] + space, x_col[n] - space), (x_box[n] - space, x_box[n] + space),
                              color=self.x_marker_color,
                              lw=self.marker_linewidth)

            for n in range(0, np.size(o_col)):
                circle = Circle((o_col[n], o_box[n]), space, color=self.o_marker_color, lw=self.marker_linewidth,
                                fill=False)
                self.ax2.add_artist(circle)

    def _plot_trendlines(self):
        """
        plots 45 degree trendlines to the PointFigureChart figure
        """
        if self.show_trendlines == 'external':
            trendline_modus = 'external'
        elif self.show_trendlines == 'internal':
            trendline_modus = 'internal'
        else:
            trendline_modus = 'external'

        trendlines = self.trendlines

        for n in range(0, np.size(trendlines['column index'])):

            if trendlines['bounded'][n] == trendline_modus:

                if trendlines['type'][n] == 'bullish support':
                    c = trendlines['column index'][n]
                    r = trendlines['box index'][n] - self.matrix_bottom_cut_index
                    r_floor = r + 0.5
                    r_ceill = r - 0.5
                    self.ax2.plot((c, c + 1), (r_ceill, r_floor), color='b', lw=self.marker_linewidth)
                    k = 1

                    while k < trendlines['length'][n]:
                        c = c + 1
                        r_floor = r_ceill
                        r_ceill = r_ceill + 1
                        k = k + 1
                        self.ax2.plot((c, c + 1), (r_floor + 1, r_ceill + 1), color='b', lw=self.marker_linewidth)

                elif trendlines['type'][n] == 'bearish resistance':

                    c = trendlines['column index'][n]
                    r = trendlines['box index'][n] - self.matrix_bottom_cut_index
                    r_floor = r + 0.5
                    r_ceill = r - 0.5

                    self.ax2.plot((c, c + 1), (r_floor, r_ceill,), color='r', lw=self.marker_linewidth)
                    k = 1

                    while k < trendlines['length'][n]:
                        c = c + 1
                        r_ceill = r_floor
                        r_floor = r_floor - 1
                        k = k + 1

                        self.ax2.plot((c, c + 1), (r_ceill - 1, r_floor - 1), color='r', lw=self.marker_linewidth)

    def _plot_breakouts(self):
        """
        Plots breakout lines to the PointFigureChart figure
        """

        if self.breakouts is None:
            self.breakouts = self.get_breakouts()
            bo = self.breakouts
        else:
            bo = self.breakouts

        for i, row, col, width in zip(np.arange(0, np.size(bo['column index'])),
                                      bo['box index'],
                                      bo['column index'],
                                      bo['width']):
            if bo['trend'][i] == 1:
                y = row - 0.5 - self.matrix_bottom_cut_index
                x1 = col + 1
                x2 = x1 - width
                self.ax2.plot((x1, x2), (y, y), color=self.bullish_breakout_color, lw=self.marker_linewidth)

            elif bo['trend'][i] == -1:
                y = row + 0.5 - self.matrix_bottom_cut_index
                x1 = col + 1
                x2 = x1 - width
                self.ax2.plot((x1, x2), (y, y), color=self.bearish_breakout_color, lw=self.marker_linewidth)

    def _get_indicator_keys(self):

        indicator_keys = []

        for key in self.indicator.keys():

            if 'Bollinger' in key:
                if 'upper' in key:
                    indicator_keys.append(key.split('-')[0])

            if 'Donchian' in key:
                if 'upper' in key:
                    indicator_keys.append(key.split('-')[0])

            elif 'pSAR' in key:
                indicator_keys.append(key)

            elif not 'Bollinger' in key and not 'Donchian' in key and not 'pSAR' in key:
                indicator_keys.append(key)

        return indicator_keys

    def _plot_indicator(self):
        """
        Plots applied indicator to the PointFigureChart figure
        """

        # calculate x coordinates for indicator
        x_coordinates = np.arange(np.shape(self.plot_matrix)[1]) + 0.5

        indicator_keys = self._get_indicator_keys()

        color_index = 0
        legend_entries = []

        # plot indicator
        for indicator in indicator_keys:

            if 'Bollinger' in indicator or 'Donchian' in indicator:
                bbu = self.plot_indicator[indicator + '-upper']
                bbl = self.plot_indicator[indicator + '-lower']
                self.ax2.plot(x_coordinates, bbu, '-', color=self.indicator_colors(color_index),
                              linewidth=self.marker_linewidth)
                self.ax2.plot(x_coordinates, bbl, '-', color=self.indicator_colors(color_index),
                              linewidth=self.marker_linewidth,
                              label=indicator)
                self.ax2.fill_between(x_coordinates, bbu, bbl,
                                      color=self._change_color_opacity(color_index))  # , alpha=1)

                fillcolor = self._change_color_opacity(color_index)
                legend_symbol_bollinger = Line2D([], [], color=fillcolor,
                                                 marker='s',
                                                 linestyle='None',
                                                 markeredgewidth=1,
                                                 markersize=8,
                                                 label=indicator,
                                                 fillstyle='full',
                                                 markeredgecolor=self.indicator_colors(color_index))
                legend_entries.append(legend_symbol_bollinger)
                color_index += 1

            if 'pSAR' in indicator:
                sign = np.sign(self.plot_indicator[indicator])
                psar = np.abs(self.plot_indicator[indicator])

                for val, c, tf in zip(psar, x_coordinates, sign):

                    if tf == 1:
                        self.ax2.scatter(c, val, s=self.marker_linewidth * 5, marker='o',
                                         color=self.indicator_colors(color_index))
                    elif tf == -1:
                        self.ax2.scatter(c, val, s=self.marker_linewidth * 5, marker='o',
                                         color=self.indicator_colors(color_index + 1))

                legend_symbol_psar = Line2D([], [], color=self.indicator_colors(color_index),
                                            marker='o',
                                            linestyle='None',
                                            markeredgewidth=0.1,
                                            markersize=5,
                                            label=indicator,
                                            fillstyle='left',
                                            markerfacecoloralt=self.indicator_colors(color_index + 1))
                legend_entries.append(legend_symbol_psar)
                color_index += 2

            if not 'Bollinger' in indicator and not 'Donchian' in indicator and not 'pSAR' in indicator:
                self.ax2.plot(x_coordinates, self.plot_indicator[indicator], '-',
                              color=self.indicator_colors(color_index),
                              linewidth=self.marker_linewidth)
                legend_symbol = Line2D([], [], color=self.indicator_colors(color_index),
                                       linestyle='-', label=indicator)
                legend_entries.append(legend_symbol)
                color_index += 1

            self.legend_entries = legend_entries

    def _plot_volume_at_price(self):
        """
        Placeholder for volume-at-price plotting.
        """

        raise NotImplementedError('Volume at price plotting is not implemented.')

    def _assemble_plot_chart(self):
        self._prepare_variables_for_plotting()
        self._create_figure_and_axis()

        # plot grid
        if self.grid is True:
            self._plot_grid()

        # plot points and figures
        if self.show_markers is True:
            self._plot_markers()

        # plot breakouts
        if self.show_breakouts is True:
            self._plot_breakouts()

        # plot trendlines
        # check if  trendlines are there
        if self.show_trendlines == 'external' or self.show_trendlines == 'internal':
            self._plot_trendlines()
        elif self.show_trendlines == 'both':
            self.show_trendlines = 'external'
            self._plot_trendlines()
            self.show_trendlines = 'internal'
            self._plot_trendlines()
            self.show_trendlines = 'both'

        # plot indicator
        self._plot_indicator()

        # plot volume at price
        if self.vap != {}:
            self._plot_volume_at_price()

        if self.legend_entries is not None:
            self.ax2.legend(handles=self.legend_entries, fontsize=self.legend_fontsize, loc=self.legend_position)

        plt.title(self.title, loc='left', fontsize=self.title_fontsize)

    def save(self, fname=None, dpi=None):

        if self.fig is None:
            self._assemble_plot_chart()

        if fname is None:
            fname = 'chart.png'

        if dpi is None:
            if self.size == 'tiny' or self.size == 'small':
                dpi = 1200
            else:
                dpi = 600

        self.fig.savefig(fname=fname, dpi=dpi, bbox_inches='tight', pad_inches=0)

    def show(self):

        if self.fig is None:
            self._assemble_plot_chart()

        plt.show()

