from functools import reduce
import datetime
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np
import talib.abstract as ta
from freqtrade.strategy import (IStrategy, informative, DecimalParameter)
from pandas import DataFrame, Series
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import math
from freqtrade.persistence import Trade
import pandas_ta as pta
# from finta import TA as fta
from datetime import datetime,timedelta
import logging
from logging import FATAL

logger = logging.getLogger(__name__)

class TEST7(IStrategy):

    def version(self) -> str:
        return "v1"

    # ROI table:
    minimal_roi = {
        "0": 0.2,
        '30': 0.1,
        '60': 0.03,
        '90': 0.015,
        '180': 0,
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
            'ema_26': {'color': 'yellow'},
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

    process_only_new_candles = True
    startup_candle_count = 100
    timeframe = '5m'

    @informative('1h')
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['ema_120'] = ta.EMA(dataframe, timeperiod=120)
        return dataframe

    buy_umacd_max = DecimalParameter(-0.05, 0.05, decimals=5, default=-0.01176, space="buy")
    buy_umacd_min = DecimalParameter(-0.05, 0.05, decimals=5, default=-0.01416, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['ema_12'] = ta.EMA(dataframe, timeperiod=12)
        dataframe['ema_24'] = ta.EMA(dataframe, timeperiod=24)
        dataframe['ema_26'] = ta.EMA(dataframe, timeperiod=26)
        dataframe['umacd'] = (dataframe['ema_12'] / dataframe['ema_26']) - 1
    #umacd代表的是多头行情  umacd》0时  绝对值越大，短期均价越偏离长期均价

        # 连续3根K线均满足 12均线 > 24均线


        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        long_conditions = []
        short_conditions = []
        dataframe.loc[:,'enter_tag'] = ''


        #做多long1 趋势类
        stable_golden_3days = (
                (dataframe['ema_12'] > dataframe['ema_24']) &
                (dataframe['ema_12'].shift(1) > dataframe['ema_24'].shift(1)) &
                (dataframe['ema_12'].shift(2) > dataframe['ema_24'].shift(2))
        )
        enter_long_1 = (
                (dataframe['close'] > dataframe['ema_120_1h'])
                &
                stable_golden_3days
                &
                # 三天前12 <= 24（确保是刚穿上来不久）
                (dataframe['ema_12'].shift(3) <= dataframe['ema_24'].shift(3))
                &
                (dataframe['volume'] > 0)
        )
        dataframe.loc[enter_long_1, 'enter_tag'] += 'enter_long_1_'
        long_conditions.append(enter_long_1)
        #做多long2 抄底类
        enter_long_2 = (
            (dataframe['close'] > dataframe['ema_120_1h'])
            &
            (dataframe['umacd'].between(self.buy_umacd_min.value, self.buy_umacd_max.value))
            &
            (dataframe['volume'] > 0)
        )
        dataframe.loc[enter_long_2, 'enter_tag'] += 'enter_long_2_'
        long_conditions.append(enter_long_2)
        #做多总函数
        if long_conditions:
            dataframe.loc[
                reduce(lambda x, y: x | y, long_conditions),
                'enter_long'
            ] = 1
        else:
            dataframe.loc[(),['enter_long','enter_tag']] = (0, 'no_long_enter')


        # #做空short1
        # enter_short_1 = (
        #         (dataframe['close'] < dataframe['ema_120_1h'])
        #         &
        #         qtpylib.crossed_below(dataframe['ema_12'], dataframe['ema_24'])
        #         &
        #         (dataframe['volume'] > 0)
        # )
        # dataframe.loc[enter_short_1, 'enter_tag'] += 'enter_short_1_'
        # short_conditions.append(enter_short_1)
        # #做空总函数可添加
        # if short_conditions:
        #     dataframe.loc[
        #         reduce(lambda x, y: x & y, long_conditions),
        #         'enter_long'
        #     ] = 1
        # else:
        #     dataframe.loc[(),['enter_short','enter_tag']] = (0, 'no_long_short')
        # dataframe
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # dataframe.loc[
        #     (
        #             (dataframe['close'] < dataframe['ema_120_1h'])
        #             &
        #             (dataframe['volume'] > 0)
        #     ),
        #     ['exit_long', 'exit_tag']] = (1, 'sell_long')

        # dataframe.loc[
        #     (
        #             (dataframe['close'] > dataframe['ema_120_1h'])
        #             &
        #             qtpylib.crossed_above(dataframe['ema_12'], dataframe['ema_24'])
        #             &
        #             (dataframe['volume'] > 0)
        #     ),
        #     ['exit_short', 'exit_tag']] = (1, 'sell_short')

        dataframe.loc['',['exit_long','exit_tag']] = (0, 'no_long_exit')

        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: str | None,
                            side: str, **kwargs) -> bool:
        if entry_tag =="":
            return False
        return True

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()

        if trade.enter_tag == 'enter_long_1_':
            if last_candle['ema_12'] < last_candle['ema_24']:
                return 'custom_exit_long_1'
        return None

    def confirm_trade_exit(self, pair: str, trade: Trade, order_type: str, amount: float,
                           rate: float, time_in_force: str, exit_reason: str,
                           current_time: datetime, **kwargs) -> bool:
        # if trade.enter_tag == 'enter_long_2_' and exit_reason  == 'exit_signal':
        #     return False
        return True
