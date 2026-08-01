import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from streamlit_autorefresh import st_autorefresh
from google import genai
from typing import Optional, Tuple, Dict, Any
from google.genai import types
# import pandas_ta as ta  # <-- Ensure this is imported as 'ta'
import faulthandler
faulthandler.enable()

MAX_WORKERS = 16
WATCHLIST_PATH = "watchlist_test.csv"
NASDAQ_SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks"
NASDAQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}
S8_FALLBACK_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "AVGO",
    "JPM", "V", "MA", "UNH", "XOM", "PG", "HD", "COST", "MRK", "ABBV", "PEP"
]

def shared_load_watchlist(path: str = WATCHLIST_PATH) -> pd.DataFrame:
    if not os.path.exists(path):
        df = pd.DataFrame(columns=["Yahoo Ticker", "Company Name"])
        df.to_csv(path, index=False)
        return df
    df = pd.read_csv(path)
    df["Yahoo Ticker"] = df["Yahoo Ticker"].astype(str).str.strip().str.upper()
    if "Company Name" not in df.columns:
        df["Company Name"] = df["Yahoo Ticker"]
    else:
        df["Company Name"] = df["Company Name"].astype(str).str.strip()
    return df[["Yahoo Ticker", "Company Name"]].drop_duplicates("Yahoo Ticker")


def shared_save_watchlist(tickers: list, path: str = WATCHLIST_PATH):
    ticker_to_name = {}
    if os.path.exists(path):
        try:
            old = pd.read_csv(path)
            for _, r in old.iterrows():
                t = str(r.get("Yahoo Ticker", "")).strip().upper()
                n = str(r.get("Company Name", t)).strip()
                if t:
                    ticker_to_name[t] = n
        except Exception:
            pass
    rows = [{"Yahoo Ticker": t.strip().upper(), "Company Name": ticker_to_name.get(t.strip().upper(), t.strip().upper())}
            for t in tickers if t.strip()]
    pd.DataFrame(rows).drop_duplicates("Yahoo Ticker").to_csv(path, index=False)


def s1_rsi(series: pd.Series, period: int = 14, method: str = "sma") -> pd.Series:
    series = series.astype(float)
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    if method == "wilder":
        avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    else:
        avg_gain = gain.rolling(period, min_periods=period).mean()
        avg_loss = loss.rolling(period, min_periods=period).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return 100 - (100 / (1 + rs))


@st.cache_data(ttl=3600, show_spinner=False)
def s4n_fetch_earnings(ticker: str):
    try:
        return yf.Ticker(ticker).earnings_dates
    except Exception:
        return None


# ==================================================================
# LIVE UNIVERSES
# ==================================================================
@st.cache_data(ttl=6*60*60, show_spinner=False)
def s8_get_nasdaq_universe() -> pd.DataFrame:
    """Live large-cap stock universe with Market Cap."""
    params = {"tableonly": "true", "limit": 10000, "offset": 0, "download": "true"}
    try:
        r = requests.get(NASDAQ_SCREENER_URL, headers=NASDAQ_HEADERS, params=params, timeout=20)
        r.raise_for_status()
        rows = r.json()["data"]["rows"]
        df = pd.DataFrame(rows)
        df["marketCap"] = pd.to_numeric(df["marketCap"], errors="coerce")
        df = df.dropna(subset=["marketCap"])
        df = df.rename(columns={"symbol": "Ticker", "name": "Name", "marketCap": "MarketCap", "sector": "Sector"})
        df["Ticker"] = df["Ticker"].str.replace(".", "-", regex=False).str.strip().str.upper()
        keep = ["Ticker", "Name", "MarketCap"]
        if "Sector" in df.columns:
            df["Sector"] = df["Sector"].fillna("Unknown").replace("", "Unknown")
            keep.append("Sector")
        return df[keep].drop_duplicates("Ticker").reset_index(drop=True)
    except Exception as e:
        st.warning(f"Nasdaq screener failed ({e}). Using fallback.")
        return pd.DataFrame({
            "Ticker": S8_FALLBACK_TICKERS,
            "Name": S8_FALLBACK_TICKERS,
            "MarketCap": np.nan,
            "Sector": "Unknown"
        })


@st.cache_data(ttl=12*60*60, show_spinner=False)
def s8_get_live_etf_universe() -> pd.DataFrame:
    """Fully live – all ETFs from official Nasdaq Trader files (updated daily)."""
    urls = [
        "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
    ]
    frames = []
    for url in urls:
        try:
            df = pd.read_csv(url, sep="|")
            # Remove Nasdaq footer
            df = df[df["Symbol"].notna()]
            df = df[~df["Symbol"].astype(str).str.contains("File Creation", na=False)]
            if "ETF" in df.columns:
                df = df[df["ETF"] == "Y"]
            frames.append(df)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame(columns=["Ticker", "Name", "AUM_B", "Sector"])

    etfs = pd.concat(frames, ignore_index=True)
    etfs = etfs.rename(columns={"Symbol": "Ticker", "Security Name": "Name"})
    etfs["Ticker"] = etfs["Ticker"].astype(str).str.strip().str.upper()
    etfs = etfs.drop_duplicates(subset="Ticker")
    etfs["Name"] = etfs["Name"].fillna(etfs["Ticker"])
    etfs["Sector"] = "ETF"
    etfs["AUM_B"] = np.nan          # will be filled later only for shortlist
    return etfs[["Ticker", "Name", "AUM_B", "Sector"]].reset_index(drop=True)


# ==================================================================
# Price data (fast)
# ==================================================================
@st.cache_data(ttl=15*60, show_spinner=False)
def s8_fetch_price_history(tickers: tuple, period: str = "1y") -> dict:
    all_data = {}
    tickers = list(tickers)
    batch_size = 200          # larger batches = faster

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        try:
            data = yf.download(
                batch, period=period, interval="1d",
                group_by="ticker", threads=True, progress=False, auto_adjust=True
            )
        except Exception:
            continue
        if data is None or data.empty:
            continue

        if len(batch) == 1:
            t = batch[0]
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            all_data[t] = data.dropna(how="all")
        else:
            if isinstance(data.columns, pd.MultiIndex):
                for t in batch:
                    try:
                        df_t = data[t].dropna(how="all")
                        if not df_t.empty and "Close" in df_t.columns:
                            all_data[t] = df_t
                    except Exception:
                        pass
    return all_data


@st.cache_data(ttl=15*60, show_spinner=False)
def s8_fetch_spy_history(period: str = "1y") -> pd.DataFrame:
    df = yf.download("SPY", period=period, interval="1d", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


# ==================================================================
# Technical helpers
# ==================================================================
def s8_pct_return(close: pd.Series, window: int) -> float:
    if len(close) < window + 1:
        return np.nan
    return float((close.iloc[-1] / close.iloc[-window] - 1) * 100)


def s8_volume_declining(vol: pd.Series, recent: int = 10, prior: int = 10) -> Optional[bool]:
    if vol is None or len(vol) < recent + prior:
        return None
    recent_avg = vol.tail(recent).mean()
    prior_avg = vol.iloc[-(recent+prior):-recent].mean()
    if pd.isna(recent_avg) or pd.isna(prior_avg) or prior_avg == 0:
        return None
    return bool(recent_avg < prior_avg)


def s8_avg_volume(vol: pd.Series, days: int = 20) -> float:
    if vol is None or len(vol) < days:
        return 0.0
    return float(vol.tail(days).mean())


def s8_screen_ticker(ticker: str, df: pd.DataFrame, spy_ret_63d: float, rsi_method: str = "sma") -> Optional[Dict]:
    if df is None or df.empty or "Close" not in df.columns or len(df) < 200:
        return None
    close = df["Close"].dropna()
    if len(close) < 200:
        return None

    last = float(close.iloc[-1])
    sma200 = float(close.rolling(200).mean().iloc[-1])
    high_3mo = float(close.tail(63).max())
    pct_off = (last / high_3mo - 1) * 100
    dist_sma = (last / sma200 - 1) * 100

    rsi_s = s1_rsi(close, 14, method=rsi_method)
    rsi = float(rsi_s.iloc[-1]) if not rsi_s.empty else np.nan

    ret63 = s8_pct_return(close, 63)
    rs = ret63 - spy_ret_63d if not np.isnan(ret63) and not np.isnan(spy_ret_63d) else np.nan

    vol = df["Volume"] if "Volume" in df.columns else None
    vol_decl = s8_volume_declining(vol)
    avg_vol = s8_avg_volume(vol)

    return {
        "Price": round(last, 2),
        "SMA200": round(sma200, 2),
        "AboveSMA200": last > sma200,
        "DistToSMA%": round(dist_sma, 2),
        "3moHigh": round(high_3mo, 2),
        "PctOffHigh": round(pct_off, 2),
        "RSI": round(rsi, 1) if not np.isnan(rsi) else None,
        "RS_vs_SPY": round(rs, 1) if not np.isnan(rs) else None,
        "VolDeclining": vol_decl,
        "AvgVolume": round(avg_vol),
    }


def s8_calculate_score(row: pd.Series) -> int:
    score = 0
    pb = row.get("PctOffHigh", 0)
    if pb <= -12: score += 30
    elif pb <= -8: score += 20
    elif pb <= -5: score += 10

    rsi = row.get("RSI")
    if rsi is not None:
        if 30 <= rsi <= 45: score += 25
        elif 45 < rsi <= 55: score += 15
        elif 25 <= rsi < 30: score += 10

    rs = row.get("RS_vs_SPY")
    if rs is not None:
        if rs >= 8: score += 25
        elif rs >= 3: score += 15
        elif rs >= 0: score += 8

    if row.get("AboveSMA200"): score += 15
    if row.get("VolDeclining") is True: score += 10
    return score


def s8_apply_sector_cap(df: pd.DataFrame, max_per: int, sort_col: str = "RSI") -> pd.DataFrame:
    if "Sector" not in df.columns or df.empty:
        return df
    return (df.sort_values(sort_col)
              .groupby("Sector", group_keys=False)
              .head(max_per)
              .reset_index(drop=True))


def s8_earnings_flag(ticker: str, days: int) -> Tuple[bool, str]:
    try:
        ed = s4n_fetch_earnings(ticker)
        if ed is None or ed.empty:
            return False, "None found"
        idx = ed.index
        now = pd.Timestamp.now(tz=idx.tz) if idx.tz is not None else pd.Timestamp.now()
        upcoming = idx[idx >= now]
        if len(upcoming) == 0:
            return False, "None found"
        d = (upcoming[0] - now).days
        return (True, f"⚠️ In {d}d") if d <= days else (False, f"In {d}d")
    except Exception:
        return False, "Unknown"


def s8_fetch_aum(ticker: str) -> Optional[float]:
    """Fetch AUM in $B – only called on shortlist."""
    try:
        info = yf.Ticker(ticker).info
        assets = info.get("totalAssets")
        if assets and assets > 0:
            return round(assets / 1e9, 2)
    except Exception:
        pass
    return None


# ==================================================================
# STOCK FUNNEL
# ==================================================================
def s8_run_stock_funnel(
    min_cap_b, min_pullback, rsi_low, rsi_high,
    require_sma, min_rs, require_vol, max_sector,
    earn_days, use_scoring, rsi_method, progress_cb=None
):
    stages = {}
    uni = s8_get_nasdaq_universe()
    stages["1. Full universe"] = len(uni)

    capped = uni[uni["MarketCap"] >= min_cap_b * 1e9].copy()
    stages[f"2. MarketCap ≥ ${min_cap_b}B"] = len(capped)
    if capped.empty:
        return pd.DataFrame(), stages

    # drop no-sector
    if "Sector" in capped.columns:
        mask = capped["Sector"].isna() | capped["Sector"].isin(["Unknown", "", "N/A"])
        capped = capped[~mask]
    stages["3. Candidate stocks"] = len(capped)
    if capped.empty:
        return pd.DataFrame(), stages

    tickers = tuple(sorted(capped["Ticker"]))
    if progress_cb: progress_cb(0.15, "Downloading stock prices…")

    prices = s8_fetch_price_history(tickers)
    spy = s8_fetch_spy_history()
    spy_ret = s8_pct_return(spy["Close"].dropna(), 63) if not spy.empty else np.nan

    if progress_cb: progress_cb(0.40, "Screening stocks…")

    meta = capped.set_index("Ticker")
    rows = []

    def _proc(t):
        tech = s8_screen_ticker(t, prices.get(t), spy_ret, rsi_method)
        if not tech: return None
        try:
            m = meta.loc[t]
            return {
                "Ticker": t,
                "Name": m.get("Name", ""),
                "Sector": m.get("Sector", "Unknown"),
                "MarketCap($B)": round(m["MarketCap"]/1e9, 1) if "MarketCap" in m else None,
                **tech
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for fut in as_completed({ex.submit(_proc, t): t for t in tickers}):
            r = fut.result()
            if r: rows.append(r)

    res = pd.DataFrame(rows)
    stages["4. Have 200d history"] = len(res)
    if res.empty:
        return res, stages

    mask = (res["PctOffHigh"] <= -min_pullback) & (res["RSI"] >= rsi_low) & (res["RSI"] <= rsi_high)
    if require_sma: mask &= res["AboveSMA200"]
    if min_rs is not None: mask &= res["RS_vs_SPY"].fillna(-999) >= min_rs
    if require_vol: mask &= res["VolDeclining"].fillna(False)

    filt = res[mask].copy()
    stages["5. Technical filters"] = len(filt)
    if filt.empty:
        return filt, stages

    filt = s8_apply_sector_cap(filt, max_sector)
    stages[f"6. Sector cap ≤{max_sector}"] = len(filt)
    if filt.empty:
        return filt, stages

    if progress_cb: progress_cb(0.75, "Earnings check…")

    emap = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(s8_earnings_flag, t, earn_days): t for t in filt["Ticker"]}
        for fut in as_completed(futs):
            t = futs[fut]
            try: emap[t] = fut.result()
            except: emap[t] = (False, "Unknown")

    filt["EarningsSoon"] = [emap.get(t, (False, "Unknown"))[0] for t in filt["Ticker"]]
    filt["EarningsNote"] = [emap.get(t, (False, "Unknown"))[1] for t in filt["Ticker"]]

    if use_scoring:
        filt["Score"] = filt.apply(s8_calculate_score, axis=1)
        filt = filt.sort_values("Score", ascending=False)
    else:
        filt = filt.sort_values("RSI")

    filt.insert(0, "Rank", range(1, len(filt)+1))
    stages["7. Final shortlist"] = len(filt)
    return filt.reset_index(drop=True), stages


# ==================================================================
# ETF FUNNEL (live + AUM on shortlist only)
# ==================================================================
def s8_run_etf_funnel(
    min_aum_b, min_pullback, rsi_low, rsi_high,
    require_sma, min_rs, require_vol, min_avg_vol,
    use_scoring, rsi_method, progress_cb=None
):
    stages = {}
    uni = s8_get_live_etf_universe()
    stages["1. Live ETF universe"] = len(uni)
    if uni.empty:
        return pd.DataFrame(), stages

    tickers = tuple(uni["Ticker"])
    if progress_cb: progress_cb(0.50, "Downloading ETF prices…")

    prices = s8_fetch_price_history(tickers)
    spy = s8_fetch_spy_history()
    spy_ret = s8_pct_return(spy["Close"].dropna(), 63) if not spy.empty else np.nan

    if progress_cb: progress_cb(0.70, "Screening ETFs…")

    meta = uni.set_index("Ticker")
    rows = []

    def _proc(t):
        tech = s8_screen_ticker(t, prices.get(t), spy_ret, rsi_method)
        if not tech: return None
        # early liquidity filter
        if tech["AvgVolume"] < min_avg_vol:
            return None
        try:
            m = meta.loc[t]
            return {"Ticker": t, "Name": m.get("Name", t), **tech}
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for fut in as_completed({ex.submit(_proc, t): t for t in tickers}):
            r = fut.result()
            if r: rows.append(r)

    res = pd.DataFrame(rows)
    stages["2. Have history + liquidity"] = len(res)
    if res.empty:
        return res, stages

    mask = (res["PctOffHigh"] <= -min_pullback) & (res["RSI"] >= rsi_low) & (res["RSI"] <= rsi_high)
    if require_sma: mask &= res["AboveSMA200"]
    if min_rs is not None: mask &= res["RS_vs_SPY"].fillna(-999) >= min_rs
    if require_vol: mask &= res["VolDeclining"].fillna(False)

    filt = res[mask].copy()
    stages["3. Technical filters"] = len(filt)
    if filt.empty:
        return filt, stages

    # ---- AUM only on shortlist (fast) ----
    if progress_cb: progress_cb(0.85, f"Fetching AUM for {len(filt)} ETFs…")

    aum_map = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(s8_fetch_aum, t): t for t in filt["Ticker"]}
        for fut in as_completed(futs):
            t = futs[fut]
            aum_map[t] = fut.result()

    filt["AUM($B)"] = [aum_map.get(t) for t in filt["Ticker"]]

    # Apply AUM filter (keep rows that meet min OR have no data if you prefer)
    if min_aum_b > 0:
        filt = filt[filt["AUM($B)"].fillna(0) >= min_aum_b]

    stages["4. After AUM filter"] = len(filt)

    if use_scoring and not filt.empty:
        filt["Score"] = filt.apply(s8_calculate_score, axis=1)
        filt = filt.sort_values("Score", ascending=False)
    else:
        filt = filt.sort_values("RSI")

    if not filt.empty:
        filt.insert(0, "Rank", range(1, len(filt)+1))

    stages["5. Final ETF shortlist"] = len(filt)
    return filt.reset_index(drop=True), stages


def s8_row_color(row):
    if row.get("EarningsSoon"):
        return ["background-color:#FFF3CD;color:black"] * len(row)
    return [""] * len(row)


# ==============================================================================
# 1. GLOBAL APP CONFIGURATION & INITIALIZATION (Must be at the absolute top)
# ==============================================================================
st.set_page_config(page_title="Master Trading Suite", layout="wide")
st.title("🎛️ Master Strategy & Scanning Interface")

WATCHLIST_PATH = "watchlist.csv"
REQUIRED_COLS = {"Open", "High", "Low", "Close", "Volume"}
MAX_WORKERS = 8  # tune down if Yahoo Finance starts rate-limiting you


# ==============================================================================
# MARKET CONTEXT (SPY) — cached so it doesn't hit the network every rerun
# ==============================================================================
@st.cache_data(ttl=300, show_spinner=False)
def load_spy_snapshot():
    df = yf.download("SPY", period="1mo", interval="1d", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


spy_data = load_spy_snapshot()
close = spy_data['Close']
if isinstance(close, pd.DataFrame):
    close = close.iloc[:, 0]

if len(close) >= 20:
    spy_price = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    spy_change = spy_price - prev_close
    spy_percent = (spy_change / prev_close) * 100

    mean = close.rolling(window=20).mean()
    std = close.rolling(window=20).std()
    z_score_series = (close - mean) / std
    latest_z_score = float(z_score_series.iloc[-1])

    if latest_z_score < -1.5:
        market_status = "GOOD TIME (Oversold)"
    elif latest_z_score > 1.5:
        market_status = "BAD TIME (Overbought)"
    else:
        market_status = "STABLE"

    st.subheader("Market Context: S&P 500 (SPY)")
    col1, col2, col3 = st.columns(3)
    col1.metric("SPY Price", f"${spy_price:.2f}", f"{spy_change:+.2f} ({spy_percent:+.2f}%)")
    col2.metric("SPY Z-Score", f"{latest_z_score:.2f}")
    col3.info(f"Market Sentiment: {market_status}")
    st.divider()
else:
    st.warning("Gathering market data...")


@st.cache_resource
def s4_get_ai_client():
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            os.environ["GEMINI_API_KEY"] = api_key
            return genai.Client()
        except Exception:
            return None
    return None


# Setup Global Navigation Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🎯 Atharv Swing Scanner (5m/15m)",
    "📈 Goel's Swing Strategy",
    "📊 52-Week High/Low Strategy",
    "🌙 Overnight Gap Screener",
    "Pullback Funnel"
])


# ==============================================================================
# 2. SHARED DATA UTILITIES & ENGINE CONFIGURATIONS
# ==============================================================================
def shared_load_watchlist(path: str = WATCHLIST_PATH) -> pd.DataFrame:
    """Unified CSV Watchlist Loader used by all strategies"""
    if not os.path.exists(path):
        df = pd.DataFrame(columns=["Yahoo Ticker", "Company Name"])
        df.to_csv(path, index=False)
        return df
    df = pd.read_csv(path)
    df["Yahoo Ticker"] = df["Yahoo Ticker"].astype(str).str.strip().str.upper()
    if "Company Name" not in df.columns:
        df["Company Name"] = df["Yahoo Ticker"]
    else:
        df["Company Name"] = df["Company Name"].astype(str).str.strip()
    return df[["Yahoo Ticker", "Company Name"]]


def shared_save_watchlist(watchlist_tickers, path: str = WATCHLIST_PATH):
    """Saves updated tickers back to CSV while safeguarding format"""
    ticker_to_name = {}
    if os.path.exists(path):
        try:
            old_df = pd.read_csv(path)
            for _, r in old_df.iterrows():
                t = str(r.get('Yahoo Ticker', '')).strip().upper()
                n = str(r.get('Company Name', r.get('Yahoo Ticker', ''))).strip()
                if t: ticker_to_name[t] = n
        except:
            pass

    updated_rows = []
    for t in watchlist_tickers:
        t_clean = t.strip().upper()
        if t_clean:
            updated_rows.append({
                "Yahoo Ticker": t_clean,
                "Company Name": ticker_to_name.get(t_clean, t_clean)
            })
    pd.DataFrame(updated_rows).to_csv(path, index=False)


# ==============================================================================
# 3. STRATEGY 1: ATHARV SWING SCANNER UTILITIES
# ==============================================================================
def s1_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    series = series.astype(float)
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return 100 - (100 / (1 + rs))


def s1_compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["RSI14"] = s1_rsi(df["Close"], 14)
    df["VolAvg20"] = df["Volume"].rolling(20).mean()
    return df


def s1_get_last_values(df: pd.DataFrame):
    return {
        "o_last": float(df["Open"].iloc[-1]), "h_last": float(df["High"].iloc[-1]),
        "l_last": float(df["Low"].iloc[-1]), "c_last": float(df["Close"].iloc[-1]),
        "v_last": float(df["Volume"].iloc[-1]), "o_prev": float(df["Open"].iloc[-2]),
        "h_prev": float(df["High"].iloc[-2]), "l_prev": float(df["Low"].iloc[-2]),
        "c_prev": float(df["Close"].iloc[-2]), "ema20_last": float(df["EMA20"].iloc[-1]),
        "ema50_last": float(df["EMA50"].iloc[-1]), "rsi_last": float(df["RSI14"].iloc[-1]),
        "rsi_prev": float(df["RSI14"].iloc[-2]), "vol_avg20": float(df["VolAvg20"].iloc[-1]),
    }


@st.cache_data(ttl=120, show_spinner=False)
def s1_safe_history(ticker: str, interval: str, period: str = "7d") -> pd.DataFrame | None:
    """Cached — intraday data is short-lived so TTL is short (2 min)."""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, interval=interval, prepost=False)
        if df is None or df.empty or not REQUIRED_COLS.issubset(df.columns):
            return None
        return df.dropna(subset=list(REQUIRED_COLS))
    except:
        return None


def s1_analyze_ticker(ticker: str, interval: str) -> dict:
    data = s1_safe_history(ticker, interval=interval, period="7d")
    if data is None or len(data) < 60:
        return {"ticker": ticker, "status": "NO_DATA", "interval": interval}

    df = s1_compute_indicators(data).dropna()
    if len(df) < 30:
        return {"ticker": ticker, "status": "NO_DATA", "interval": interval}

    vals = s1_get_last_values(df)
    trend = "UP" if (vals["c_last"] > vals["ema20_last"] > vals["ema50_last"]) else "DOWN"

    recent = df.tail(40)
    support = recent['Low'].rolling(5).min().iloc[-1]
    resistance = recent['High'].rolling(5).max().iloc[-1]

    near_support = (support > 0) and (abs(vals["c_last"] - support) / support <= 0.02)
    near_resistance = (resistance > 0) and (abs(vals["c_last"] - resistance) / resistance <= 0.02)

    rsi_up = vals["rsi_last"] > vals["rsi_prev"]
    rsi_down = vals["rsi_last"] < vals["rsi_prev"]

    bull_eng = (vals["c_prev"] < vals["o_prev"]) and (vals["c_last"] > vals["o_last"]) and (
                vals["c_last"] >= vals["o_prev"]) and (vals["o_last"] <= vals["c_prev"])
    bear_eng = (vals["c_prev"] > vals["o_prev"]) and (vals["c_last"] < vals["o_last"]) and (
                vals["c_last"] <= vals["o_prev"]) and (vals["o_last"] >= vals["c_prev"])

    body = abs(vals["c_last"] - vals["o_last"])
    rng = vals["h_last"] - vals["l_last"]
    is_hammer = (rng > 0) and ((min(vals["o_last"], vals["c_last"]) - vals["l_last"]) > 2 * body) and (body / rng < 0.4)

    vol_ok = (not np.isnan(vals["vol_avg20"])) and (vals["vol_avg20"] > 0) and (
                vals["v_last"] > 1.1 * vals["vol_avg20"])

    long_score = sum(
        [trend == "UP", near_support, (28 <= vals["rsi_last"] <= 55) and rsi_up, bull_eng or is_hammer, vol_ok])
    short_score = sum([trend == "DOWN", near_resistance, (55 <= vals["rsi_last"] <= 75) and rsi_down, bear_eng, vol_ok])

    if long_score >= 4:
        decision = "BUY"
    elif short_score >= 4:
        decision = "SHORT"
    elif (trend in ["UP", "DOWN"]) and (near_support or near_resistance):
        decision = "WAIT"
    else:
        decision = "NO ENTER"

    confirmed = (decision == "BUY") and (trend == "UP") and (long_score >= 3) and (
                28 <= vals["rsi_last"] <= 55) and near_support and vol_ok
    confirmed_label = "CONFIRMED" if confirmed else "NOT CONFIRMED"

    strength = 0
    if vals["c_last"] > vals["ema20_last"] > vals["ema50_last"]:
        strength += 2
    elif vals["ema20_last"] > vals["ema50_last"]:
        strength += 1
    if 35 <= vals["rsi_last"] <= 50:
        strength += 2
    elif 28 <= vals["rsi_last"] <= 55:
        strength += 1

    if support > 0:
        dist = abs(vals["c_last"] - support) / support
        if dist <= 0.01:
            strength += 2
        elif dist <= 0.02:
            strength += 1

    if (not np.isnan(vals["vol_avg20"])) and vals["vol_avg20"] > 0:
        if vals["v_last"] > 1.3 * vals["vol_avg20"]:
            strength += 2
        elif vals["v_last"] > 1.1 * vals["vol_avg20"]:
            strength += 1

    if bull_eng or is_hammer: strength += 1
    if confirmed: strength += 1

    return {
        "ticker": ticker, "status": "OK", "interval": interval, "trend": trend, "close": vals["c_last"],
        "support": support, "resistance": resistance, "rsi": vals["rsi_last"], "long_score": long_score,
        "short_score": short_score, "decision": decision, "confirmed": confirmed_label, "strength": strength,
    }


def s1_decision_color(val: str) -> str:
    if val == "BUY":
        return "background-color:#2ECC71;color:black;"
    elif val == "WAIT":
        return "background-color:#F1C40F;color:black;"
    elif val == "NO ENTER":
        return "background-color:#E74C3C;color:white;"
    return ""


def s1_confirmed_color(val: str) -> str:
    return "background-color:#27AE60;color:white;" if val == "CONFIRMED" else "background-color:#AAB7B8;color:black;"


def s1_run_interval_scan(watchlist_df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Fetches/analyzes every ticker for one interval in parallel instead of one-by-one."""
    rows = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(s1_analyze_ticker, row["Yahoo Ticker"], interval): row
            for _, row in watchlist_df.iterrows()
        }
        for future in as_completed(future_map):
            row = future_map[future]
            t = row["Yahoo Ticker"]
            company_name = row["Company Name"]
            try:
                res = future.result()
            except Exception:
                res = {"status": "NO_DATA"}

            if res.get("status") != "OK":
                rows.append({
                    "Ticker": t, "Company (Ticker)": f"{company_name} ({t})", "Decision": "NO ENTER",
                    "Trend": "", "Close": "", "Support": "", "Resistance": "", "RSI": "",
                    "LongScore": "", "ShortScore": "", "CONFIRMED": "", "Strength": 0
                })
            else:
                rows.append({
                    "Ticker": res["ticker"], "Company (Ticker)": f"{company_name} ({res['ticker']})",
                    "Decision": res["decision"], "Trend": res["trend"], "Close": round(res["close"], 2),
                    "Support": round(res["support"], 2), "Resistance": round(res["resistance"], 2),
                    "RSI": round(res["rsi"], 1), "LongScore": res["long_score"],
                    "ShortScore": res["short_score"], "CONFIRMED": res["confirmed"], "Strength": res["strength"],
                })

    df_res = pd.DataFrame(rows)
    df_res["Rank"] = df_res["Decision"].map({"BUY": 0, "WAIT": 1, "NO ENTER": 2}).fillna(3)
    df_res["ConfRank"] = df_res["CONFIRMED"].map({"CONFIRMED": 0, "NOT CONFIRMED": 1}).fillna(2)
    df_res = df_res.sort_values(
        ["Rank", "ConfRank", "Strength", "LongScore"],
        ascending=[True, True, False, False]
    ).drop(columns=["Rank", "ConfRank"])
    return df_res


# ==============================================================================
# 4. STRATEGY 2: GOEL'S SWING STRATEGY UTILITIES
# ==============================================================================
def s2_add_basic_indicators(df):
    if df.empty or len(df) < 50: return df
    df = df.copy()
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    return df


def s2_add_extra_indicators(df):
    if df.empty or len(df) < 50: return df
    df = df.copy()
    df['H-L'] = df['High'] - df['Low']
    df['H-Cp'] = (df['High'] - df['Close'].shift()).abs()
    df['L-Cp'] = (df['Low'] - df['Close'].shift()).abs()
    df['TR'] = df[['H-L', 'H-Cp', 'L-Cp']].max(axis=1)
    df['ATR'] = df['TR'].rolling(14).mean()
    df['ATR_Pct'] = (df['ATR'] / df['Close']) * 100
    df['Volume_MA20'] = df['Volume'].rolling(20).mean()
    df['Volume_Ratio'] = df['Volume'] / df['Volume_MA20'].replace(0, np.nan)
    df['Swing_Low_20'] = df['Low'].rolling(20).min()
    df['Distance_to_EMA20'] = ((df['Close'] - df['EMA20']) / df['EMA20'].replace(0, np.nan)) * 100
    df['MACD_H'] = df['MACD'] - df['MACD_Signal']
    return df.bfill().ffill().fillna(0)


@st.cache_data(ttl=600)
def s2_check_market_context():
    try:
        spy_data = yf.download('SPY', period='3mo', progress=False)
        if isinstance(spy_data.columns, pd.MultiIndex):
            spy_data.columns = [col[0] for col in spy_data.columns]
        spy_data['EMA50'] = spy_data['Close'].ewm(span=50, adjust=False).mean()
        is_bullish = spy_data['Close'].iloc[-1] > spy_data['EMA50'].iloc[-1]
        return is_bullish, f"SPY: {'Bullish ✓' if is_bullish else 'Bearish ✗'}"
    except:
        return True, "Market check unavailable"


@st.cache_data(ttl=300)
def s2_check_vix_level():
    try:
        vix_data = yf.download('^VIX', period='1d', progress=False)
        if isinstance(vix_data.columns, pd.MultiIndex):
            vix_data.columns = [col[0] for col in vix_data.columns]
        vix_value = float(vix_data['Close'].iloc[-1])
        if vix_value < 15:
            return vix_value, "Very Calm", "Too slow, hard to make 2-3%", False, "blue"
        elif vix_value < 20:
            return vix_value, "Normal/Healthy", "IDEAL for swing trading ✅", True, "green"
        elif vix_value < 30:
            return vix_value, "Worried", "Getting dangerous - Only take STRONG BUY", "selective", "orange"
        elif vix_value < 40:
            return vix_value, "Scared", "Very risky, avoid trading", False, "red"
        else:
            return vix_value, "Panic", "Market crash, STOP trading", False, "darkred"
    except:
        return None, "Unavailable", "Could not fetch VIX", None, "gray"


def s2_enhanced_signal(df):
    if df.empty or len(df) < 50: return "HOLD", "Insufficient data", "N/A"
    try:
        last = df.iloc[-1]
        vix_value, vix_category, _, _, _ = s2_check_vix_level()
        trend_up = float(last['EMA20']) > float(last['EMA50'])
        volume_good = float(last.get('Volume_Ratio', 0)) > 1.2
        volatility_good = float(last.get('ATR_Pct', 0)) > 1.5
        market_bullish, _ = s2_check_market_context()

        pullback_to_ema = -5.0 <= float(last.get('Distance_to_EMA20', 0)) <= 0.0
        rsi_not_hot = float(last['RSI']) < 65
        pullback_count = sum([trend_up, pullback_to_ema, rsi_not_hot, volume_good, volatility_good])

        breakout = float(last['Close']) > float(df['High'].tail(5).max())
        rsi_not_extreme = float(last['RSI']) < 75
        breakout_count = sum([trend_up, breakout, volume_good, volatility_good, rsi_not_extreme])

        vix_str = f"{vix_value:.1f}" if vix_value else "N/A"

        if vix_value and vix_value > 30:
            if pullback_count >= 4 and market_bullish:
                return "STRONG BUY (Pullback)", f"Perfect pullback | VIX: {vix_str}", vix_str
            elif breakout_count >= 4 and market_bullish:
                return "STRONG BUY (Breakout)", f"Perfect breakout | VIX: {vix_str}", vix_str
            return "HOLD", f"⚠️ VIX High ({vix_str}), SKIP | PB:{pullback_count}/5 BC:{breakout_count}/5", vix_str

        if pullback_count >= 4 and market_bullish:
            return "STRONG BUY (Pullback)", f"Perfect pullback | VIX: {vix_str}", vix_str
        elif pullback_count >= 3:
            return "POTENTIAL BUY (Pullback)", f"Good pullback near EMA20 | VIX: {vix_str}", vix_str
        if breakout_count >= 4 and market_bullish:
            return "STRONG BUY (Breakout)", f"Perfect breakout | VIX: {vix_str}", vix_str
        elif breakout_count >= 3:
            return "POTENTIAL BUY (Breakout)", f"Breakout above 5-day high | VIX: {vix_str}", vix_str
        if pullback_count >= 2 or breakout_count >= 3: return "MODERATE BUY", f"Weak setup | VIX: {vix_str}", vix_str
        return "HOLD", f"No setup | PB:{pullback_count}/5 BC:{breakout_count}/5", vix_str
    except Exception as e:
        return "ERROR", str(e), "N/A"


@st.cache_data(ttl=900, show_spinner=False)
def s2_fetch_safe(ticker):
    """Cached — 1y of daily data doesn't need to be re-downloaded every rerun."""
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex): df.columns = [col[0] for col in df.columns]
        if df.empty or not {'Open', 'High', 'Low', 'Close', 'Volume'}.issubset(df.columns): return pd.DataFrame()
        df = df.reset_index()
        if 'Date' in df.columns: df['Date'] = pd.to_datetime(df['Date']); df = df.set_index('Date')
        return df.dropna()
    except:
        return pd.DataFrame()


def s2_score_signal(row):
    score = 0
    sig = str(row.get('Enhanced Signal', ''))
    if 'STRONG BUY' in sig:
        score += 50
    elif 'POTENTIAL BUY' in sig:
        score += 35
    elif 'MODERATE BUY' in sig:
        score += 20
    vr = row.get('Volume Ratio', 0)
    if isinstance(vr, (int, float)):
        if vr > 2.0:
            score += 20
        elif vr > 1.5:
            score += 15
        elif vr > 1.2:
            score += 10
    atr_pct = row.get('ATR %', 0)
    if isinstance(atr_pct, (int, float)):
        if atr_pct > 3:
            score += 15
        elif atr_pct > 2:
            score += 10
        elif atr_pct > 1.5:
            score += 5
    return min(score, 100)


def s2_rating_from_score(score):
    if score >= 85:
        return "A+ (High Probability)"
    elif score >= 70:
        return "A (Strong Setup)"
    elif score >= 55:
        return "B (Decent)"
    return "C (Weak)"


def s2_analyze_single(ticker: str, ticker_to_name: dict) -> dict:
    df_s2 = s2_fetch_safe(ticker)
    if df_s2.empty:
        return {
            'Ticker': ticker, 'Company Name': ticker_to_name.get(ticker, ticker), 'Enhanced Signal': 'NO DATA',
            'Current Price': '-', 'Entry Price': '-', 'Stop Loss (ATR)': '-', 'Target 2%': '-',
            'Target 3%': '-', 'Volume Ratio': '-', 'ATR %': '-', 'Score': 0, 'Reason': 'No data', 'VIX Level': '-'
        }

    df_s2 = s2_add_basic_indicators(df_s2)
    df_s2 = s2_add_extra_indicators(df_s2)
    signal, reason, vix_level = s2_enhanced_signal(df_s2)
    last_row = df_s2.iloc[-1]

    close_p = float(last_row['Close']) if 'Close' in last_row else 0
    atr_v = float(last_row['ATR']) if 'ATR' in last_row else 0
    v_ratio = float(last_row['Volume_Ratio']) if 'Volume_Ratio' in last_row else 0
    a_pct = float(last_row['ATR_Pct']) if 'ATR_Pct' in last_row else 0

    return {
        'Ticker': ticker, 'Company Name': ticker_to_name.get(ticker, ticker), 'Enhanced Signal': signal,
        'Current Price': round(close_p, 2) if close_p else "-",
        'Entry Price': round(close_p, 2) if close_p else "-",
        'Stop Loss (ATR)': round(close_p - (atr_v * 1.5), 2) if close_p and atr_v else "-",
        'Target 2%': round(close_p * 1.02, 2) if close_p else "-",
        'Target 3%': round(close_p * 1.03, 2) if close_p else "-",
        'Volume Ratio': round(v_ratio, 2) if v_ratio else "-", 'ATR %': round(a_pct, 2) if a_pct else "-",
        'Score': 0, 'Reason': reason, 'VIX Level': vix_level
    }


def s2_run_scan(watchlist: list, ticker_to_name: dict) -> pd.DataFrame:
    results_s2 = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(s2_analyze_single, t, ticker_to_name) for t in watchlist]
        for f in as_completed(futures):
            results_s2.append(f.result())

    df_results_s2 = pd.DataFrame(results_s2)
    df_results_s2['Score'] = df_results_s2.apply(s2_score_signal, axis=1)
    df_results_s2['Rating'] = df_results_s2['Score'].apply(s2_rating_from_score)
    return df_results_s2


# ==============================================================================
# 5. STRATEGY 3: 52-WEEK DROP ANALYZER UTILITIES
# ==============================================================================
@st.cache_data(show_spinner=False)
def s3_download_single_ticker(ticker: str):
    try:
        df = yf.download(ticker, period="2y", interval="1d", progress=False)
        if df is None or df.empty: return None
        df.index = pd.to_datetime(df.index)
        if isinstance(df.columns, pd.MultiIndex): df.columns = [col[0] for col in df.columns]
        return df
    except:
        return None


# ==============================================================================
# 6. STRATEGY 4 (LEGACY, UNUSED): kept only because other code may reference it
# ==============================================================================
def s4_get_last_values(df: pd.DataFrame):
    return {
        "o_last": float(df["Open"].iloc[-1]),
        "h_last": float(df["High"].iloc[-1]),
        "l_last": float(df["Low"].iloc[-1]),
        "c_last": float(df["Close"].iloc[-1]),
        "v_last": float(df["Volume"].iloc[-1]),
        "o_prev": float(df["Open"].iloc[-2]),
        "h_prev": float(df["High"].iloc[-2]),
        "l_prev": float(df["Low"].iloc[-2]),
        "c_prev": float(df["Close"].iloc[-2]),
        "ema20_last": float(df["EMA20"].iloc[-1]),
        "ema50_last": float(df["EMA50"].iloc[-1]),
        "rsi_last": float(df["RSI14"].iloc[-1]),
        "rsi_prev": float(df["RSI14"].iloc[-2]),
        "vol_avg20": float(df["VolAvg20"].iloc[-1]),
        "day_range_pos": (float(df["Close"].iloc[-1]) - float(df["Low"].iloc[-1])) / (
                    float(df["High"].iloc[-1]) - float(df["Low"].iloc[-1]) + 1e-9),
    }


def s4_detect_support_resistance(df: pd.DataFrame, lookback: int = 40):
    recent = df.tail(lookback)
    support = recent['Low'].rolling(5).min().iloc[-1]
    resistance = recent['High'].rolling(5).max().iloc[-1]
    return support, resistance


# ==============================================================================
# 7. STRATEGY 5: OVERNIGHT GAP SCREENER UTILITIES
# ==============================================================================
@st.cache_data(ttl=300, show_spinner=False)
def s4n_fetch_daily(ticker: str):
    stock = yf.Ticker(ticker)
    df = stock.history(period="3mo", interval="1d", prepost=False)
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def s4n_fetch_earnings(ticker: str):
    """Earnings dates barely change intraday — cache for an hour."""
    stock = yf.Ticker(ticker)
    try:
        return stock.earnings_dates
    except Exception:
        return None


def s4n_color(val):
    if "STRONG" in str(val):
        return "background-color:#2ECC71;color:black;"
    elif "WATCH" in str(val):
        return "background-color:#F1C40F;color:black;"
    elif "SKIP" in str(val):
        return "background-color:#E74C3C;color:white;"
    return ""


def s4n_analyze_single(ticker, name, min_range_pos, rsi_low, rsi_high, min_vol_ratio, exclude_earnings_days):
    try:
        df = s4n_fetch_daily(ticker)
        if df is None or df.empty or len(df) < 25:
            return None
        df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["RSI14"] = s1_rsi(df["Close"])
        df["VolAvg20"] = df["Volume"].rolling(20).mean()

        last = df.iloc[-1]
        c_last = float(last["Close"])
        h_last = float(last["High"])
        l_last = float(last["Low"])
        v_last = float(last["Volume"])
        rsi_last = float(df["RSI14"].iloc[-1])
        vol_avg20 = float(df["VolAvg20"].iloc[-1])
        ema20_last = float(df["EMA20"].iloc[-1])

        day_range = h_last - l_last
        range_pos = (c_last - l_last) / day_range if day_range > 0 else 0.5

        closing_strength_ok = range_pos >= min_range_pos
        rsi_ok = rsi_low <= rsi_last <= rsi_high
        vol_ok = (not np.isnan(vol_avg20)) and vol_avg20 > 0 and v_last >= min_vol_ratio * vol_avg20
        trend_ok = c_last > ema20_last

        earnings_soon = False
        earnings_note = "None found"
        try:
            edates = s4n_fetch_earnings(ticker)
            if edates is not None and not edates.empty:
                now_ts = pd.Timestamp.now(tz=edates.index.tz) if edates.index.tz else pd.Timestamp.now()
                upcoming = edates.index[edates.index >= now_ts]
                if len(upcoming) > 0:
                    days_out = (upcoming[0] - now_ts).days
                    if days_out <= exclude_earnings_days:
                        earnings_soon = True
                        earnings_note = f"⚠️ In {days_out}d"
                    else:
                        earnings_note = f"In {days_out}d"
        except Exception:
            earnings_note = "Unknown"

        # Closing Strength and Earnings are now hard gates, not just two votes out of five.
        # This strategy's entry mechanic IS the strong close — a weak close should disqualify
        # a name outright rather than get outvoted by RSI/volume/trend agreeing on everything else.
        sub_score = sum([rsi_ok, vol_ok, trend_ok])  # secondary confirmation, out of 3

        if earnings_soon:
            decision = "❌ SKIP (Earnings Risk)"
        elif not closing_strength_ok:
            decision = "❌ SKIP (Weak Close)"
        elif sub_score == 3:
            decision = "🔥 STRONG CANDIDATE"
        elif sub_score == 2:
            decision = "⚠️ WATCH"
        else:
            decision = "❌ SKIP"

        return {
            "Ticker": ticker,
            "Company": name,
            "Decision": decision,
            "Score": f"{sub_score}/3",
            "Close": round(c_last, 2),
            "Closing Strength %": round(range_pos * 100, 1),
            "RSI": round(rsi_last, 1),
            "Vol vs Avg": round(v_last / vol_avg20, 2) if vol_avg20 else "-",
            "Trend": "UP" if trend_ok else "DOWN",
            "Earnings": earnings_note,
            "Suggested Target (+2%)": round(c_last * 1.02, 2),
            "Suggested Stop (-1.5%)": round(c_last * 0.985, 2),
        }
    except Exception:
        return None


def s4n_run_scan(watchlist_df, min_range_pos, rsi_low, rsi_high, min_vol_ratio, exclude_earnings_days) -> pd.DataFrame:
    rows = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(
                s4n_analyze_single, row["Yahoo Ticker"], row["Company Name"],
                min_range_pos, rsi_low, rsi_high, min_vol_ratio, exclude_earnings_days
            )
            for _, row in watchlist_df.iterrows()
        ]
        for f in as_completed(futures):
            r = f.result()
            if r is not None:
                rows.append(r)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    rank_map = {
        "🔥 STRONG CANDIDATE": 0, "⚠️ WATCH": 1,
        "❌ SKIP (Earnings Risk)": 2, "❌ SKIP (Weak Close)": 3, "❌ SKIP": 4,
    }
    df["_rank"] = df["Decision"].map(rank_map).fillna(5)
    df = df.sort_values("_rank").drop(columns=["_rank"])
    return df


# ==============================================================================
# ==============================================================================
# TAB EXECUTION BLOCKS
# ==============================================================================
# ==============================================================================

# ==============================================================================
# 🎯 TAB 1: ATHARV SWING SCANNER
# ==============================================================================
with tab1:
    st.header("Atharv Swing Trading Scanner (5m + 15m)")

    watchlist_df = shared_load_watchlist()
    tickers = watchlist_df["Yahoo Ticker"].tolist()
    st.write(f"Loaded **{len(tickers)}** tickers from internal configuration repository.")

    intervals = ["5m", "15m"]

    if st.button("Run Scanner", key="btn_run_atharv_scanner"):
        st.session_state["tab1_results"] = {}
        for interval in intervals:
            with st.spinner(f"Scanning {len(tickers)} tickers on {interval}..."):
                st.session_state["tab1_results"][interval] = s1_run_interval_scan(watchlist_df, interval)

    # Persisted display — survives reruns triggered elsewhere in the app (e.g. Tab 2 autorefresh)
    if "tab1_results" in st.session_state:
        for interval, df_res in st.session_state["tab1_results"].items():
            st.subheader(f"Interval Target: {interval}")
            styled = df_res.style.apply(
                lambda col: [s1_decision_color(v) for v in col], subset=["Decision"]
            ).apply(
                lambda col: [s1_confirmed_color(v) for v in col], subset=["CONFIRMED"]
            )
            st.dataframe(styled, use_container_width=True)

# ==============================================================================
# 📈 TAB 2: GOEL'S SWING STRATEGY
# ==============================================================================
with tab2:
    st.header("📈 Goel's Swing Strategy Engine")

    autorefresh_on = st.checkbox(
        "Enable auto-refresh (every 3 min)", value=True, key="goel_autorefresh_toggle",
        help="This reruns the whole app, not just this tab. Turn it off if you're actively "
             "working in another tab (e.g. running the Overnight Screener) and don't want interruptions."
    )
    if autorefresh_on:
        st_autorefresh(interval=180000, key="refresh_goel_tab")

    s2_watchlist = shared_load_watchlist()["Yahoo Ticker"].tolist()
    ticker_to_name = dict(zip(shared_load_watchlist()["Yahoo Ticker"], shared_load_watchlist()["Company Name"]))

    st.markdown("### Market Environmental Conditions")
    col1, col2 = st.columns(2)
    with col1:
        spy_bullish, spy_msg = s2_check_market_context()
        if spy_bullish:
            st.success(f"📈 {spy_msg}")
        else:
            st.error(f"📉 {spy_msg}")
    with col2:
        vix_val, vix_cat, vix_cond, trading_ok, vix_color = s2_check_vix_level()
        if vix_val:
            st.info(f"VIX: {vix_val:.2f} ({vix_cat}) — {vix_cond}")
        else:
            st.warning("VIX Matrix configuration data currently unavailable")

    st.markdown("---")

    col_add_1, col_add_2 = st.columns([4, 1])
    with col_add_1:
        new_ticker = st.text_input("Enter ticker to add to master engine list:", "", key="txt_add_goel").upper().strip()
    with col_add_2:
        if st.button("Add Ticker Asset", key="btn_add_goel"):
            if new_ticker and new_ticker not in s2_watchlist:
                s2_watchlist.append(new_ticker)
                shared_save_watchlist(s2_watchlist)
                st.success(f"Added {new_ticker}!")
                st.rerun()

    if s2_watchlist:
        st.info(f"Analyzing metrics for {len(s2_watchlist)} tracked parameters...")
        with st.spinner("Fetching and scoring watchlist..."):
            df_results_s2 = s2_run_scan(s2_watchlist, ticker_to_name)

        strong_df = df_results_s2[df_results_s2['Enhanced Signal'].str.contains('STRONG BUY', na=False)].sort_values(
            'Score', ascending=False)
        potential_df = df_results_s2[
            df_results_s2['Enhanced Signal'].str.contains('POTENTIAL BUY', na=False)].sort_values('Score',
                                                                                                  ascending=False)
        moderate_df = df_results_s2[
            df_results_s2['Enhanced Signal'].str.contains('MODERATE BUY', na=False)].sort_values('Score',
                                                                                                 ascending=False)

        st.subheader(f"🚀 STRONG BUY SETUPS ({len(strong_df)})")
        if not strong_df.empty:
            st.dataframe(strong_df[['Ticker', 'Company Name', 'Enhanced Signal', 'Current Price', 'Entry Price',
                                    'Stop Loss (ATR)', 'Target 2%', 'Target 3%', 'VIX Level', 'Score', 'Rating']],
                         use_container_width=True)
        else:
            st.info("No strong conditions detected.")

        with st.expander(f"💡 POTENTIAL SIGNALS ({len(potential_df)})"):
            if not potential_df.empty:
                st.dataframe(potential_df[['Ticker', 'Company Name', 'Enhanced Signal', 'Current Price', 'Entry Price',
                                           'Stop Loss (ATR)', 'Target 2%', 'Target 3%', 'VIX Level', 'Score',
                                           'Rating']], use_container_width=True)
            else:
                st.info("No elements inside bucket.")

        with st.expander(f"⚠️ MODERATE ALPHA ALERTS ({len(moderate_df)})"):
            if not moderate_df.empty:
                st.dataframe(moderate_df[['Ticker', 'Company Name', 'Enhanced Signal', 'Current Price', 'Entry Price',
                                          'Stop Loss (ATR)', 'Target 2%', 'Target 3%', 'VIX Level', 'Score', 'Rating']],
                             use_container_width=True)
            else:
                st.info("No elements inside bucket.")

# ==============================================================================
# 📊 TAB 3: 52-WEEK HIGH DROP ANALYZER
# ==============================================================================
with tab3:
    st.header("📉 52-Week High Drop Analyzer Overview")

    CATEGORIES = {"<10%": (0.0, 10.0), "10-20%": (10.0, 20.0), "20-30%": (10.0, 30.0), "30-40%": (30.0, 40.0),
                  "40-50%": (40.0, 50.0001)}
    CATEGORY_COLORS = {"<10%": "#d9f0ff", "10-20%": "#b3e6ff", "20-30%": "#ffeeb3", "30-40%": "#ffd6cc",
                       "40-50%": "#ffb3b3"}

    watch_data_s3 = shared_load_watchlist()
    tickers_s3 = watch_data_s3['Yahoo Ticker'].tolist()
    companies_s3 = dict(zip(watch_data_s3['Yahoo Ticker'], watch_data_s3['Company Name']))

    if len(tickers_s3) == 0:
        st.warning("Please add data parameters into watchlist.csv to initialize.")
    else:
        st.info("Computing mathematical rolling matrices against 252-day baseline...")
        collected_s3 = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            hist_map = dict(zip(tickers_s3, executor.map(s3_download_single_ticker, tickers_s3)))

        for ticker in tickers_s3:
            df_hist = hist_map.get(ticker)
            if df_hist is not None and not df_hist.empty and "Close" in df_hist.columns:
                high_s = df_hist["High"] if "High" in df_hist.columns else df_hist["Close"]
                h52_series = high_s.rolling(window=252, min_periods=1).max()

                latest_c = float(df_hist["Close"].iloc[-1])
                latest_h = float(h52_series.iloc[-1])

                if latest_h > 0:
                    drop_p = ((latest_h - latest_c) / latest_h) * 100
                    collected_s3.append({
                        "Company Name": companies_s3.get(ticker, ticker), "Ticker": ticker,
                        "Current Price": round(latest_c, 2), "52-Week High": round(latest_h, 2),
                        "Drop %": round(drop_p, 2)
                    })

        if len(collected_s3) == 0:
            st.error("Historical loading engine failed to construct values.")
        else:
            df_all_s3 = pd.DataFrame(collected_s3)

            for label, rng in CATEGORIES.items():
                b_df = df_all_s3[(df_all_s3["Drop %"] >= rng[0]) & (df_all_s3["Drop %"] < rng[1])].copy()
                b_df.sort_values("Drop %", ascending=False, inplace=True)

                c_color = CATEGORY_COLORS[label]
                with st.expander(f"{label} Bracket Pool — {len(b_df)} listings"):
                    st.markdown(
                        f"<div style='background:{c_color};padding:8px;border-radius:6px;color:black;'><b>Bracket Context: {label}</b> Drop Status</div>",
                        unsafe_allow_html=True)
                    if b_df.empty:
                        st.info("No assets within range boundaries.")
                    else:
                        render_df = b_df.copy()
                        render_df["Current Price"] = render_df["Current Price"].map(lambda x: f"{x:.2f}")
                        render_df["52-Week High"] = render_df["52-Week High"].map(lambda x: f"{x:.2f}")
                        render_df["Drop %"] = render_df["Drop %"].map(lambda x: f"{x:.2f}%")
                        st.dataframe(render_df, use_container_width=True)

# ==============================================================================
# 📊 TAB 4: 🌙 Overnight Gap Screener
# ==============================================================================
with tab4:
    st.header("🌙 Overnight Gap Screener")
    st.caption("Buy at today's close, sell at tomorrow's open (or first 5-10 min). Target ~2%. "
               "This is a new, independent screener — it does not touch any logic used elsewhere in this app.")

    s4n_watchlist = shared_load_watchlist()

    s4n_col1, s4n_col2, s4n_col3 = st.columns(3)
    s4n_min_range_pos = s4n_col1.slider("Min. Closing Strength (% of day's range)", 50, 100, 70, 5,
                                         key="s4n_range_pos") / 100
    s4n_rsi_low, s4n_rsi_high = s4n_col2.slider("RSI Band (avoid overbought/oversold)", 10, 90, (28, 65),
                                                 key="s4n_rsi_band")
    s4n_min_vol_ratio = s4n_col3.slider("Min. Volume vs 20d Avg", 1.0, 2.5, 1.1, 0.1, key="s4n_vol_ratio")

    s4n_exclude_earnings_days = st.slider("Exclude if earnings within next N days", 0, 5, 2, key="s4n_earn_days")

    if st.button("🔄 Run Overnight Screener", key="s4n_run_btn"):
        with st.spinner("Scanning watchlist for overnight gap candidates..."):
            st.session_state["tab4_results"] = s4n_run_scan(
                s4n_watchlist, s4n_min_range_pos, s4n_rsi_low, s4n_rsi_high,
                s4n_min_vol_ratio, s4n_exclude_earnings_days
            )

    # Persisted display — this is what keeps your results on screen even if a
    # background rerun happens elsewhere in the app (e.g. Tab 2's autorefresh).
    if "tab4_results" in st.session_state:
        s4n_df = st.session_state["tab4_results"]
        if s4n_df is not None and not s4n_df.empty:
            st.dataframe(
                s4n_df.style.map(s4n_color, subset=["Decision"]),
                use_container_width=True, hide_index=True
            )
            st.caption(
                "⚠️ Reminder: overnight positions can't be stopped out until the market reopens. "
                "Size positions assuming the stop could be missed by a gap, not hit cleanly. "
                "'Earnings' field depends on Yahoo Finance data being current — always double-check "
                "manually before holding anything overnight."
            )
        else:
            st.info("No candidates matched, or watchlist/data unavailable.")

with tab5:
    st.header("⚡ Live Large-Cap Stock + ETF Pullback Funnel")
    with st.sidebar:
        st.header("⚙️ Settings")
        st.markdown("---")

        min_cap = st.number_input("Stock Min Market Cap ($B)", value=50, min_value=1, step=5)
        min_aum = st.number_input("ETF Min AUM ($B)", value=5.0, min_value=0.0, step=1.0,
                                  help="Fetched only for final candidates")
        min_avg_vol = st.number_input("ETF Min Avg Volume", value=50_000, min_value=0, step=10_000,
                                      help="Early liquidity filter – keeps app fast")

        min_pb = st.slider("Min % off 3-mo high", 0, 40, 8)
        rsi_lo, rsi_hi = st.slider("RSI range", 0, 100, (32, 52))

        st.markdown("---")
        req_sma = st.checkbox("Require > 200-SMA", value=True)
        req_vol = st.checkbox("Require declining volume", value=False)
        use_rs = st.checkbox("Require RS vs SPY", value=False)
        rs_th = st.slider("Min RS vs SPY", -20, 30, 0, disabled=not use_rs)

        max_sec = st.number_input("Max stocks / sector", value=4, min_value=1, step=1)
        earn_d = st.slider("Flag earnings within days", 0, 14, 7)

        st.markdown("---")
        use_score = st.checkbox("Enable scoring", value=True)
        rsi_m = st.selectbox("RSI method", ["sma", "wilder"])

        run = st.button("⚡ Run Live Funnel", type="primary", use_container_width=True)

    if run:
        bar = st.progress(0)
        status = st.empty()


        def prog(p, msg):
            bar.progress(min(p, 1.0))
            status.caption(msg)


        with st.spinner("Running live parallel funnel…"):
            stock_df, stock_st = s8_run_stock_funnel(
                min_cap, min_pb, rsi_lo, rsi_hi, req_sma,
                (rs_th if use_rs else None), req_vol, max_sec, earn_d,
                use_score, rsi_m, prog
            )
            etf_df, etf_st = s8_run_etf_funnel(
                min_aum, min_pb, rsi_lo, rsi_hi, req_sma,
                (rs_th if use_rs else None), req_vol, min_avg_vol,
                use_score, rsi_m, prog
            )

        st.session_state.update({
            "stock_results": stock_df, "stock_stages": stock_st,
            "etf_results": etf_df, "etf_stages": etf_st,
            "run_time": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        bar.empty()
        status.empty()

    # ---------- Results ----------
    if "stock_results" in st.session_state:
        t = st.session_state["run_time"]
        tab1, tab2 = st.tabs(["📈 Stocks", "📊 ETFs (Live)"])

        with tab1:
            st.subheader(f"Stock Shortlist • {t}")
            with st.expander("Stages"):
                for k, v in st.session_state["stock_stages"].items():
                    st.write(f"**{k}:** {v:,}")

            df = st.session_state["stock_results"]
            if df.empty:
                st.info("No stocks matched.")
            else:
                cols = ["Rank", "Ticker", "Name", "Sector", "MarketCap($B)", "Price", "SMA200",
                        "DistToSMA%", "PctOffHigh", "RSI", "RS_vs_SPY", "VolDeclining", "EarningsNote"]
                if "Score" in df.columns: cols.insert(1, "Score")
                st.dataframe(
                    df[cols].style.apply(s8_row_color, axis=1).format({
                        "MarketCap($B)": "{:.1f}", "Price": "${:.2f}", "SMA200": "${:.2f}",
                        "DistToSMA%": "{:+.1f}%", "PctOffHigh": "{:.1f}%", "RSI": "{:.1f}",
                        "RS_vs_SPY": "{:+.1f}", "Score": "{:.0f}"
                    }, na_rep="—"),
                    use_container_width=True, hide_index=True
                )
                c1, c2 = st.columns(2)
                c1.download_button("⬇️ Stocks CSV", df.to_csv(index=False).encode(),
                                   f"stocks_{datetime.now():%Y%m%d}.csv", "text/csv")
                if c2.button("➕ Add stocks to watchlist"):
                    existing = shared_load_watchlist()["Yahoo Ticker"].tolist()
                    shared_save_watchlist(list(dict.fromkeys(existing + df["Ticker"].tolist())))
                    st.success("Added to watchlist_test.csv")

        with tab2:
            st.subheader(f"Live ETF Shortlist • {t}")
            with st.expander("Stages"):
                for k, v in st.session_state["etf_stages"].items():
                    st.write(f"**{k}:** {v:,}")

            edf = st.session_state["etf_results"]
            if edf.empty:
                st.info("No ETFs matched.")
            else:
                cols = ["Rank", "Ticker", "Name", "AUM($B)", "Price", "SMA200",
                        "DistToSMA%", "PctOffHigh", "RSI", "RS_vs_SPY", "AvgVolume", "VolDeclining"]
                if "Score" in edf.columns: cols.insert(1, "Score")
                st.dataframe(
                    edf[cols].style.format({
                        "AUM($B)": "{:.1f}", "Price": "${:.2f}", "SMA200": "${:.2f}",
                        "DistToSMA%": "{:+.1f}%", "PctOffHigh": "{:.1f}%", "RSI": "{:.1f}",
                        "RS_vs_SPY": "{:+.1f}", "AvgVolume": "{:,.0f}", "Score": "{:.0f}"
                    }, na_rep="—"),
                    use_container_width=True, hide_index=True
                )
                c1, c2 = st.columns(2)
                c1.download_button("⬇️ ETFs CSV", edf.to_csv(index=False).encode(),
                                   f"etfs_{datetime.now():%Y%m%d}.csv", "text/csv")
                if c2.button("➕ Add ETFs to watchlist"):
                    existing = shared_load_watchlist()["Yahoo Ticker"].tolist()
                    shared_save_watchlist(list(dict.fromkeys(existing + edf["Ticker"].tolist())))
                    st.success("Added to watchlist_test.csv")