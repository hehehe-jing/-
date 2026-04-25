from freqtrade.exchange import timeframe_to_minutes
from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta

class TEST2(IStrategy):


    timeframe = '1h'
    stoploss = -0.1
    minimal_roi = {
        "0": 0.1,  # 盈利 5% 才止盈
    }


    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        dataframe['rsi'] = ta.RSI(dataframe,timeperio=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        dataframe.loc[dataframe['rsi']<30,'enter_long'
        ]=1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe['rsi'] > 70, 'enter_long'
        ] = 1
        return dataframe