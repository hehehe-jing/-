from freqtrade.strategy import IStrategy
from pandas import DataFrame, Series


class TEST5(IStrategy):
    timeframe = '1h'
    minimal_roi = {"0": 0.01}
    stoploss = -0.01

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['ma5'] = dataframe['close'].rolling(5).mean()
        dataframe['ma20'] = dataframe['close'].rolling(20).mean()
        dataframe['volume20'] = dataframe['volume'].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe['close'] > dataframe['ma5']) &
                      (dataframe['ma5'] > dataframe['ma20']) & (dataframe['volume']>dataframe['volume20']), 'enter_long'
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[((dataframe['close'] < dataframe['ma5']) |
                      (dataframe['ma5']<dataframe['ma20'])) & (dataframe['volume']>dataframe['volume20']), 'exit_long'
        ] = 1
        return dataframe
