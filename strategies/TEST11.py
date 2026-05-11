"""
TrendRider Public v2.11.0 — Strat Ninja Edition

Philosophy: Ride established trends with WIDE stoploss.
Key insight: crypto swings 2-4% per hour. Stoploss must be >= 5-6%.

Public version:
- No external API calls (FNG, Bybit funding/OI)
- No SQLite price alerts
- No Cornix formatting
- Leverage 1x (spot-safe)
- All TA-Lib indicators and confidence scoring preserved
"""
import json
import requests
import talib.abstract as ta
from datetime import datetime, timedelta

from mypy.checker import defaultdict

from freqtrade.persistence import Trade
from freqtrade.rpc.api_server.api_trading import profit
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, merge_informative_pair
from pandas import DataFrame
from functools import reduce
import logging

logger = logging.getLogger(__name__)


class TEST11(IStrategy):
    INTERFACE_VERSION = 3

    # --- ROI: Hyperopt-optimized (2026-03-23, 5 pairs) ---
    minimal_roi = {
        "0": 0.229,     # 22.9% immediate
        "124": 0.136,   # 13.6% after ~2h
        "290": 0.044,   # 4.4% after ~5h
        "764": 0,       # breakeven after ~12.7h
    }

    # --- Stoploss: WIDE for crypto volatility ---
    stoploss = -0.06           # 6% default (ATR-based custom stoploss overrides)
    use_custom_stoploss = False

    # --- Trailing Stop: WIDE ---
    trailing_stop = True
    trailing_stop_positive = 0.03        # 3% trail
    trailing_stop_positive_offset = 0.05 # Activate after +5%
    trailing_only_offset_is_reached = True  #盈利达到百分之五之后出发止损，然后每涨到一个最新价格，止损线上涨百分之三锁定利润

    # --- General ---
    timeframe = "1h"
    startup_candle_count = 210
    process_only_new_candles = True
    can_short = False
    position_adjustment_enable = False

    # --- Protections (moved from config.json for Freqtrade 2026.2+) ---
    # protections = [
    #     {
    #         "method": "CooldownPeriod",
    #         "stop_duration": 20  #20分钟内不再开新单
    #     },
    #     {
    #         "method": "StoplossGuard",
    #         "lookback_period": 720,
    #         "trade_limit": 3,
    #         "stop_duration": 60,
    #         "only_per_pair": False#720分钟内发生3次止损的话暂停交易60分钟
    #     },
    #     {
    #         "method": "MaxDrawdown",
    #         "lookback_period": 1440,             # 回看过去 1440 分钟（24 小时）
    #         "max_allowed_drawdown": 0.10,        # 允许的最大回撤 10%
    #         "stop_duration": 300,                # 触发后暂停交易 300 分钟（5 小时）
    #         "trade_limit": 5                     # 至少交易 5 笔后才激活此检查
    #     }
    # ]

    # --- HyperOpt Results (applied from optimization session 2026-03-23) ---
    buy_params = {
        "adx_threshold": 27,
        "ema_fast": 15,
        "ema_slow": 29,
        "rsi_bounce": 28,
        "rsi_period": 12,
        "rsi_pullback_high": 58,
        "rsi_pullback_low": 45,
        "volume_factor": 1.031,
    }
    plot_config = {
        # ========== 主图 ==========
        'main_plot': {
            # 优化后的快慢EMA（金叉信号核心）
            'ema_15': {'color': '#00BFFF', 'label': 'EMA 15 (Fast)'},  # 快线 - 深天蓝
            'ema_29': {'color': '#FFA500', 'label': 'EMA 29 (Slow)'},  # 慢线 - 橙色

            # 中期趋势
            'ema_50': {'color': '#32CD32', 'label': 'EMA 50'},  # 绿

            # 长期趋势（牛熊分界线）
            'ema_200': {'color': '#FF1493', 'label': 'EMA 200'},  # 粉红

            # 布林带（上下轨虚线）
            'bb_upper': {'color': '#9370DB', 'type': 'dash', 'label': 'BB Upper'},
            'bb_lower': {'color': '#9370DB', 'type': 'dash', 'label': 'BB Lower'},

            # 日线EMA200（若存在，粗虚线）
            'ema_200_1d': {'color': '#8B0000', 'type': 'dash', 'label': 'EMA 200 (1d)'},
        },

        # ========== 副图 ==========
        'subplots': {
            # 1. RSI（优化周期 = 12）
            'RSI': {
                'rsi_12': {'color': '#7FFF00', 'label': 'RSI 12'},  # 查特酒绿
            },
            # 2. MACD 完整三线
            'MACD': {
                'macd': {'color': '#1E90FF', 'label': 'MACD'},
                'macdsignal': {'color': '#FF4500', 'label': 'Signal'},
                'macdhist': {'color': '#708090', 'type': 'bar', 'label': 'Histogram'},
            },
            # 3. ADX 趋势强度 + 方向线
            'ADX/DI': {
                'adx': {'color': '#FFD700', 'label': 'ADX (14)'},  # 金
                'plus_di': {'color': '#00FA9A', 'label': '+DI'},  # 春绿
                'minus_di': {'color': '#FF6347', 'label': '-DI'},  # 番茄红
            },
            # 4. 成交量及均量
            'Volume': {
                'volume': {'color': '#B0C4DE', 'type': 'bar', 'label': 'Volume'},
                'volume_ema': {'color': '#FF69B4', 'label': 'Volume EMA (20)'},
            },
        }
    }
    # Sell parameters:
    sell_params = {
        "rsi_exit": 79,
    }

    # --- HyperOpt Parameters ---
    ema_fast = IntParameter(5, 15, default=9, space="buy")
    ema_slow = IntParameter(15, 30, default=21, space="buy")
    rsi_period = IntParameter(10, 20, default=14, space="buy")
    rsi_pullback_low = IntParameter(30, 48, default=35, space="buy")
    rsi_pullback_high = IntParameter(52, 65, default=60, space="buy")
    rsi_bounce = IntParameter(25, 35, default=33, space="buy")
    rsi_exit = IntParameter(72, 85, default=78, space="sell")
    adx_threshold = IntParameter(20, 35, default=22, space="buy")
    volume_factor = DecimalParameter(1.0, 2.5, default=1.3, space="buy")

    # --- Leverage: 1x for Strat Ninja (spot-safe) ---
    leverage_value = 1  #一倍杠杆就是不适用杠杆

    def leverage(self, pair: str, current_time, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str,
                 side: str, **kwargs) -> float:
        return 1

    def informative_pairs(self):
        pairs = self.dp.current_whitelist() if self.dp else []
        informative = []
        for pair in pairs:
            informative.append((pair, "4h"))
            informative.append((pair, "1d"))
        # BTC as market sentiment
        informative.append(("BTC/USDT:USDT", "1h"))
        informative.append(("BTC/USDT:USDT", "4h"))
        return informative    #实盘或者模拟盘的时候会自动拉去这些数据，每个交易对的1天和四小时的数据


    def _send_wecom(self, content: str) -> None:
        """发送 Markdown 消息到企业微信群机器人"""
        webhook_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=939cb90f-dd93-46d9-88fb-3fbdf4f57f75"
        headers = {"Content-Type": "application/json"}
        data = {
            "msgtype": "markdown",
            "markdown": {"content": content}
        }
        try:
            response = requests.post(webhook_url, data=json.dumps(data), headers=headers, timeout=10)
            logger.info(f"WeCom response: {response.json()}")
        except Exception as e:
            logger.error(f"Failed to send WeCom message: {e}")


    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # EMAs (all periods for hyperopt ranges)
        for period in range(5, 31):    #提前计算5到30的所以ema会用到
            dataframe[f"ema_{period}"] = ta.EMA(dataframe, timeperiod=period)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        # RSI (all periods for hyperopt range 10-20)
        for period in range(10, 21):    #提前计算10到20的所以rsi会用到,进行超参数优化的时候有个范围
            dataframe[f"rsi_{period}"] = ta.RSI(dataframe, timeperiod=period)

        # ADX
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)#衡量趋势的强度（无论上涨还是下跌），值越高代表趋势越强。
        dataframe["plus_di"] = ta.PLUS_DI(dataframe, timeperiod=14)#当 plus_di > minus_di 时表示上涨动能占优，是多头信号的一个确认条件
        dataframe["minus_di"] = ta.MINUS_DI(dataframe, timeperiod=14)

        # MACD
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd["macd"]#两者差值
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]#柱状图（直方图），反映动能变化的快慢   就是绿柱子红柱子
        dataframe["macdhist_prev"] = macd["macdhist"].shift(1)

        # Bollinger Bands  布林带
        bb = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_upper"] = bb["upperband"]
        dataframe["bb_middle"] = bb["middleband"]
        dataframe["bb_lower"] = bb["lowerband"]
        # BB width for volatility regime
        dataframe["bb_width"] = (dataframe["bb_upper"] - dataframe["bb_lower"]) / (dataframe["bb_middle"] + 1e-10)
        #衡量波动率大小。带宽越大，价格波动越剧烈；带宽越小，市场越趋于横盘整理。
        dataframe["bb_width_sma"] = ta.SMA(dataframe["bb_width"], timeperiod=50)
        #bb_width 显著高于 bb_width_sma 时，表示当前处于高波动状态；反之则处于低波动状态。

        # Volume (fix #4: epsilon guard against division by zero)
        dataframe["volume_ema"] = ta.EMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = dataframe["volume"] / (dataframe["volume_ema"] + 1e-10)
        #volume_ratio 值	含义
        # > 1.0	当前成交量高于近期平均水平，属于放量
        #= 1.0	成交量与平均水平持平
        #< 1.0	成交量低于近期平均水平，属于缩量
        #远大于 1.0（如 > 1.5）	显著放量，通常伴随重要价格变动


        # OBV
        dataframe["obv"] = ta.OBV(dataframe)#反映资金流入流出的累积趋势。OBV 上升表示资金净流入，下降表示净流出
        dataframe["obv_ema"] = ta.EMA(dataframe["obv"], timeperiod=20)
        #obv > obv_ema，表示当前 OBV 处于其均线上方，确认资金流向与趋势方向一致。

        # ATR for dynamic stoploss
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        #衡量市场波动幅度。ATR 越大，说明价格波动越剧烈

        # Regime
        dataframe["is_bull"] = (
            (dataframe["close"] > dataframe["ema_200"]) &
            (dataframe["ema_50"] > dataframe["ema_200"])
        ).astype(int)

        dataframe["is_bear"] = (
            (dataframe["close"] < dataframe["ema_200"]) &
            (dataframe["ema_50"] < dataframe["ema_200"])
        ).astype(int)
        #判断大趋势是上升还是下降

        # --- LONG pullback detection ---
        ema_slow_key = f"ema_{self.ema_slow.value}"
        if ema_slow_key in dataframe.columns:
            dataframe["pullback_to_ema"] = (
                (dataframe["low"] <= dataframe[ema_slow_key] * 1.02) &
                (dataframe["close"] > dataframe[ema_slow_key]) &
                (dataframe["close"] > dataframe["open"])  # Bullish candle
            ).astype(int)
        else:
            dataframe["pullback_to_ema"] = 0
        #有效回踩判断   回踩均线    价格回踩慢速 EMA 并阳线反弹

        # EMA50 support bounce (LONG)
        dataframe["ema50_bounce"] = (
            (dataframe["low"] <= dataframe["ema_50"] * 1.01) &
            (dataframe["close"] > dataframe["ema_50"]) &
            (dataframe["close"] > dataframe["open"])
        ).astype(int)
        # 有效回踩判断   回踩均线    价格回踩50天 EMA 并阳线反弹  对应深度回调


        # --- Multi-Timeframe data ---
        if self.dp:
            # 4h data for current pair
            df_4h = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe='4h')
            if len(df_4h) > 0:
                df_4h['ema_50'] = ta.EMA(df_4h, timeperiod=50)
                df_4h['ema_200'] = ta.EMA(df_4h, timeperiod=200)
                df_4h['rsi_14'] = ta.RSI(df_4h, timeperiod=14)
                df_4h['adx'] = ta.ADX(df_4h, timeperiod=14)
                df_4h['is_bull'] = (
                    (df_4h['close'] > df_4h['ema_200']) &
                    (df_4h['ema_50'] > df_4h['ema_200'])
                ).astype(int)
                dataframe = merge_informative_pair(
                    dataframe,
                    df_4h[['date', 'ema_50', 'ema_200', 'rsi_14', 'adx', 'is_bull']],
                    self.timeframe, '4h', ffill=True
                )
            else:
                dataframe['ema_50_4h'] = 0
                dataframe['ema_200_4h'] = 0
                dataframe['rsi_14_4h'] = 50
                dataframe['adx_4h'] = 0
                dataframe['is_bull_4h'] = 0
            #将4小时的一些指标添加进一小时的框架中可以调用    看短期趋势

            # Daily data for macro trend
            df_1d = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe='1d')
            if len(df_1d) > 0:
                df_1d['ema_200'] = ta.EMA(df_1d, timeperiod=200)
                dataframe = merge_informative_pair(
                    dataframe,
                    df_1d[['date', 'ema_200']],
                    self.timeframe, '1d', ffill=True
                )
            else:
                dataframe['ema_200_1d'] = 0
            # 将1天的一些指标添加进一小时的框架中可以调用   看长期趋势

            # BTC market sentiment
            df_btc = self.dp.get_pair_dataframe(pair='BTC/USDT:USDT', timeframe='1h')
            if len(df_btc) > 0:
                df_btc['btc_ema_200'] = ta.EMA(df_btc, timeperiod=200)
                df_btc['btc_ema_50'] = ta.EMA(df_btc, timeperiod=50)
                df_btc['btc_rsi'] = ta.RSI(df_btc, timeperiod=14)
                df_btc['btc_is_bull'] = (
                    (df_btc['close'] > df_btc['btc_ema_200']) &
                    (df_btc['btc_ema_50'] > df_btc['btc_ema_200'])
                ).astype(int)
                dataframe = merge_informative_pair(
                    dataframe,
                    df_btc[['date', 'btc_ema_200', 'btc_ema_50', 'btc_rsi', 'btc_is_bull']],
                    self.timeframe, '1h', ffill=True
                )
            else:
                dataframe['btc_is_bull_1h'] = 1
                dataframe['btc_rsi_1h'] = 50
            #主要用于看bct也就是大盘的指标，添加到一小时框架中
        else:
            # Safety fallback when dp is not available
            dataframe['is_bull_4h'] = dataframe['is_bull']
            dataframe['rsi_14_4h'] = dataframe['rsi_14'] if 'rsi_14' in dataframe.columns else 50
            dataframe['adx_4h'] = dataframe['adx']
            dataframe['btc_is_bull_1h'] = 1
            dataframe['btc_rsi_1h'] = 50
            dataframe['ema_200_1d'] = 0

        # Ensure columns exist (safety for backtesting edge cases)
        for col, default in [
            ('is_bull_4h', 1), ('rsi_14_4h', 50), ('adx_4h', 20),
            ('btc_is_bull_1h', 1), ('btc_rsi_1h', 50),
            ('ema_200_1d', 0),
        ]:
            if col not in dataframe.columns:
                dataframe[col] = default

        dataframe['fng_value'] = 50  # 恐惧贪婪指数 → 中性
        dataframe['funding_rate'] = 0.0  # 资金费率 → 无倾向
        dataframe['funding_extreme'] = 0  # 资金费率极端标志 → 无
        dataframe['oi_change'] = 0.0  # 持仓量变化 → 无变化

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        rsi = f"rsi_{self.rsi_period.value}"

        # ========== LONG ENTRIES ==========

        # === LONG 1: Trend Pullback to EMA ===   回踩慢速均线确认反弹时买入
        conditions_pullback = [
            dataframe["is_bull"] == 1,
            dataframe["pullback_to_ema"] == 1,
            dataframe[rsi] > self.rsi_pullback_low.value,
            dataframe[rsi] < self.rsi_pullback_high.value,
            dataframe["adx"] > self.adx_threshold.value,
            dataframe["volume_ratio"] > self.volume_factor.value,
            dataframe["plus_di"] > dataframe["minus_di"],
            dataframe["obv"] > dataframe["obv_ema"],
            dataframe["volume"] > 0,
            dataframe["btc_rsi_1h"] > 35,
            dataframe["fng_value"] >= 25,      # Not extreme fear
            dataframe["fng_value"] <= 85,      # Not extreme greed
            dataframe[rsi] < 70,               # Not overbought
        ]
        # Daily EMA200 filter — helps filter bad entries
        if 'ema_200_1d' in dataframe.columns:
            conditions_pullback.append(dataframe["close"] > dataframe["ema_200_1d"])

        dataframe.loc[
            reduce(lambda x, y: x & y, conditions_pullback),
            ["enter_long", "enter_tag"]
        ] = (1, "trend_pullback")

        # === LONG 2: EMA50 Support Bounce ===   回踩50小时均线确认反弹时买入
        conditions_ema50 = [
            dataframe["is_bull"] == 1,
            dataframe["ema50_bounce"] == 1,
            dataframe[rsi] > 30,
            dataframe[rsi] < 50,
            dataframe["adx"] > 20,
            dataframe["volume_ratio"] > 1.0,
            dataframe["macdhist"] > dataframe["macdhist"].shift(1),
            dataframe["volume"] > 0,
            dataframe["btc_rsi_1h"] > 35,
            dataframe["fng_value"] >= 25,
            dataframe["fng_value"] <= 85,
            dataframe[rsi] < 70,
        ]
        dataframe.loc[
            reduce(lambda x, y: x & y, conditions_ema50),
            ["enter_long", "enter_tag"]
        ] = (1, "ema50_bounce")

        # === LONG 3: RSI Oversold Bounce ===  rsi超卖反弹的时候买入
        conditions_rsi = [
            dataframe["close"] > dataframe["ema_200"],
            dataframe[rsi].shift(1) < self.rsi_bounce.value,
            dataframe[rsi] > self.rsi_bounce.value,
            dataframe["close"] > dataframe["bb_lower"],
            dataframe["close"] > dataframe["open"],
            dataframe["volume_ratio"] > 0.8,
            dataframe["obv"] > dataframe["obv_ema"],
            dataframe["volume"] > 0,
            dataframe["btc_rsi_1h"] > 35,
            dataframe["fng_value"] >= 25,
            dataframe["fng_value"] <= 85,
        ]
        dataframe.loc[
            reduce(lambda x, y: x & y, conditions_rsi),
            ["enter_long", "enter_tag"]
        ] = (1, "rsi_bounce")

        # === LONG 4: EMA Crossover (golden cross on fast EMAs) ===   快速均线向上穿过慢速均线时买入
        #  ema金叉时买入
        ema_fast_key = f"ema_{self.ema_fast.value}"
        ema_slow_key = f"ema_{self.ema_slow.value}"
        conditions_ema_cross = [
            (dataframe[ema_fast_key] > dataframe[ema_slow_key]) &
            (dataframe[ema_fast_key].shift(1) <= dataframe[ema_slow_key].shift(1)),  # crossed above
            dataframe[rsi] > 40,
            dataframe[rsi] < 75,
            dataframe["close"] > dataframe["ema_200"],
            dataframe["volume_ratio"] > 0.5,
            dataframe["volume"] > 0,
            dataframe["btc_rsi_1h"] > 35,
            dataframe["fng_value"] >= 25,
            dataframe["fng_value"] <= 85,
        ]
        dataframe.loc[
            reduce(lambda x, y: x & y, conditions_ema_cross),
            ["enter_long", "enter_tag"]
        ] = (1, "ema_crossover")

        # === LONG 5: Bollinger Band Bounce (V4: tightened vol 0.3→0.7, added ADX>18) ===  布林带下轨反弹买入
        conditions_bb = [
            dataframe["close"] <= dataframe["bb_lower"] * 1.005,           # close within 0.5% of BB lower
            dataframe["close"] > dataframe["open"],                         # bullish candle (bounce)
            dataframe[rsi] < 45,
            dataframe["volume_ratio"] > 0.7,                                # V4: was 0.3, filter weak bounces
            dataframe["adx"] > 18,                                          # V4: trend strength filter
            dataframe["volume"] > 0,
            dataframe["btc_rsi_1h"] > 35,
            dataframe["fng_value"] >= 25,
            dataframe["fng_value"] <= 85,
        ]
        dataframe.loc[
            reduce(lambda x, y: x & y, conditions_bb),
            ["enter_long", "enter_tag"]
        ] = (1, "bb_bounce")

        # === LONG 6: MACD Histogram Reversal (tightened: RSI 40-60, EMA200 filter, volume 0.8x) ===
        conditions_macd = [
            (dataframe["macdhist"] > 0) &
            (dataframe["macdhist"].shift(1) <= 0),  # histogram crossed above zero
            dataframe["close"] > dataframe["ema_50"],
            dataframe["close"] > dataframe["ema_200"],  # confirm uptrend
            dataframe[rsi] > 40,
            dataframe[rsi] < 60,
            dataframe["adx"] > 15,
            dataframe["volume_ratio"] > 0.8,            # volume confirmation
            dataframe["volume"] > 0,
            dataframe["btc_rsi_1h"] > 35,
            dataframe["fng_value"] >= 25,
            dataframe["fng_value"] <= 85,
        ]
        dataframe.loc[
            reduce(lambda x, y: x & y, conditions_macd),
            ["enter_long", "enter_tag"]
        ] = (1, "macd_reversal")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        rsi = f"rsi_{self.rsi_period.value}"
        ema_fast = f"ema_{self.ema_fast.value}"
        ema_slow = f"ema_{self.ema_slow.value}"

        # ========== LONG EXITS ==========

        # EXIT 1: RSI very overbought
        dataframe.loc[
            (dataframe[rsi] > self.rsi_exit.value) &
            (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "rsi_overbought")

        # EXIT 2: Bearish EMA cross with MACD confirmation
        dataframe.loc[
            (dataframe[ema_fast] < dataframe[ema_slow]) &
            (dataframe[ema_fast].shift(1) >= dataframe[ema_slow].shift(1)) &
            (dataframe["macdhist"] < 0) &
            (dataframe[rsi] > 50) &
            (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "ema_bearish_cross")

        # EXIT 3: Price drops below EMA200 by 1%+ (trend broken, softened to avoid premature exits)
        dataframe.loc[
            (dataframe["close"] < dataframe["ema_200"] * 0.99) &
            (dataframe["close"].shift(1) >= dataframe["ema_200"].shift(1)) &
            (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "trend_broken")

        # EXIT 4 (V4): Trend early warning — RSI overbought reversal near EMA200
        # Catches trend exhaustion before price breaks support, saving avg -3% vs trend_broken
        dataframe.loc[
            (dataframe["close"] < dataframe["ema_200"] * 0.995) &  # within 0.5% of breaking
            (dataframe[rsi] > 72) &                                  # exhausted
            (dataframe["macdhist"] < dataframe["macdhist"].shift(1)) & # momentum dropping
            (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "trend_early_warning")

        return dataframe


    # def bot_loop_start(self, current_time: datetime, **kwargs) -> None:
    #     ndays = 20*6
    #     x_minutes = 60*8
    #     current_timestamp = current_time.timestamp()
    #     last_execution_timestame = getattr(self,'last_execution_timestame',0)
    #     if current_timestamp - last_execution_timestame >= round(x_minutes,0):
    #         closed_trades = Trade.get_trades_proxy(is_open=False)
    #         profit_by_category = defaultdict(float)
    #         for trade in closed_trades:
    #             profit_by_category["空单" if trade.is_short else "多单"] += trade.close_profit_abs
    #             profit_by_category[trade.enter_tag]  += trade.close_profit_abs
    #
    #         for category in profit_by_category.items():
    #             logger.info(f"最近{ndays}天,{category}收益:{profit}")
    #
    #         self.last_execution_timestame = current_timestamp



    def _calc_confidence(self, last: dict) -> tuple:       #打分机制
        """Calculate signal confidence based on weighted indicator alignment.

        Max score ~17.5. Returns (level_str, bar_str, details_list, numeric_level).
        """
        score = 0.0
        details = []
        rsi_key = f"rsi_{self.rsi_period.value}"
        rsi_val = last.get(rsi_key, 50)

        # RSI in healthy zone (not overbought): +1.5
        if 35 < rsi_val < 60:
            score += 1.5
            details.append("RSI healthy")

        # Strong trend (ADX): +2.5 strong, +1.5 moderate
        adx_val = last.get('adx', 0)
        if adx_val > 30:
            score += 2.5
            details.append("Strong trend")
        elif adx_val > self.adx_threshold.value:
            score += 1.5
            details.append("Moderate trend")

        # Volume confirmation: +2.5 high, +1.5 normal
        vol_ratio = last.get('volume_ratio', 0)
        if vol_ratio > 1.5:
            score += 2.5
            details.append("High volume")
        elif vol_ratio > 1.0:
            score += 1.5
            details.append("Normal volume")

        # MACD positive histogram: +1.5, bonus +0.5 if rising
        macd_hist = last.get('macdhist', 0)
        macd_hist_prev = last.get('macdhist_prev', 0)
        if macd_hist > 0:
            score += 1.5
            if macd_hist > macd_hist_prev:
                score += 0.5
                details.append("MACD positive+rising")
            else:
                details.append("MACD positive")

        # OBV rising AND above EMA: +1.5
        if last.get('obv', 0) > last.get('obv_ema', 0):
            score += 1.5
            details.append("OBV rising")

        # BTC healthy (RSI 40-70): +1.5
        btc_rsi = last.get('btc_rsi_1h', 50)
        if 40 < btc_rsi < 70:
            score += 1.5
            details.append("BTC healthy")

        # 4h trend alignment AND ADX_4h > 20: +1.5
        if last.get('is_bull_4h', 0) == 1 and last.get('adx_4h', 0) > 20:
            score += 1.5
            details.append("4H trend aligned")

        # Bollinger Band position (close near lower = good for long): +1
        close = last.get('close', 0)
        bb_lower = last.get('bb_lower', 0)
        bb_upper = last.get('bb_upper', 0)
        bb_range = bb_upper - bb_lower if bb_upper > bb_lower else 1
        if bb_lower > 0 and close > 0:
            bb_position = (close - bb_lower) / bb_range
            if bb_position < 0.35:
                score += 1.0
                details.append("Near BB lower")

        # Plus_DI > Minus_DI spread > 10: +1
        plus_di = last.get('plus_di', 0)
        minus_di = last.get('minus_di', 0)
        if plus_di - minus_di > 10:
            score += 1.0
            details.append("Strong DI spread")

        # FNG bonus: neutral/healthy (40-60): +1
        fng_val = last.get('fng_value', 50)
        if 40 <= fng_val <= 60:
            score += 1.0
            details.append("FNG neutral")

        # On-chain: healthy funding rate: +1
        funding = last.get('funding_rate', 0)
        if abs(funding) < 0.0001:  # Normal funding
            score += 1
            details.append("Healthy funding")

        # Smooth mapping to 1-10 (max score ~17.5)
        numeric = max(1, min(10, round(score * 10 / 17.5)))

        # Level label
        # if numeric >= 8:
        #     level = "STRONG"
        # elif numeric >= 6:
        #     level = "GOOD"
        # elif numeric >= 4:
        #     level = "MEDIUM"
        # else:
        #     level = "WEAK"
        if numeric >= 6:
            level = "STRONG"
        elif numeric >= 4:
            level = "GOOD"
        elif numeric >= 2:
            level = "MEDIUM"
        else:
            level = "WEAK"
        # Dynamic bar
        bar = "|" * numeric + "-" * (10 - numeric) + f" {numeric}/10"

        return level, bar, details, numeric   #返回四个数据分别是等级，打了多少分，什么类型的加分，

    def _market_context(self, last: dict) -> str:
        """Generate market context string."""
        btc_rsi = last.get('btc_rsi_1h', 50)
        btc_bull = last.get('btc_is_bull_1h', 0)
        bull_4h = last.get('is_bull_4h', 0)

        if btc_bull and btc_rsi > 55:
            btc_status = "Bullish"
        elif btc_rsi > 40:
            btc_status = "Neutral"
        else:
            btc_status = "Bearish"

        tf_4h = "Uptrend" if bull_4h else "Downtrend"

        parts = [f"BTC: {btc_status} (RSI {btc_rsi:.0f})", f"4H: {tf_4h}"]

        return " | ".join(parts)

    def _get_market_regime(self, last: dict) -> str:
        """Detect market regime from ADX + EMA200 + BB width."""
        adx_val = last.get('adx', 0)
        ema_200 = last.get('ema_200', 0)
        close = last.get('close', 0)
        is_bull = last.get('is_bull', 0)
        bb_width = last.get('bb_width', 0)
        bb_width_sma = last.get('bb_width_sma', 0)

        high_vol = bb_width > bb_width_sma * 1.5 if bb_width_sma > 0 else False

        if adx_val < 20:
            return "Ranging (High Vol)" if high_vol else "Ranging"
        elif is_bull and close > ema_200:
            return "Trending Bull"
        else:
            return "Trending Bear (High Vol)" if high_vol else "Trending Bear"

    def custom_exit(self, pair: str, trade, current_time: datetime,  #类似于时间止盈机制
                    current_rate: float, current_profit: float, **kwargs):
        """V4 cascading early exit — stop bleeding before 24h timeout.

        Real dry-run data (51 trades): time_exit_24h cost -$13.01 across 9 trades,
        avg -2.85% loss after holding full 24h. Cascade catches losers earlier:
        - 2h: cut if -1.5% (already broken thesis)
        - 4h: cut if red (no recovery momentum)
        - 8h: cut if not at +0.5% (dead trade)
        - 16h: cut if not at +1% (final mercy)
        """
        duration_hours = (current_time - trade.open_date_utc).total_seconds() / 3600
        if duration_hours >= 2 and current_profit < -0.015:
            return "early_loss_cut_2h"
        if duration_hours >= 4 and current_profit < 0:
            return "early_loss_cut_4h"
        if duration_hours >= 8 and current_profit < 0.005:
            return "early_loss_cut_8h"
        if duration_hours >= 16 and current_profit < 0.01:
            return "early_loss_cut_16h"
        if duration_hours >= 24:
            return "time_exit_24h"
        return None

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: str | None,
                           side: str, **kwargs) -> bool:
        # Calculate levels (LONG only, can_short = False)
        sl_price = rate * (1 + self.stoploss)
        tp2_price = rate * 1.05   # +5%

        leverage = self.leverage_value
        side_str = "LONG"

        # Risk/reward ratio
        risk = abs(rate - sl_price)
        reward = abs(tp2_price - rate)
        rr_ratio = reward / risk if risk > 0 else 0

        # Entry reason mapping
        reasons = {
            "trend_pullback": "Pullback to EMA in uptrend, bounce with volume confirmation",
            "ema50_bounce": "Deep pullback to EMA50, bounce with rising MACD",
            "rsi_bounce": "RSI oversold, bounce from lower Bollinger in bull market",
            "ema_crossover": "EMA9 crossed above EMA16, golden cross with trend confirmation",
            "bb_bounce": "Price bounced from lower Bollinger Band with oversold RSI",
            "macd_reversal": "MACD histogram turned positive, momentum shift above EMA50",
        }
        reason = reasons.get(entry_tag, entry_tag or "Signal")

        # Get current indicators for context
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) > 0:
            last = dataframe.iloc[-1]
            rsi_key = f"rsi_{self.rsi_period.value}"
            rsi_val = last.get(rsi_key, 0)
            adx_val = last.get("adx", 0)
            vol_ratio = last.get("volume_ratio", 0)
            macd_hist = last.get("macdhist", 0)
        else:
            rsi_val = adx_val = vol_ratio = macd_hist = 0
            last = {}

        # Confidence & market context
        conf_level, conf_bar, conf_details, conf_numeric = self._calc_confidence(last)
        market_ctx = self._market_context(last)
        regime = self._get_market_regime(last)

        # --- REJECT WEAK SIGNALS ---
        min_conf = 5 if "Bear" in regime else 4
        if conf_numeric < min_conf:
            # logger.info(f"Rejecting signal for {pair}: confidence {conf_numeric}/10 < {min_conf} (regime: {regime})")
            return False

        # --- Main Telegram Signal ---
        msg = (
            f"*TRENDRIDER SIGNAL*\n"
            f"{'='*28}\n"
            f"*{pair}* | *{side_str}* | {leverage}x\n"
            f"{'='*28}\n\n"
            f"*Entry:* `{rate:.2f}` USDT\n"
            f"*Stop Loss:* `{sl_price:.2f}` ({self.stoploss*100:+.1f}%)\n"
            f"  R:R = 1:{rr_ratio:.1f}\n\n"
            f"*Confidence:* {conf_level}\n"
            f"  [{conf_bar}]\n"
            f"  {', '.join(conf_details)}\n\n"
            f"*Regime:* {regime}\n"
            f"*Indicators:*\n"
            f"  RSI: {rsi_val:.1f} | ADX: {adx_val:.1f}\n"
            f"  Volume: {vol_ratio:.2f}x | MACD: {'+'  if macd_hist > 0 else '-'}\n\n"
            f"*Market:* {market_ctx}\n\n"
            f"*Why:* {reason}\n"
            f"{'='*28}\n"
            f"_TrendRider AI_"
        )
        #self.dp.send_msg(msg, always_send=True)
        self._send_wecom(msg)
        return True

    def confirm_trade_exit(self, pair: str, trade, order_type: str, amount: float,
                          rate: float, time_in_force: str, exit_reason: str,
                          current_time: datetime, **kwargs) -> bool:
        # Calculate results (LONG only)
        profit_pct = ((rate - trade.open_rate) / trade.open_rate) * 100 * trade.leverage
        duration_hours = (current_time - trade.open_date_utc).total_seconds() / 3600

        # Exit reason mapping
        exit_reasons = {
            "roi": "ROI target reached",
            "stop_loss": "Stop Loss hit",
            "trailing_stop_loss": "Trailing Stop",
            "exit_signal": "Exit signal",
            "rsi_overbought": "RSI overbought (>81)",
            "ema_bearish_cross": "EMA bearish crossover",
            "trend_broken": "Trend broken (below EMA200)",
            "force_exit": "Force exit",
            "time_exit_24h": "Time exit (24h, low profit)",
        }
        reason_text = exit_reasons.get(exit_reason, exit_reason)

        # Result line
        if profit_pct > 0:
            result_line = f"+{profit_pct:.2f}%"
        else:
            result_line = f"{profit_pct:.2f}%"

        # Duration formatting
        if duration_hours < 1:
            dur_str = f"{int(duration_hours * 60)}m"
        elif duration_hours < 24:
            dur_str = f"{duration_hours:.1f}h"
        else:
            dur_str = f"{duration_hours/24:.1f}d"

        msg = (
            f"*TRADE CLOSED* {'WIN' if profit_pct > 0 else 'LOSS'}\n"
            f"{'='*25}\n"
            f"*{pair}* | LONG | {trade.leverage}x\n"
            f"{'='*25}\n\n"
            f"*Entry:* `{trade.open_rate:.2f}`\n"
            f"*Exit:* `{rate:.2f}`\n"
            f"*Result:* *{result_line}*\n"
            f"*Duration:* {dur_str}\n"
            f"*Reason:* {reason_text}\n"
            f"*Max price:* `{trade.max_rate:.2f}`\n"
            f"{'='*25}\n"
            f"_TrendRider AI_"
        )

        #self.dp.send_msg(msg, always_send=True)
        self._send_wecom(msg)
        return True