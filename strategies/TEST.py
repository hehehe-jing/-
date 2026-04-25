from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta

class TEST(IStrategy):


    timeframe = '1h'
    stoploss = -0.10
    minimal_roi = {"0": 0.05}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        dataframe['ma5'] = dataframe['close'].rolling(5).mean()
        dataframe['ma20'] = dataframe['close'].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        dataframe.loc[(dataframe['ma5']>dataframe['ma20']) &
                      (dataframe['ma5'].shift(1)<=dataframe['ma20'].shift(1)),'enter_long'
        ]=1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe['ma5'] < dataframe['ma20']) &
                      (dataframe['ma5'].shift(1) >= dataframe['ma20'].shift(1)),'enter_long'
                      ] = 1
        return dataframe