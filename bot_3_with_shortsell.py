# ============================================================
# GOEL'S SUPER INDICATOR IBKR BOT - FINAL
#
# Strategy:
# FINAL BUY / FINAL SELL ONLY
#
# Entry:
# FINAL BUY signal
#
# Exit:
# 2 x ATR PROFIT TARGET
# FINAL SELL SIGNAL
#
# No Stop Loss
# No Trailing Stop
#
# Capital:
# $10,000
#
# Trading:
# 6:30 AM - 12:00 PM PST
#
# IBKR:
# Paper / Live compatible
# ============================================================


from ib_insync import (
    IB,
    Stock,
    MarketOrder,
    LimitOrder,
    util
)

import pandas as pd
import numpy as np
import datetime
import time
import pytz
import csv
import os
import winsound

# ============================================================
# CONFIGURATION
# ============================================================


IB_HOST = "127.0.0.1"
IB_PORT = 7497
CLIENT_ID = 6


# 1 = Live
# 2 = Frozen
# 3 = Delayed
MARKET_DATA_TYPE = 1


# ----------------------------
# ACCOUNT
# ----------------------------

CAPITAL = 10000

ONE_POSITION_ONLY = True
ALLOW_SHORT_SELLING = True   # set False any time to instantly revert to long-only behavior

# ----------------------------
# SYMBOLS
# ----------------------------

SYMBOLS = [
    "AMZN",   # Semiconductor / AI
    "MSFT",   # Technology / Software
    "TSLA",   # Consumer / EV / High volatility
    "MA",    # Financials
    "LLY",    # Healthcare
    "CVX",    # Energy
]


EXCHANGE = "SMART"
CURRENCY = "USD"



# ----------------------------
# TRADING TIME PST
# ----------------------------


TIMEZONE = "America/Vancouver"


START_HOUR = 6
START_MINUTE = 30


END_HOUR = 12
END_MINUTE = 0



# ----------------------------
# CANDLE SETTINGS
# ----------------------------


TIMEFRAME = "2 mins"

HISTORY_DURATION = "10 D"

HISTORY_BARS = 500



# ----------------------------
# PROFIT TARGET
# ----------------------------


ATR_MULTIPLIER = 1



# ----------------------------
# EXIT RULES
# ----------------------------


USE_STOP_LOSS = True
STOP_LOSS_PCT = 0.05   # 5% adverse move from entry, direction-aware
USE_TRAILING_STOP = False

USE_SIGNAL_EXIT = True



# ----------------------------
# ORDER
# ----------------------------


ORDER_TYPE = "MKT"


CHECK_INTERVAL = 5



# ----------------------------
# MODE
# ----------------------------


LIVE_TRADING = False



# ----------------------------
# FILES
# ----------------------------


TRADE_LOG = "goel_trade_history.csv"


def play_trade_alert(side):
    try:
        winsound.Beep(1200, 400) if side.upper() == 'BUY' else winsound.Beep(600, 400)
    except Exception:
        pass


# ============================================================
# IBKR CONNECTION
# ============================================================


# ============================================================
# IBKR CONNECTION
# ============================================================


class IBKRConnection:


    def __init__(self):

        self.ib = IB()



    def connect(self):

        try:

            print("\nConnecting to IBKR...")


            self.ib.connect(
                IB_HOST,
                IB_PORT,
                clientId=CLIENT_ID
            )


            print(
                "Connected:",
                self.ib.isConnected()
            )


            self.ib.reqMarketDataType(
                MARKET_DATA_TYPE
            )


            print(
                "Market data type:",
                MARKET_DATA_TYPE
            )


            print(
                "Account:",
                self.ib.managedAccounts()
            )


            return True



        except Exception as e:


            print(
                "IBKR connection failed:",
                e
            )


            return False




    def disconnect(self):


        if self.ib.isConnected():

            self.ib.disconnect()

            print(
                "IBKR disconnected"
            )




# ============================================================
# TIME MANAGER
# ============================================================


class TimeManager:



    @staticmethod
    def trading_time():


        tz = pytz.timezone(
            TIMEZONE
        )


        now = datetime.datetime.now(
            tz
        )


        current = (
            now.hour * 60
            +
            now.minute
        )


        start = (
            START_HOUR * 60
            +
            START_MINUTE
        )


        end = (
            END_HOUR * 60
            +
            END_MINUTE
        )


        return (
            start
            <=
            current
            <=
            end
        )



    @staticmethod
    def now():


        tz = pytz.timezone(
            TIMEZONE
        )

        return datetime.datetime.now(
            tz
        )


# --- HELPER FUNCTIONS (Place these at the very bottom of bot_3.py) ---

def print_status(symbol, price, signal):
    print(f"🔍 [{symbol}] Price: ${price:.2f} | Score: {signal['confirmation']}/10 | Buy: {signal['buy']} | Sell: {signal['sell']} | ATR: ${signal['atr']:.2f} | Time: {datetime.datetime.now().strftime('%H:%M:%S')}")


def print_position_status(symbol, entry, current_price, peak_price, qty, direction='LONG'):
    if direction == 'LONG':
        pnl_per_share = current_price - entry
    else:
        pnl_per_share = entry - current_price
    pnl_total = pnl_per_share * qty
    pnl_percent = (pnl_per_share / entry) * 100 if entry > 0 else 0
    print(f"⏳ [{symbol}] {direction} | Qty: {qty} shares | Entry: ${entry:.2f} | Now: ${current_price:.2f} | Peak: ${peak_price:.2f} | PnL: {pnl_percent:.2f}% (${pnl_total:.2f})")


# END PART 1
# ============================================================
# ============================================================
# MARKET DATA ENGINE
# ============================================================


class MarketData:
    def last_price(self):

        if self.df.empty:
            return None

        return float(
            self.df.iloc[-1]["close"]
        )

    def __init__(self, ib, symbol):

        self.ib = ib

        self.symbol = symbol

        self.contract = Stock(
            symbol,
            EXCHANGE,
            CURRENCY
        )

        self.df = pd.DataFrame()



    def qualify(self):

        try:

            self.ib.qualifyContracts(
                self.contract
            )

            print(
                self.symbol,
                "qualified"
            )

            return True


        except Exception as e:

            print(
                "Qualification error:",
                e
            )

            return False

    def load_history(self):
        try:
            # keepUpToDate=True streams live updates directly into the dataframe for 2-min bars
            self.bars = self.ib.reqHistoricalData(
                self.contract,
                endDateTime="",
                durationStr=HISTORY_DURATION,
                barSizeSetting=TIMEFRAME,
                whatToShow="TRADES",
                useRTH=False,
                formatDate=1,
                keepUpToDate=True
            )

            self.bars.updateEvent += self.update_bar_history

            self.df = util.df(self.bars)
            if len(self.df) > HISTORY_BARS:
                self.df = self.df.tail(HISTORY_BARS).reset_index(drop=True)

            if self.df is None or self.df.empty:
                print(self.symbol, "NO HISTORICAL DATA")
                return pd.DataFrame()

            print(self.symbol, "bars loaded & streaming:", len(self.df))
            return self.df

        except Exception as e:
            print("History error:", e)
            return None

    def realtime(self):
        # Handled natively via keepUpToDate in load_history
        pass

    def update_bar_history(self, bars, hasNewBar):
        self.df = util.df(bars)
        if len(self.df) > HISTORY_BARS:
            self.df = self.df.tail(HISTORY_BARS).reset_index(drop=True)




    def data(self):

        return self.df.copy()






# ============================================================
# INDICATOR ENGINE
# ============================================================


class Indicators:



    def __init__(self, df):

        self.df = df.copy()





    def ema(
        self,
        length
    ):

        return (

            self.df["close"]

            .ewm(
                span=length,
                adjust=False
            )

            .mean()

        )





    def atr(
        self,
        length=14
    ):


        high = self.df["high"]

        low = self.df["low"]

        close = self.df["close"]



        tr1 = high - low


        tr2 = abs(
            high - close.shift()
        )


        tr3 = abs(
            low - close.shift()
        )



        tr = pd.concat(

            [

                tr1,

                tr2,

                tr3

            ],

            axis=1

        ).max(axis=1)



        return (

            tr

            .rolling(length)

            .mean()

        )





    def rsi(
        self,
        length=14
    ):


        delta = (

            self.df["close"]

            .diff()

        )


        gain = delta.clip(
            lower=0
        )


        loss = (

            -delta.clip(
                upper=0
            )

        )



        avg_gain = (

            gain

            .rolling(length)

            .mean()

        )


        avg_loss = (

            loss

            .rolling(length)

            .mean()

        )



        rs = (

            avg_gain /

            avg_loss

        )


        return (

            100 -

            (

                100 /

                (1 + rs)

            )

        )





    def macd(self):


        fast = (

            self.df["close"]

            .ewm(
                span=12,
                adjust=False
            )

            .mean()

        )


        slow = (

            self.df["close"]

            .ewm(
                span=26,
                adjust=False
            )

            .mean()

        )


        macd = fast - slow


        signal = (

            macd

            .ewm(
                span=9,
                adjust=False
            )

            .mean()

        )


        hist = macd - signal



        return macd, signal, hist





    def vwap(self):


        pv = (

            self.df["close"]

            *

            self.df["volume"]

        )


        return (

            pv.cumsum()

            /

            self.df["volume"]

            .cumsum()

        )





    def obv(self):


        direction = np.sign(

            self.df["close"]

            .diff()

        )


        return (

            direction

            *

            self.df["volume"]

        ).cumsum()





    def bb_width(self):


        basis = (

            self.df["close"]

            .rolling(20)

            .mean()

        )


        dev = (

            self.df["close"]

            .rolling(20)

            .std()

            *

            2

        )


        upper = basis + dev

        lower = basis - dev



        return (

            upper - lower

        ) / basis





    def mfi(
        self,
        length=14
    ):


        typical = (

            self.df["high"]

            +

            self.df["low"]

            +

            self.df["close"]

        ) / 3



        money = (

            typical

            *

            self.df["volume"]

        )



        positive = money.where(

            typical.diff() > 0,

            0

        )


        negative = money.where(

            typical.diff() < 0,

            0

        )



        ratio = (

            positive

            .rolling(length)

            .sum()

            /

            negative

            .rolling(length)

            .sum()

        )


        return (

            100 -

            (

                100 /

                (1 + ratio)

            )

        )





# ============================================================
# END PART 2
# ============================================================
# ============================================================
# SIGNAL ENGINE
#
# FINAL BUY / FINAL SELL ONLY
#
# Layers:
#
# 1. Dr David Paul System
# 2. Confirmation Score
# 3. TTM Squeeze Momentum
# 4. Choppiness Filter
# 5. VWAP Filter
#
# Output:
# finalBuy
# finalSell
# ATR
#
# ============================================================


class SignalEngine:
    def __init__(self, df):
        self.df = df.copy()
        self.ind = Indicators(self.df)

    def calculate(self):
        df = self.df

        if len(df) < 100:
            return {
                "buy": False,
                "sell": False,
                "atr": None,
                "confirmation": 0
            }

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # ====================================================
        # PART 1 — DR DAVID PAUL SYSTEM & 10-POINT SCORE
        # ====================================================

        emaFast = self.ind.ema(13)
        emaSlow = self.ind.ema(34)
        emaTrend = self.ind.ema(150)

        bullTrend = emaFast.iloc[-1] > emaSlow.iloc[-1]
        bearTrend = emaFast.iloc[-1] < emaSlow.iloc[-1]
        aboveTrend = close.iloc[-1] > emaTrend.iloc[-1]

        # F1 Trend Score (max 2)
        trendScore = 2 if (bullTrend and aboveTrend) else (1 if (bullTrend or aboveTrend) else 0)

        # F2 EPS / Momentum proxy (max 1)
        roc1 = close.diff(12)
        roc2 = close.diff(24)
        epsSmooth = (roc1 - roc2).ewm(span=6, adjust=False).mean()
        epsScore = 1 if epsSmooth.iloc[-1] > 1.5 else 0

        # F3 Relative Strength proxy (max 1)
        stockPerf = close / close.shift(30)
        # Using rolling mean proxy for benchmark comparison if standalone
        rsRatio = stockPerf / stockPerf.rolling(30).mean()
        rsScore = 1 if rsRatio.iloc[-1] >= 1.03 else 0

        # F4 Volume surge (max 1)
        volMA = volume.rolling(14).mean()
        volScore = 1 if volume.iloc[-1] >= volMA.iloc[-1] * 1.75 else 0

        # F5 Market regime (max 1)
        regimeEMA = close.ewm(span=50, adjust=False).mean()
        bullRegime = close.iloc[-1] > regimeEMA.iloc[-1]
        bearRegime = close.iloc[-1] < regimeEMA.iloc[-1]
        regimeScore = 1 if bullRegime else 0

        # F6 RSI (max 1)
        rsi = self.ind.rsi(14)
        rsiScore = 1 if (50 < rsi.iloc[-1] < 75) else 0

        # F7 Stochastic proxy (max 1)
        stochK = self.ind.rsi(14)  # Stoch alignment proxy
        stochScore = 1 if (50 < stochK.iloc[-1] < 80) else 0

        # F8 MACD histogram (max 1)
        macd, signal, hist = self.ind.macd()
        macdBull = hist.iloc[-1] > 0 and hist.iloc[-1] > hist.iloc[-2]
        macdBear = hist.iloc[-1] < 0 and hist.iloc[-1] < hist.iloc[-2]
        macdScore = 1 if macdBull else 0

        # F9 VWAP (max 1)
        vwap = self.ind.vwap()
        aboveVWAP = close.iloc[-1] > vwap.iloc[-1]
        vwapScore = 1 if aboveVWAP else 0

        # F10 ADX trend strength proxy (max 1)
        adxScore = 1 if abs(close.iloc[-1] - emaSlow.iloc[-1]) > self.ind.atr(14).iloc[-1] else 0

        # Total Score (0-10 matching Pine Script)
        ddTotalScore = (
                trendScore + epsScore + rsScore + volScore +
                regimeScore + rsiScore + stochScore + macdScore +
                vwapScore + adxScore
        )

        # ====================================================
        # CROSSOVER LOOKBACK (Matching Pine Script ta.barssince)
        # ====================================================
        crossover = (emaFast > emaSlow) & (emaFast.shift(1) <= emaSlow.shift(1))
        crossunder = (emaFast < emaSlow) & (emaFast.shift(1) >= emaSlow.shift(1))

        recentCross = crossover.tail(10).any()
        recentUnder = crossunder.tail(10).any()

        buySignal = (ddTotalScore >= 6) and bullTrend and bullRegime and recentCross
        sellSignal = (ddTotalScore <= 4) and bearTrend and bearRegime and recentUnder

        # ====================================================
        # TTM SQUEEZE & CHOPPINESS (Layers 3 & 4)
        # ====================================================
        length = 20
        highest = high.rolling(length).max()
        lowest = low.rolling(length).min()

        sqMom = (close - ((highest + lowest) / 2)).rolling(length).mean()
        sqBullRelease = sqMom.iloc[-1] > 0 and sqMom.iloc[-1] > sqMom.iloc[-2]
        sqBearRelease = sqMom.iloc[-1] < 0 and sqMom.iloc[-1] < sqMom.iloc[-2]

        # Choppiness Index
        atrSum = self.ind.atr(1).rolling(14).sum().iloc[-1]
        priceRange = (high.rolling(14).max() - low.rolling(14).min()).iloc[-1]

        choppiness = 0.0
        if priceRange > 0:
            choppiness = 100 * np.log10(atrSum / priceRange) / np.log10(14)

        chopTrending = choppiness < 38.2

        # ====================================================
        # FINAL DECISION (All Layers Combined)
        # ====================================================
        finalBuy = buySignal and sqBullRelease and chopTrending and aboveVWAP
        finalSell = sellSignal and sqBearRelease and chopTrending and (not aboveVWAP)

        atr = self.ind.atr(14).iloc[-1]

        return {
            "buy": bool(finalBuy),
            "sell": bool(finalSell),
            "atr": float(atr) if not np.isnan(atr) else 0.0,
            "confirmation": int(ddTotalScore)
        }



# ============================================================
# END PART 3
# ============================================================
# ============================================================
# ORDER ENGINE
#
# Rules:
#
# BUY:
# FINAL BUY ONLY
#
# SELL:
# FINAL SELL ONLY
# OR
# 2 x ATR PROFIT TARGET
#
# No Stop Loss
# No Trailing Stop
#
# ============================================================


class OrderEngine:



    def __init__(self, ib):

        self.ib = ib




    def position(self, symbol):


        positions = self.ib.positions()


        for p in positions:


            if p.contract.symbol == symbol:


                if p.position != 0:

                    return p.position



        return 0






    def calculate_quantity(self, price):


        qty = int(

            CAPITAL /

            price

        )


        return max(
            qty,
            1
        )

    def sell(self, contract, qty):
        order = MarketOrder('SELL', qty, tif='DAY')
        trade = self.ib.placeOrder(contract, order)
        trade.statusEvent += lambda t: play_trade_alert('SELL') if t.orderStatus.status == 'Filled' else None
        return trade

    def buy(self, contract, qty):
        order = MarketOrder('BUY', qty, tif='DAY')
        trade = self.ib.placeOrder(contract, order)
        trade.statusEvent += lambda t: play_trade_alert('BUY') if t.orderStatus.status == 'Filled' else None
        return trade




# ============================================================
# POSITION MANAGER
# ============================================================


class PositionManager:

    def __init__(self):
        self.symbol = None
        self.qty = 0
        self.direction = None   # 'LONG' or 'SHORT'
        self.entry_price = None
        self.target_price = None
        self.stop_price = None
        self.atr = None
        self.peak_price = None   # best price seen: highest for LONG, lowest for SHORT

    def open_position(self, symbol, qty, entry, atr, direction='LONG'):
        self.symbol = symbol
        self.qty = qty
        self.direction = direction
        self.entry_price = entry
        self.atr = atr
        self.peak_price = entry

        if direction == 'LONG':
            self.target_price = entry + (atr * ATR_MULTIPLIER)
            self.stop_price = entry * (1 - STOP_LOSS_PCT)
        else:
            self.target_price = entry - (atr * ATR_MULTIPLIER)
            self.stop_price = entry * (1 + STOP_LOSS_PCT)

        print()
        print("POSITION OPEN")
        print("Symbol:", symbol)
        print("Direction:", direction)
        print("Qty:", qty, "shares")
        print("Entry:", entry)
        print("ATR Target:", self.target_price)
        print("Stop Loss:", round(self.stop_price, 2), f"({STOP_LOSS_PCT*100:.0f}%)")

    def update_peak(self, current_price):
        if self.peak_price is None:
            return
        if self.direction == 'LONG' and current_price > self.peak_price:
            self.peak_price = current_price
        elif self.direction == 'SHORT' and current_price < self.peak_price:
            self.peak_price = current_price

    def close_position(self):
        self.symbol = None
        self.qty = 0
        self.direction = None
        self.entry_price = None
        self.target_price = None
        self.stop_price = None
        self.atr = None
        self.peak_price = None

    def active(self):
        return self.symbol is not None and self.qty > 0

    def target_hit(self, price):
        if self.target_price is None:
            return False
        if self.direction == 'LONG':
            return price >= self.target_price
        else:
            return price <= self.target_price

    def stop_hit(self, price):
        if not USE_STOP_LOSS or self.stop_price is None:
            return False
        if self.direction == 'LONG':
            return price <= self.stop_price
        else:
            return price >= self.stop_price


# ============================================================
# TRADE LOGGER
# ============================================================


class TradeLogger:



    def __init__(self):


        if not os.path.exists(
            TRADE_LOG
        ):


            with open(
                TRADE_LOG,
                "w",
                newline=""
            ) as f:


                writer = csv.writer(f)


                writer.writerow(

                    [

                        "time",

                        "symbol",

                        "side",

                        "qty",

                        "price",

                        "reason"

                    ]

                )






    def log(
        self,
        symbol,
        side,
        qty,
        price,
        reason
    ):


        with open(
            TRADE_LOG,
            "a",
            newline=""
        ) as f:


            writer = csv.writer(f)


            writer.writerow(

                [

                    datetime.datetime.now(),

                    symbol,

                    side,

                    qty,

                    price,

                    reason

                ]

            )



        print(

            "LOGGED:",

            symbol,

            side,

            price,

            reason

        )






# ============================================================
# END PART 4
# ============================================================
# ============================================================
# MAIN BOT CONTROLLER
#
# Connects:
#
# IBKR
# Market Data
# Signal Engine
# Order Engine
# Position Manager
# Logger
#
# ============================================================


class GoelBot:



    def __init__(self):


        self.connection = IBKRConnection()


        self.ib = None


        self.market = {}


        self.order = None


        self.position = PositionManager()


        self.logger = TradeLogger()

        self.daily_realized_pnl = 0.0
        self.daily_trade_count = 0
        self.daily_date = None


    def reset_daily_counters_if_new_day(self):
        today = TimeManager.now().date()
        if self.daily_date != today:
            self.daily_date = today
            self.daily_realized_pnl = 0.0
            self.daily_trade_count = 0


    def print_daily_pnl(self):
        unrealized = 0.0
        if self.position.active():
            data = self.market.get(self.position.symbol)
            now_price = data.last_price() if data else None
            if now_price is not None and self.position.entry_price is not None:
                unrealized = (now_price - self.position.entry_price) * self.position.qty
        day_total = self.daily_realized_pnl + unrealized
        sign = "+" if day_total >= 0 else ""
        print(f"💰 TODAY | Realized: ${self.daily_realized_pnl:.2f} ({self.daily_trade_count} trades) | Unrealized: ${unrealized:.2f} | TOTAL: {sign}${day_total:.2f}")


    def sync_existing_state(self):
        print()
        print("=" * 60)
        print(" SYNCING EXISTING STATE FROM IBKR")
        print("=" * 60)

        for pos in self.ib.positions():
            symbol = pos.contract.symbol
            if symbol in SYMBOLS and pos.position != 0:
                data = self.market.get(symbol)
                atr_value = 0.0
                if data is not None:
                    df = data.data()
                    if len(df) >= 100:
                        sig = SignalEngine(df).calculate()
                        atr_value = sig["atr"] or 0.0
                self.position.open_position(
                    symbol=symbol,
                    qty=int(pos.position),
                    entry=pos.avgCost,
                    atr=atr_value if atr_value else (pos.avgCost * 0.01)
                )
                print(f"SYNCED POSITION: {int(pos.position)} shares of {symbol} @ ${pos.avgCost:.2f}")
                break

        relevant = [t for t in self.ib.openTrades() if t.contract.symbol in SYMBOLS and t.isActive()]
        if relevant:
            print(f"WARNING: {len(relevant)} open order(s) still resting at IBKR from before restart:")
            for t in relevant:
                print(f"   - {t.contract.symbol}: {t.order.action} {t.order.totalQuantity} ({t.orderStatus.status})")
            print("Review these manually before letting the bot trade.")
        else:
            print("No leftover open orders found.")
        print("=" * 60)
        print()


    def start(self):
        connected = self.connection.connect()



        if not connected:


            return



        self.ib = self.connection.ib



        self.order = OrderEngine(
            self.ib
        )



        print()

        print(
            "================================"
        )

        print(
            " GOEL SUPER INDICATOR BOT STARTED"
        )

        print(
            " FINAL BUY / FINAL SELL ONLY"
        )

        print(
            "================================"
        )





        # Load symbols

        # Load all symbols
        for symbol in SYMBOLS:

            data = MarketData(
                self.ib,
                symbol
            )

            if data.qualify():
                data.load_history()
                data.realtime()

                self.market[symbol] = data

        # Sync any existing IBKR position
        self.sync_existing_state()

        # Start the trading loop
        self.run()
    def run(self):
        while True:
            try:
                self.ib.sleep(CHECK_INTERVAL)

                self.reset_daily_counters_if_new_day()

                inside_window = TimeManager.trading_time()

                if not inside_window and not self.position.active():
                    print("Outside trading hours. No open position — standing by.")
                    self.print_daily_pnl()
                    print("-" * 60)
                    continue

                if not inside_window and self.position.active():
                    print("Outside entry window — no new entries, but still managing open position.")

                if self.position.active():
                    symbol = self.position.symbol
                    direction = self.position.direction
                    data = self.market[symbol]
                    price = data.last_price()

                    if price is not None:
                        self.position.update_peak(price)

                        print_position_status(
                            symbol,
                            self.position.entry_price,
                            price,
                            self.position.peak_price,
                            self.position.qty,
                            direction
                        )

                        closing_action = 'SELL' if direction == 'LONG' else 'BUY'

                        if self.position.stop_hit(price):
                            print(f"🛑 STOP LOSS HIT ({STOP_LOSS_PCT * 100:.0f}%) — exiting.")
                            if closing_action == 'SELL':
                                self.order.sell(data.contract, self.position.qty)
                            else:
                                self.order.buy(data.contract, self.position.qty)
                            self.logger.log(symbol, closing_action, self.position.qty, price, "STOP LOSS")
                            pnl = (price - self.position.entry_price) if direction == 'LONG' else (
                                        self.position.entry_price - price)
                            self.daily_realized_pnl += pnl * self.position.qty
                            self.daily_trade_count += 1
                            self.position.close_position()
                            self.print_daily_pnl()
                            print("-" * 60)
                            continue

                        if self.position.target_hit(price):
                            print("ATR TARGET HIT")
                            if closing_action == 'SELL':
                                self.order.sell(data.contract, self.position.qty)
                            else:
                                self.order.buy(data.contract, self.position.qty)
                            self.logger.log(symbol, closing_action, self.position.qty, price, "2 ATR TARGET")
                            pnl = (price - self.position.entry_price) if direction == 'LONG' else (self.position.entry_price - price)
                            self.daily_realized_pnl += pnl * self.position.qty
                            self.daily_trade_count += 1
                            self.position.close_position()
                            self.print_daily_pnl()
                            print("-" * 60)
                            continue

                        signal = SignalEngine(data.data()).calculate()
                        # LONG closes on a FINAL SELL signal; SHORT covers on a FINAL BUY signal
                        opposite_signal = signal["sell"] if direction == 'LONG' else signal["buy"]
                        if opposite_signal:
                            print("FINAL OPPOSITE SIGNAL — CLOSING")
                            if closing_action == 'SELL':
                                self.order.sell(data.contract, self.position.qty)
                            else:
                                self.order.buy(data.contract, self.position.qty)
                            self.logger.log(symbol, closing_action, self.position.qty, price, "FINAL SIGNAL EXIT")
                            pnl = (price - self.position.entry_price) if direction == 'LONG' else (self.position.entry_price - price)
                            self.daily_realized_pnl += pnl * self.position.qty
                            self.daily_trade_count += 1
                            self.position.close_position()

                    self.print_daily_pnl()
                    print("-" * 60)
                    continue

                if not inside_window:
                    self.print_daily_pnl()
                    print("-" * 60)
                    continue

                for symbol, data in self.market.items():
                    df = data.data()
                    if len(df) < 100:
                        continue

                    engine = SignalEngine(df)
                    signal = engine.calculate()
                    price = data.last_price()

                    print_status(symbol, price, signal)

                    if signal["buy"] or (ALLOW_SHORT_SELLING and signal["sell"]):
                        if self.position.active():
                            break

                        price = data.last_price()
                        if price is None:
                            continue

                        qty = self.order.calculate_quantity(price)

                        if signal["buy"]:
                            trade = self.order.buy(data.contract, qty)
                            direction = 'LONG'
                            action_label = "FINAL BUY"
                        else:
                            trade = self.order.sell(data.contract, qty)
                            direction = 'SHORT'
                            action_label = "FINAL SELL (SHORT ENTRY)"

                        if trade:
                            self.ib.sleep(2)
                            fill_price = price

                            self.position.open_position(symbol, qty, fill_price, signal["atr"], direction)
                            self.logger.log(symbol, direction, qty, fill_price, action_label)
                        break

                self.print_daily_pnl()
                print("-" * 60)

            except Exception as e:
                print("BOT ERROR:", e)
                self.ib.sleep(10)

# ============================================================
# START BOT
# ============================================================


if __name__ == "__main__":


    bot = GoelBot()


    bot.start()



# ============================================================
# END OF GOEL SUPER INDICATOR IBKR BOT
# ============================================================