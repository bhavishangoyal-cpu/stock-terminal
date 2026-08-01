"""
Large-Cap Stock + ETF Pullback Funnel — LIVE + FAST
===================================================
- Stocks: Live Nasdaq screener (Market Cap)
- ETFs: Fully live from official Nasdaq Trader files (all ETFs)
- AUM filter for ETFs (fetched only on shortlist → fast)
- Heavy parallelization + caching for speed
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# ------------------------------------------------------------------
# Config – tuned for speed
# ------------------------------------------------------------------
st.set_page_config(page_title="Live Stock + ETF Pullback Funnel", layout="wide")
st.title("⚡ Live Large-Cap Stock + ETF Pullback Funnel")
st.caption("Fully live universe • Parallel engine • AUM filter on shortlist only")

MAX_WORKERS = 16          # higher = faster (adjust to your CPU)
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

# ==================================================================
# Shared utilities
# ==================================================================
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


# ==================================================================
# UI
# ==================================================================
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