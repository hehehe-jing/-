from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta

class TEST4(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short: bool = False

    # 止盈目标提高，让利润奔跑
    minimal_roi = {
        "0": 0.025,   # 2.5%
        "30": 0.015,  # 1.5%
        "60": 0.008   # 0.8%
    }

    # 收紧止损，控制单笔亏损
    stoploss = -0.015   # -1.5%

    # 启用移动止损，锁定利润
    trailing_stop = True
    trailing_stop_positive = 0.01        # 盈利1%后启动移动止损
    trailing_stop_positive_offset = 0.02 # 盈利2%时移动止损线设为1%
    trailing_only_offset_is_reached = True

    process_only_new_candles = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()

        # 底分型定义（保持你的逻辑）
        df['1_low'] = df['low'].shift(3)
        df['1_high'] = df['high'].shift(3)
        df['2_low'] = df['low'].shift(2)
        df['2_high'] = df['high'].shift(2)
        df['3_low'] = df['low'].shift(1)
        df['3_high'] = df['high'].shift(1)
        df['4_low'] = df['low']
        df['4_high'] = df['high']

        cond1 = (df['2_low'] < df['1_low']) & (df['2_low'] < df['3_low'])
        cond2 = (df['2_high'] < df['1_high']) & (df['2_high'] < df['3_high'])
        cond3 = df['3_high'] > df['1_high']
        cond4 = df['4_high'] > df['3_high']
        df['bottom_fx'] = (cond1 & cond2 & cond3) | (cond1 & cond2 & cond3 & cond4)

        # 趋势过滤：使用更长期的200均线（约16.7小时）
        df['sma200'] = ta.SMA(df['close'], timeperiod=200)

        # 主动卖出信号：20周期EMA
        df['ema20'] = ta.EMA(df['close'], timeperiod=20)

        # 成交量确认：成交量大于20周期均量
        df['volume_ma20'] = df['volume'].rolling(20).mean()

        return df

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 买入条件：底分型 + 价格在200均线上方（上升趋势） + 成交量放大
        dataframe.loc[
            (
                dataframe['bottom_fx'] &
                (dataframe['close'] > dataframe['sma200']) &
                (dataframe['volume'] > dataframe['volume_ma20']) &
                (dataframe['volume'] > 0)
            ),
            'enter_long'] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 主动卖出：价格跌破20EMA
        dataframe.loc[
            (dataframe['close'] < dataframe['ema20']) & (dataframe['volume'] > 0),
            'exit_long'] = 1
        return dataframe