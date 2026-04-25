from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta


class TEST3(IStrategy):
    timeframe = '1h'
    stoploss = -0.05
    minimal_roi = {'0': 0.08}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe['macd'] = macd['macd']
        dataframe['macd_signal'] = macd['macdsignal']
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # MACD 线上穿信号线
        dataframe.loc[
            (dataframe['macd'] > dataframe['macd_signal']) &
            (dataframe['macd'].shift(1) <= dataframe['macd_signal'].shift(1)),
            'enter_long'] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # MACD 线下穿信号线
        dataframe.loc[
            (dataframe['macd'] < dataframe['macd_signal']) &
            (dataframe['macd'].shift(1) >= dataframe['macd_signal'].shift(1)),
            'exit_long'] = 1
        return dataframe