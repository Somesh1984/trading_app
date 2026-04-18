# -*- coding: utf-8 -*-
"""Count helpers for PointFigureChart.

This module reads completed chart matrix and breakout data to produce count
inspection dictionaries. It does not create chart columns, generate orders, or
change trading state.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING
from warnings import warn

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle

from .chart_shared import BEARISH, BULLISH, BoxSize, DateTimeUnit, SIGNAL_TYPES, tabulate


class ChartCountMixin:
    breakouts: Any
    boxscale: np.ndarray
    matrix: np.ndarray
    reversal: int
    scaling: str

    if TYPE_CHECKING:
        def get_breakouts(self) -> Any: ...

        def _get_boxscale(self, overscan: Any = None) -> np.ndarray: ...

    @classmethod
    def _assign_to_dict_in_loop(cls,
                                counts, n,
                                trend, sort,
                                column, row, box,
                                anchor_column, anchor_box, length,
                                target, reward,
                                risk1, risk2,
                                ratio1, ratio2,
                                percent_filled):
        
        counts['trend'][n] = trend
        counts['type'][n] = sort
        counts['column index'][n] = column
        counts['box index'][n] = row
        counts['box'][n] = box
        counts['anchor column'][n] = anchor_column
        counts['anchor box'][n] = anchor_box
        counts['length'][n] = length
        counts['target'][n] = target
        counts['reward'][n] = reward
        counts['risk 1'][n] = risk1
        counts['risk 2'][n] = risk2
        counts['ratio 1'][n] = ratio1
        counts['ratio 2'][n] = ratio2
        counts['quality'][n] = percent_filled

        return counts

    @classmethod
    def count_percent_filled(cls, M, width):
        num_filled = np.sum(np.abs(M))
        height = np.size(M, 0)
        max_filled = (width-1) * (height-1) + height
        percent_filled = np.round(num_filled / max_filled, 2)

        return percent_filled

    def counts_RevGreater1(self, counts, new_boxscale, Extension_Down, MinLength):
        BO = self.breakouts
        mtx = self.matrix
        sort = 'vertical'
        # anchor point is row below anchor column
            
        n = 0 
        for colindex, boxindex, width, trend in zip(BO['column index'], BO['box index'], BO['width'], BO['trend']):    
        
            A = mtx[:,colindex-width+1:colindex+1].copy() # part of mtx containing the signal columns only
            B = np.sum(np.abs(A),1)
        
            if trend == BULLISH:
                
                min_IDX = np.where(B != 0)[0][0]
                
                C = mtx[min_IDX:boxindex,colindex-width+1:colindex+1].copy()
        
                perc_filled = self.count_percent_filled(C, width)
                
                if C[0,0] == BULLISH: # condition for valid count columns
                    
                    length = np.sum(np.abs(mtx[:,colindex-width+1].copy()))
                    anc_IDX = min_IDX - 1
                    
                    Target_IDX = int(anc_IDX + (length * self.reversal) + Extension_Down)    

                    target = new_boxscale[Target_IDX] 
                    
                    reward = target - self.boxscale[boxindex]
                    
                    risk1 = self.boxscale[boxindex] - self.boxscale[np.where(A[:,-2] != 0)[0][0]-1]
                    risk2 = self.boxscale[boxindex] - self.boxscale[min_IDX-1]
                    
                    ratio1 = np.round(reward/risk1,2)
                    ratio2 = np.round(reward/risk2,2)
                    
                    anchor_col = colindex - width + 1
                    anchor_box = self.boxscale[anc_IDX]
                    
                    box = self.boxscale[boxindex]
                    
                    counts = self._assign_to_dict_in_loop(counts, n,
                                                    trend, sort,
                                                    colindex, boxindex, box,
                                                    anchor_col, anchor_box, length,
                                                    target, reward,
                                                    risk1, risk2,
                                                    ratio1, ratio2,
                                                    perc_filled)
                    
            elif trend == BEARISH:
                    
                max_IDX = np.where(B != 0)[0][-1]
                
                C = mtx[boxindex+1:max_IDX+1,colindex-width+1:colindex+1].copy()
                    
                perc_filled = self.count_percent_filled(C, width)
        
                if C[-1,0] == BEARISH: # condition for valid count columns
                        
                    length = np.sum(np.abs(mtx[:,colindex-width+1].copy()))
                        
                    anc_IDX = max_IDX + 1
    
                    TargetIdx = int(anc_IDX - (length * self.reversal) + Extension_Down) 
                    
                    if TargetIdx < 0:
                        TargetIdx = 0
                        
                    target = new_boxscale[TargetIdx]
                        
                    reward = self.boxscale[boxindex] - target
                        
                    risk1 = self.boxscale[np.where(A[:,-2] != 0)[0][-1] + 1] - self.boxscale[boxindex]
                    risk2 = self.boxscale[max_IDX+1] - self.boxscale[boxindex]
            
                    ratio1 = np.round(reward/risk1,2)
                    ratio2 = np.round(reward/risk2,2)            
                        
                    anchor_col = colindex - width + 1
                    anchor_box = self.boxscale[anc_IDX]                            
                    
                    box = self.boxscale[boxindex]
                    
                    counts = self._assign_to_dict_in_loop(counts, n, 
                                                    trend, sort,
                                                    colindex, boxindex, box, 
                                                    anchor_col, anchor_box, length, 
                                                    target, reward, 
                                                    risk1, risk2, 
                                                    ratio1, ratio2, 
                                                    perc_filled)
        
            n = n + 1

            
        sort = 'horizontal R>1'
        # count row is lowest box in the pattern (breakout)
        # target is "lowest box in pattern" + (Reversal x Width) 
        # reward is target row minus count row
        # risk 1 is row below the column before the breakout-column
        # risk 2 is row below the low of the pattern

        for colindex, boxindex, width, trend, pattern in zip(BO['column index'], BO['box index'], BO['width'], BO['trend'], BO['type']):

            if trend == BULLISH and pattern == 'reversal' and width >= MinLength:
                                
                A = mtx[:,colindex-width+1:colindex+1].copy()
                B = np.sum(np.abs(A),1)
                min_IDX = np.where(B != 0)[0][0] # lowest row in the pattern
                
                C = mtx[min_IDX:boxindex,colindex-width+1:colindex+1].copy()
                
                perc_filled = self.count_percent_filled(C, width)
                        
                TargetIdx = min_IDX + (width * self.reversal) + Extension_Down          

                target = new_boxscale[TargetIdx]        
                reward = target - self.boxscale[boxindex]
                
                risk1  = self.boxscale[boxindex] - self.boxscale[ np.where( A[:,-2] != 0)[0][0] -1]
                ratio1 = np.round(reward/risk1,2)
                
                risk2  = self.boxscale[boxindex] - self.boxscale[min_IDX - 1]
                ratio2 = np.round(reward/risk2,2)
                
                anchor_col = colindex - np.size(C,1) + np.where(C[0,:] != 0)[0][-1] + 1     
                anchor_box = self.boxscale[min_IDX]
                    
                box = self.boxscale[boxindex]
                
                counts = self._assign_to_dict_in_loop(counts, n, 
                                                trend, sort,
                                                colindex, boxindex, box, 
                                                anchor_col, anchor_box, width, 
                                                target, reward, 
                                                risk1, risk2, 
                                                ratio1, ratio2, 
                                                perc_filled)
                
                if trend == BEARISH and pattern == 'reversal' and width >= MinLength:    
                    
                    A = mtx[:,colindex-width+1:colindex+1].copy()
                    B = np.sum(np.abs(A),1)
                    max_IDX = np.where(B != 0)[0][-1] # highest row in the pattern
                    
                    C = mtx[ boxindex+1:max_IDX+1, colindex-width+1:colindex+1 ].copy()
            
                    perc_filled = self.count_percent_filled(C, width)
                            
                    TargetIdx = max_IDX - (width * self.reversal) + Extension_Down    
                    
                    if TargetIdx < 0:
                        TargetIdx = 0
            
                    target = new_boxscale[TargetIdx]        
                    reward = self.boxscale[boxindex] - target
                    
                    risk1  = self.boxscale[ np.where( A[:,-2] != 0)[0][-1] + 1] - self.boxscale[boxindex] 
                    ratio1 = np.round(reward/risk1,2)
                    
                    risk2  = self.boxscale[max_IDX + 1] - self.boxscale[boxindex]
                    ratio2 = np.round(reward/risk2,2)
            
                    anchor_col = colindex - np.size(C,1) + np.where(C[-1,:] != 0)[0][-1] - 1   
                    anchor_box = self.boxscale[max_IDX]        
            
                    box = self.boxscale[boxindex]
                    
                    counts = self._assign_to_dict_in_loop(counts, n, 
                                                    trend, sort,
                                                    colindex, boxindex, box, 
                                                    anchor_col, anchor_box, width, 
                                                    target, reward, 
                                                    risk1, risk2, 
                                                    ratio1, ratio2, 
                                                    perc_filled)
                n = n + 1

        return counts

    def counts_Rev1(self, counts, new_boxscale, Extension_Down, MinLength):
        BO = self.breakouts
        mtx = self.matrix
        sort = 'horizontal (base) R=1'
        # count row is row with most filled boxes
        # if more than one currently the highest for bullish and lowest for bearish
        # target is count row + width
        # risk 1 is one row below count row
        # risk 2 is row below low of pattern
        # count_percent_filled is different here: perc filled of anchor row
        
        n=0
        for colindex, boxindex, width, trend, pattern in zip(BO['column index'], BO['box index'], BO['outer width'], BO['trend'], BO['type']):
        
            A = mtx[:,colindex-width+1:colindex+1].copy()
            B = np.sum(np.abs(A),1)
            
            if trend == BULLISH and pattern == 'reversal' and width >= MinLength:    
                
                min_IDX = np.where(B != 0)[0][0]
                
                anc_IDX = np.where(B == np.max(B))[0][0] # take the lowest 
                        
                C = mtx[min_IDX:boxindex,colindex-width+1:colindex+1].copy()
                
                
                boxes_filled = B[anc_IDX]
                perc_filled = np.round(boxes_filled/width,2)               
                
                TargetIdx = anc_IDX + width + Extension_Down
        
                target = new_boxscale[TargetIdx]        
                reward = target - self.boxscale[boxindex]
                
                # zeros will be deleted later
                if target < self.boxscale[boxindex]:
                    reward = 0
                
                risk1  = self.boxscale[boxindex] - self.boxscale[anc_IDX-1]
                ratio1 = np.round(reward/risk1,2)
                
                risk2  = self.boxscale[boxindex] - self.boxscale[min_IDX-1]
                ratio2 = np.round(reward/risk2,2)
                
                anchor_col = colindex
                anchor_box = self.boxscale[anc_IDX]                                            
                
                box = self.boxscale[boxindex]
                
                counts = self._assign_to_dict_in_loop(counts, n,
                                                trend, sort,
                                                colindex, boxindex, box,
                                                anchor_col, anchor_box, width,
                                                target, reward,
                                                risk1, risk2,
                                                ratio1, ratio2,
                                                perc_filled)
                
            if trend == BEARISH and pattern == 'reversal' and width >= MinLength: 
                
                max_IDX = np.where(B != 0)[0][-1]
        
                anc_IDX = np.where(B == np.max(B))[0][-1] # take the highest row
                
                C = mtx[boxindex+1:max_IDX+1,colindex-width+1:colindex+1].copy()
        
                boxes_filled = B[anc_IDX]
                perc_filled = np.round(boxes_filled/width,2) 
        
                Target_IDX = anc_IDX - width + Extension_Down
                
                if Target_IDX < 0:
                    Target_IDX = 0
                
                
                print('TargetIDX2',Target_IDX) 
                
                target = new_boxscale[Target_IDX]        
                reward = self.boxscale[boxindex] - target
                
                # zeros will be deleted later
                if target > self.boxscale[boxindex]:
                    reward = 0
                
                risk1  = self.boxscale[anc_IDX+1] - self.boxscale[boxindex] 
                ratio1 = np.round(reward/risk1,2)
                
                risk2  = self.boxscale[max_IDX - 1] - self.boxscale[boxindex]
                ratio2 = np.round(reward/risk2,2)
                
                anchor_col = colindex
                anchor_box = self.boxscale[anc_IDX]                                            
                
                box = self.boxscale[boxindex]
                
                counts = self._assign_to_dict_in_loop(counts, n,
                                                trend, sort,
                                                colindex, boxindex, box,
                                                anchor_col, anchor_box, width,
                                                target, reward,
                                                risk1, risk2,
                                                ratio1, ratio2,
                                                perc_filled)
        
            n = n + 1

        sort = 'horizontal (signal) R=1'
        # Count row is the base of the column where the signal occurs.
        # target is count row + width
        # risk1 row under base of signal column
        # risk2 row under lowest low

        for colindex, boxindex, width, trend, pattern in zip(BO['column index'], BO['box index'], BO['outer width'], BO['trend'], BO['type']):

            if trend == BULLISH and pattern == 'reversal' and width >= MinLength:    
                
                A = mtx[:,colindex-width+1:colindex+1].copy()
                B = np.sum(np.abs(A),1)
                min_IDX = np.where(B != 0)[0][0] # minimum in pattern
                
                C = mtx[min_IDX:boxindex,colindex-width+1:colindex+1].copy()

                perc_filled = self.count_percent_filled(C, width)
                
                # Anchor row is the base row of the breakout column.
                # count row is the base row of the exit column
                anc_IDX = np.where (A[:,-1] != 0)[0][0]                  
                
                Target_IDX = anc_IDX + width + Extension_Down
                    
                target = new_boxscale[Target_IDX]        
                reward = target - self.boxscale[boxindex]
                
                risk1  = self.boxscale[boxindex] - self.boxscale[np.where (A[:,-1] != 0)[0][0]-1] # row under count row
                ratio1 = np.round(reward/risk1,2)
                
                risk2  = self.boxscale[boxindex] - self.boxscale[min_IDX - 1] # row under minimum in pattern
                ratio2 = np.round(reward/risk2,2)

                anchor_col = colindex
                anchor_box = self.boxscale[np.where (A[:,-1] != 0)[0][0]] # base of breakout column

                box = self.boxscale[boxindex]
                
                counts = self._assign_to_dict_in_loop(counts, n,
                                                trend, sort,
                                                colindex, boxindex, box,
                                                anchor_col, anchor_box, width,
                                                target, reward,
                                                risk1, risk2,
                                                ratio1, ratio2,
                                                perc_filled)      
                
                
            if trend == BEARISH and pattern == 'reversal' and width >= MinLength:    
                
                A = mtx[:,colindex-width+1:colindex+1].copy()
                B = np.sum(np.abs(A),1)
                max_IDX = np.where(B != 0)[0][-1]
                
                C = mtx[boxindex+1:max_IDX+1,colindex-width+1:colindex+1].copy()

                perc_filled = self.count_percent_filled(C, width)
                
                # Anchor row is the base row of the breakdown column.
                anc_IDX = np.where( A[:,-1] !=0 )[0][-1].astype(int) #+ Extension_Down
                
                Target_IDX = anc_IDX - width + Extension_Down
                
                if Target_IDX < 0:
                    Target_IDX = 0

                target = new_boxscale[Target_IDX]        
                reward = self.boxscale[boxindex] - target
                
                risk1  = self.boxscale[np.where( A[:,-1] != 0)[0][-1]+1] - self.boxscale[boxindex]
                ratio1 = np.round(reward/risk1,2)
                
                risk2  = self.boxscale[max_IDX+1] - self.boxscale[boxindex]
                ratio2 = np.round(reward/risk2,2)

                anchor_col = colindex
                anchor_box = self.boxscale[anc_IDX]   

                box = self.boxscale[boxindex]
                
                counts = self._assign_to_dict_in_loop(counts, n,
                                                trend, sort,
                                                colindex, boxindex, box,
                                                anchor_col, anchor_box, width,
                                                target, reward,
                                                risk1, risk2,
                                                ratio1, ratio2,
                                                perc_filled) 
                    
            n = n + 1  

        return counts

    def get_counts(self, MinLength=5):

        if MinLength == None or MinLength < 5:
            MinLength = 5
            
        if not self.breakouts:
            self.get_breakouts()

        BO = self.breakouts

        keys = ['column index', 'box index', 'box', 'trend', 'type', 'length', 'anchor column', 'anchor box', 'target', 'reward', 'risk 1', 'risk 2', 'ratio 1', 'ratio 2', 'quality']
        
        counts = {}
        
        for key in keys:
            
            counts[key] = np.zeros(2 * np.size(BO['column index'])) # double the length
             
            if key == 'column' or key == 'row' or key == 'length' or key =='anchor column' or key == 'anchor box':
                
                counts[key] = counts[key].astype(int)   
                    
            elif key == 'trend' or key =='type':
                
                counts[key][:] = np.nan
                counts[key] = counts[key].astype(str)
                
            elif key == 'target' or key == 'reward' or key == 'risk 1' or key == 'risk 2' or key == 'ratio 1' or key == 'ratio 2' or key == 'quality':
                
                counts[key][:] = np.nan    
                
        #%% find length for maximal extension of box scale and extend it
        
        # minimum extension length for horizontal counts:
        MaxWidthUp  = MinLength                                                       
        MaxWidthDown = MinLength                                                      
        
        for width, trend, pattern in zip(BO['outer width'], BO['trend'], BO['type']):
            if trend == BULLISH and pattern == 'reversal':
                MaxWidthUp = width if width > MaxWidthUp else MaxWidthUp
        
            elif trend == BEARISH and pattern == 'reversal':
                MaxWidthDown = width if width > MaxWidthDown else MaxWidthDown
                
        Extension_Up   = MaxWidthUp   * self.reversal      
        Extension_Down = MaxWidthDown * self.reversal         
        
        # minimum extension length for vertical counts
        max_col_height = np.max(np.sum(np.abs(self.matrix), 0))
        Extension      = 2 * self.reversal * max_col_height
        
        Extension_Up   = Extension_Up   if   Extension_Up > Extension else Extension
        Extension_Down = Extension_Down if Extension_Down > Extension else Extension

        new_boxscale = self._get_boxscale([Extension_Up, Extension_Down])


        original_scale_start = np.where(new_boxscale == self.boxscale[0])[0]
        if np.size(original_scale_start) > 0:
            Extension_Down = int(original_scale_start[0])
        
        # call functions to find counts
        if self.reversal > 1:
            counts = self.counts_RevGreater1(counts, new_boxscale, Extension_Down, MinLength)
        
        elif self.reversal == 1:
            counts = self.counts_Rev1(counts, new_boxscale, Extension_Down, MinLength)

            
        # delete NaNs
        x = np.argwhere(np.isnan(counts['reward']))
            
        temp_counts = {}
        for key in keys:
            temp_counts[key] = np.delete(counts[key],x) 
                
        counts = temp_counts        
    
        # delete multiple entries
        
        a =       np.where(counts['length'][:-1]  == counts['length'][1:])[0]
        b = np.where(counts['column index'][:-1]  == counts['column index'][1:])[0]  
        c =    np.where(counts['box index'][:-1]  ==    counts['box index'][1:])[0] 
        
        z = np.intersect1d(np.intersect1d(a,b),c)
        
        temp_counts = {}
        for key in keys:
            temp_counts[key] = np.delete(counts[key],z)     
        counts = temp_counts 
        
        return counts  

