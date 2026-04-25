import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np
import talib.abstract as ta
from freqtrade.strategy import (IStrategy, informative)
from pandas import DataFrame, Series
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import math
import pandas_ta as pta
# from finta import TA as fta
import logging
from logging import FATAL

logger = logging.getLogger(__name__)

class TEST6(IStrategy):

    def version(self) -> str:
        return "v1"

    # ROI table:
    minimal_roi = {
        "0": 0.2,
        '30': 0.1,
        '90': 0.05,
        '180': 0.02,
        '360': -1
    }

    # Stoploss:
    stoploss = -0.1

    plot_config = {
        'main_plot': {
            # Configuration for main plot indicators.
            # Specifies `ema10` to be red, and `ema50` to be a shade of gray
            'ema_12': {'color': 'red'},
            'ema_24': {'color': '#CCCCCC'},
            'ema_120_1h': {},
        }
    }


    # # Trailing stop:
    # trailing_stop = True
    # trailing_stop_positive = 0.01
    # trailing_stop_positive_offset = 0.05
    # trailing_only_offset_is_reached = True

    # Sell signal
    use_exit_signal = True
    exit_profit_only = False
    exit_profit_offset = 0.01
    ignore_roi_if_entry_signal = False

    timeframe = '5m'

    @informative('1h')
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['ema_120'] = ta.EMA(dataframe, timeperiod=120)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['ema_12'] = ta.EMA(dataframe, timeperiod=12)
        dataframe['ema_24'] = ta.EMA(dataframe, timeperiod=24)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['close'] > dataframe['ema_120_1h'])
                &
                qtpylib.crossed_above(dataframe['ema_12'], dataframe['ema_24'])
                &
                (dataframe['volume'] > 0)
            ),
            ['enter_long', 'enter_tag']] = (1, 'buy_long')

        # dataframe.loc[
        #     (
        #             (dataframe['close'] < dataframe['ema_120_1h'])
        #             &
        #             qtpylib.crossed_below(dataframe['ema_12'], dataframe['ema_24'])
        #             &
        #             (dataframe['volume'] > 0)
        #     ),
        #     ['enter_short', 'enter_tag']] = (1, 'buy_short')

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                    qtpylib.crossed_below(dataframe['ema_12'], dataframe['ema_24'])
                    &
                    (dataframe['volume'] > 0)
            ),
            ['exit_long', 'exit_tag']] = (1, 'sell_long')

        # dataframe.loc[
        #     (
        #
        #             (dataframe['close'] > dataframe['ema_120_1h'])
        #             &
        #             (dataframe['volume'] > 0)
        #     ),
        #     ['exit_short', 'exit_tag']] = (1, 'sell_short')

        return dataframe