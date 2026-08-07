# ============================================================
# SATS BOT - TradingView Pine → Python IBKR Conversion
# Part 1/3
#
# Symbol: NVDA
# Timeframe: 30 Minutes
# Strategy: Goel's Self-Aware Trend System (SATS)
# Long Only
# Target: +$2/share
# ============================================================


from ib_insync import *
import pandas as pd
import numpy as np
import pytz
import datetime
import time
import math


# ============================================================
# CONFIGURATION
# ============================================================

HOST = "127.0.0.1"
PORT = 7497
CLIENT_ID = 1


SYMBOL = "NVDA"
EXCHANGE = "SMART"
CURRENCY = "USD"
BAR_SIZE = "2 mins"

ATR_LENGTH = 10
BASE_MULT = 1.5
HISTORY = "20 D"
ER_LENGTH = 14

TAKE_PROFIT = 0.50


USE_TIME_FILTER = True

SESSION_START = (6,30)
SESSION_END = (1,0)

TIMEZONE = "America/Los_Angeles"


LOOP_SECONDS = 5



# ============================================================
# PINE INPUTS
# ============================================================



USE_ADAPTIVE = True


ADAPT_STRENGTH = 0.5
ATR_BASELINE_LENGTH = 100


USE_TQI = True

QUALITY_STRENGTH = 0.4
QUALITY_CURVE = 1.5


USE_CHAR_FLIP = True

CHAR_MIN_AGE = 5
CHAR_HIGH = 0.55
CHAR_LOW = 0.25


TQI_WEIGHT_ER = 0.35
TQI_WEIGHT_VOL = 0.20
TQI_WEIGHT_STRUCT = 0.25
TQI_WEIGHT_MOM = 0.20


TQI_STRUCT_LENGTH = 20
TQI_MOM_LENGTH = 10



# ============================================================
# IBKR CONNECTION
# ============================================================

ib = IB()


contract = Stock(
    SYMBOL,
    EXCHANGE,
    CURRENCY
)



def connect_ib():

    if not ib.isConnected():

        ib.connect(
            HOST,
            PORT,
            clientId=CLIENT_ID
        )

    print("================================")
    print(" Connected to IBKR")
    print(" Symbol:", SYMBOL)
    print(" Timeframe:", BAR_SIZE)
    print("================================")





# ============================================================
# DOWNLOAD 30 MIN DATA
# ============================================================


def get_history():

    bars = ib.reqHistoricalData(

        contract,

        endDateTime='',

        durationStr=HISTORY,

        barSizeSetting=BAR_SIZE,

        whatToShow='TRADES',

        useRTH=True,

        formatDate=1

    )


    df = util.df(bars)


    if df.empty:
        return None


    df.rename(
        columns={
            "date":"datetime"
        },
        inplace=True
    )


    return df





# ============================================================
# PINE HELPER FUNCTIONS
# ============================================================


def safe_div(num, den, fallback=0.0):

    if den == 0:
        return fallback

    if pd.isna(num):
        return fallback

    if pd.isna(den):
        return fallback

    return num / den




def clamp(value, low, high):

    return max(
        low,
        min(value, high)
    )





# ============================================================
# EFFICIENCY RATIO
# Pine:
# calcEfficiencyRatio()
# ============================================================


def efficiency_ratio(series, length):

    result=[]


    for i in range(len(series)):

        if i < length:

            result.append(np.nan)
            continue


        change = abs(
            series.iloc[i]
            -
            series.iloc[i-length]
        )


        volatility = 0


        for j in range(
            i-length+1,
            i+1
        ):

            volatility += abs(
                series.iloc[j]
                -
                series.iloc[j-1]
            )


        result.append(
            safe_div(
                change,
                volatility,
                0
            )
        )


    return pd.Series(
        result,
        index=series.index
    )





# ============================================================
# ATR
# Pine ta.atr()
# ============================================================


def calculate_atr(df,length):

    high=df["high"]
    low=df["low"]
    close=df["close"]


    tr1 = high-low

    tr2 = abs(
        high-close.shift()
    )

    tr3 = abs(
        low-close.shift()
    )


    tr = pd.concat(
        [
            tr1,
            tr2,
            tr3
        ],
        axis=1
    ).max(axis=1)


    atr = tr.rolling(
        length
    ).mean()


    return atr





# ============================================================
# VOLUME Z SCORE
# ============================================================


def volume_z(df,length=20):

    mean=df.volume.rolling(length).mean()

    std=df.volume.rolling(length).std()


    return (
        (df.volume-mean)
        /
        std
    )





# ============================================================
# SESSION FILTER
# PST 06:30 - 12:00
# ============================================================


def in_buy_window():


    if not USE_TIME_FILTER:

        return True


    tz=pytz.timezone(
        TIMEZONE
    )


    now=datetime.datetime.now(tz)


    current=now.time()


    start=datetime.time(
        SESSION_START[0],
        SESSION_START[1]
    )


    end=datetime.time(
        SESSION_END[0],
        SESSION_END[1]
    )


    return start <= current <= end





# ============================================================
# CURRENT POSITION
# ============================================================


def current_position():

    positions=ib.positions()


    for p in positions:

        if p.contract.symbol == SYMBOL:

            return p.position


    return 0


# ============================================================
# SATS ENGINE
# PART 2/3
# ============================================================


def map_clamp(
        value,
        in_low,
        in_high,
        out_low,
        out_high
):
    t = clamp(
        safe_div(
            value - in_low,
            in_high - in_low,
            0
        ),
        0,
        1
    )

    return (
            out_low +
            t * (out_high - out_low)
    )


# ============================================================
# BUILD SATS INDICATOR
# Pine equivalent:
#
# rawAtr
# erValue
# tqi
# finalMult
# SuperTrend
# Character Flip
# ============================================================


def calculate_sats(df):
    df = df.copy()

    close = df["close"]
    high = df["high"]
    low = df["low"]

    # --------------------------------------------------------
    # ATR
    # --------------------------------------------------------

    df["atr"] = calculate_atr(
        df,
        ATR_LENGTH
    )

    atr_baseline = (
        df["atr"]
        .rolling(
            ATR_BASELINE_LENGTH
        )
        .mean()
    )

    vol_ratio = (
            df["atr"]
            /
            atr_baseline
    )

    # --------------------------------------------------------
    # Efficiency Ratio
    # --------------------------------------------------------

    df["er"] = efficiency_ratio(
        close,
        ER_LENGTH
    )

    df["er"] = (
        df["er"]
        .fillna(0)
    )

    # Pine:
    # atrValue = rawAtr*(0.5+0.5*er)

    df["atr_value"] = (
            df["atr"]
            *
            (
                    0.5
                    +
                    0.5 * df["er"]
            )
    )

    # --------------------------------------------------------
    # TQI ENGINE
    # --------------------------------------------------------

    tqi_er = (
        df["er"]
        .clip(0, 1)
    )

    # Volume Quality

    df["vol_z"] = volume_z(df)

    tqi_vol = []

    for i, row in df.iterrows():

        if not pd.isna(row["volume"]):

            value = map_clamp(
                row["vol_z"],
                -1,
                2,
                0,
                1
            )

        else:

            value = map_clamp(
                vol_ratio.loc[i],
                0.6,
                1.8,
                0,
                1
            )

        tqi_vol.append(value)

    df["tqi_vol"] = tqi_vol

    # Structure Quality

    struct_hi = (
        high
        .rolling(
            TQI_STRUCT_LENGTH
        )
        .max()
    )

    struct_lo = (
        low
        .rolling(
            TQI_STRUCT_LENGTH
        )
        .min()
    )

    price_pos = (
            (close - struct_lo)
            /
            (struct_hi - struct_lo)
    )

    price_pos = price_pos.fillna(0.5)

    df["tqi_struct"] = (
            abs(price_pos - 0.5)
            *
            2
    ).clip(0, 1)

    # Momentum Persistence

    mom_change = (
            close - close.shift(
        TQI_MOM_LENGTH
    )
    )

    up_moves = (
        close.gt(
            close.shift()
        )
        .rolling(
            TQI_MOM_LENGTH
        )
        .sum()
    )

    down_moves = (
        close.lt(
            close.shift()
        )
        .rolling(
            TQI_MOM_LENGTH
        )
        .sum()
    )

    tqi_mom = []

    for i in range(len(df)):

        if mom_change.iloc[i] > 0:

            tqi_mom.append(
                up_moves.iloc[i]
                /
                TQI_MOM_LENGTH
            )

        elif mom_change.iloc[i] < 0:

            tqi_mom.append(
                down_moves.iloc[i]
                /
                TQI_MOM_LENGTH
            )

        else:

            tqi_mom.append(0)

    df["tqi_mom"] = (
        pd.Series(tqi_mom)
        .fillna(0)
        .values
    )

    weight_sum = (
            TQI_WEIGHT_ER
            +
            TQI_WEIGHT_VOL
            +
            TQI_WEIGHT_STRUCT
            +
            TQI_WEIGHT_MOM
    )

    df["tqi"] = (

            (
                    tqi_er * TQI_WEIGHT_ER
                    +
                    df["tqi_vol"] * TQI_WEIGHT_VOL
                    +
                    df["tqi_struct"] * TQI_WEIGHT_STRUCT
                    +
                    df["tqi_mom"] * TQI_WEIGHT_MOM

            )

            /

            weight_sum

    ).clip(0, 1)

    # --------------------------------------------------------
    # ADAPTIVE MULTIPLIER
    # --------------------------------------------------------

    legacy_factor = (

            1
            +
            ADAPT_STRENGTH *
            (
                    0.5 - df["er"]
            )

    )

    quality_deviation = (

            (
                    1 - df["tqi"]
            )
            **
            QUALITY_CURVE

    )

    tqi_mult = (

            1
            -
            QUALITY_STRENGTH

            +

            QUALITY_STRENGTH *

            (
                    0.6
                    +
                    0.8 * quality_deviation
            )

    )

    df["final_mult"] = (

            BASE_MULT
            *
            legacy_factor
            *
            tqi_mult

    )

    # --------------------------------------------------------
    # SUPER TREND BANDS
    # --------------------------------------------------------

    lower = []
    upper = []
    trend = []

    trend_start = []

    current_trend = 1

    start_bar = 0

    for i in range(len(df)):

        atr = df["atr_value"].iloc[i]

        mult = df["final_mult"].iloc[i]

        src = close.iloc[i]

        lower_raw = (
                src
                -
                mult * atr
        )

        upper_raw = (
                src
                +
                mult * atr
        )

        if i == 0:

            lb = lower_raw
            ub = upper_raw


        else:

            previous_close = close.iloc[i - 1]

            if previous_close > lower[i - 1]:

                lb = max(
                    lower_raw,
                    lower[i - 1]
                )

            else:

                lb = lower_raw

            if previous_close < upper[i - 1]:

                ub = min(
                    upper_raw,
                    upper[i - 1]
                )

            else:

                ub = upper_raw

        prev_trend = current_trend

        price_flip_up = (

            prev_trend == -1

            and

            close.iloc[i] > upper[i - 1]

            if i > 0 else False

        )

        price_flip_down = (

            prev_trend == 1

            and

            close.iloc[i] < lower[i - 1]

            if i > 0 else False

        )

        if price_flip_up:

            current_trend = 1


        elif price_flip_down:

            current_trend = -1

        if current_trend != prev_trend:
            start_bar = i

        lower.append(lb)

        upper.append(ub)

        trend.append(current_trend)

        trend_start.append(start_bar)

    df["lower_band"] = lower
    df["upper_band"] = upper
    df["trend"] = trend
    df["trend_age"] = (
            np.arange(len(df))
            -
            np.array(trend_start)
    )

    # --------------------------------------------------------
    # BUY SIGNAL
    # --------------------------------------------------------

    df["flip_up"] = (

            (df["trend"] == 1)

            &

            (df["trend"].shift(1) == -1)

    )

    warmup = max(
        50,
        ATR_LENGTH + ATR_BASELINE_LENGTH
    )

    df["buy_signal"] = (

            df["flip_up"]

            &

            (df.index >= warmup)

    )

    return df

# ============================================================
# SATS EXECUTION ENGINE
# PART 3/3
# ============================================================



def place_buy_order():

    if current_position() > 0:
        print("Already holding NVDA. No new entry.")
        return


    print("SATS BUY SIGNAL")

    order = MarketOrder(
        "BUY",
        ORDER_SIZE
    )


    trade = ib.placeOrder(
        contract,
        order
    )


    ib.sleep(2)


    if trade.orderStatus.status == "Filled":

        fill_price = trade.orderStatus.avgFillPrice

        print(
            f"BUY FILLED: {ORDER_SIZE} shares @ {fill_price}"
        )


        place_take_profit(fill_price)


    else:

        print(
            "Order status:",
            trade.orderStatus.status
        )




# ============================================================
# TAKE PROFIT
# Pine equivalent:
#
# strategy.exit(
# limit = strategy.position_avg_price + tpProfitAmount
# )
#
# ============================================================


def place_take_profit(entry_price):


    target_price = round(
        entry_price + TAKE_PROFIT,
        2
    )


    print(
        "Pine Equivalent TP:",
        target_price
    )


    sell_order = LimitOrder(
        "SELL",
        ORDER_SIZE,
        target_price
    )


    ib.placeOrder(
        contract,
        sell_order
    )


    print(
        "Take profit submitted"
    )




# ============================================================
# CHECK NEW SIGNAL
# ============================================================


def check_signal():


    df = get_history()


    if df is None:
        return



    sats = calculate_sats(df)



    last = sats.iloc[-1]


    print("======================")
    print("SATS STATUS")
    print("======================")

    print(
        "Candle:",
        last.datetime
    )

    print(
        "Close:",
        round(last.close,2)
    )

    print(
        "Trend:",
        "BULLISH"
        if last.trend == 1
        else
        "BEARISH"
    )

    print(
        "TQI:",
        round(last.tqi*100,1),
        "%"
    )

    print(
        "BUY:",
        last.buy_signal
    )


    if last.buy_signal:


        if in_buy_window():


            if current_position()==0:

                place_buy_order()


            else:

                print(
                    "Position exists. Ignoring signal."
                )


        else:

            print(
                "Outside Pine buy window"
            )


# ============================================================
# MAIN BOT LOOP
# ============================================================


def run_bot():

    connect_ib()


    print(
        "SATS BOT RUNNING"
    )


    last_candle=None


    while True:


        try:


            df=get_history()


            if df is not None:


                current_candle = df.iloc[-1].datetime


                if current_candle != last_candle:


                    last_candle=current_candle


                    print(
                        "\nNEW CANDLE CLOSED"
                    )


                    check_signal()



            ib.sleep(5)



        except Exception as e:


            print(
                "ERROR:",
                e
            )

            ib.sleep(10)


# ============================================================
# START
# ============================================================


if __name__=="__main__":

    run_bot()