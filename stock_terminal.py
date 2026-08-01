# ============================================================================
# ◆ BLOOMBERG AI INSTITUTIONAL TERMINAL
# Master Version 2.0 — Unified Edition
#
# Combines:
#   - UFI Terminal glass UI
#   - Institutional Terminal's rigorous financial engine
#   - Institutional Decision Score (100-point scoring system)
#   - Enhanced Technicals (MACD, ATR, Bollinger, RS vs SPY)
#   - Earnings Intelligence (real beat rate, revision trend, implied move)
#   - News Sentiment (lexicon-based, no API key)
#   - Macro Dashboard (VIX, yield curve, dollar, FRED-style)
#   - SEC Filings (EDGAR, no key)
#   - Options Analytics (put/call, max pain, implied move)
#   - AI Thesis Generator (rule-based, explains WHY)
#   - Portfolio Risk Engine (beta, correlation, sector exposure)
#   - Self-learning Calibration (accuracy tracking vs real price moves)
#
# All free data sources — no paid API keys required.
# ============================================================================

import datetime
import sqlite3
import warnings

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

warnings.filterwarnings("ignore")

# ============================================================================
# CONFIG
# ============================================================================

TICKER_STRIP_SYMBOLS = ["SPY", "QQQ", "^VIX", "^TNX", "DX-Y.NYB", "GC=F", "CL=F", "BTC-USD"]

VERDICT_COLORS = {
    "STRONG BUY": "#22d3ee",
    "BUY":        "#34d399",
    "HOLD":       "#facc15",
    "AVOID":      "#fb923c",
    "AVOID / HIGH RISK": "#f87171",
    "NO DATA":    "#94a3b8",
}

PEER_MAP = {
    "NVDA": ["AMD", "AVGO", "INTC", "QCOM"],
    "AMD":  ["NVDA", "INTC", "QCOM", "AVGO"],
    "TSLA": ["RIVN", "GM", "F", "STLA"],
    "GOOG": ["META", "MSFT", "AMZN"],
    "GOOGL":["META", "MSFT", "AMZN"],
    "META": ["GOOGL", "SNAP", "PINS", "RDDT"],
    "MSFT": ["GOOGL", "AMZN", "ORCL", "CRM"],
    "AAPL": ["MSFT", "GOOGL", "SSNLF"],
    "AMZN": ["WMT", "TGT", "GOOGL", "MSFT"],
    "PLTR": ["SNOW", "AI", "MDB", "DDOG"],
    "ASTS": ["RKLB", "IRDM", "GSAT", "SPCE"],
    "RKLB": ["ASTS", "SPCE", "LUNR", "BKSY"],
    "ORCL": ["MSFT", "SAP", "CRM", "NOW"],
    "CRM":  ["MSFT", "ORCL", "NOW", "WDAY"],
    "SHOP": ["AMZN", "WIX", "BIGC", "ETSY"],
    "COIN": ["MSTR", "HOOD", "SQ", "PYPL"],
    "V":    ["MA", "AXP", "PYPL", "SQ"],
    "JPM":  ["BAC", "WFC", "C", "GS"],
    "BRK-B":["JPM", "BAC", "V", "MA"],
}

# ============================================================================
# MEMORY (SQLite — tracks predictions for self-learning)
# ============================================================================

@st.cache_resource
def get_memory():
    conn = sqlite3.connect("bloomberg_terminal.db", check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS predictions
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         ticker TEXT, date TEXT, verdict TEXT,
         inst_score REAL, price_at_prediction REAL)""")
    conn.commit()
    return conn

def save_prediction(ticker, verdict, score, price):
    try:
        conn = get_memory()
        conn.execute(
            "INSERT INTO predictions (ticker,date,verdict,inst_score,price_at_prediction) VALUES (?,?,?,?,?)",
            (ticker, str(datetime.datetime.now()), verdict, score, price)
        )
        conn.commit()
    except Exception:
        pass

def get_prediction_history(ticker, limit=20):
    try:
        conn = get_memory()
        rows = conn.execute(
            "SELECT date,verdict,inst_score,price_at_prediction FROM predictions WHERE ticker=? ORDER BY id DESC LIMIT ?",
            (ticker, limit)
        ).fetchall()
        return rows
    except Exception:
        return []

# ============================================================================
# CSS — Bloomberg Dark Glass UI
# ============================================================================

def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .stApp {
        background:
            radial-gradient(circle at 10% 0%, rgba(56,189,248,0.07), transparent 40%),
            radial-gradient(circle at 90% 5%, rgba(129,140,248,0.07), transparent 40%),
            linear-gradient(180deg, #03050a 0%, #080c14 50%, #04060c 100%);
        color: #e2e8f0;
    }
    .block-container { padding-top: 0.75rem; padding-bottom: 2rem; max-width: 1500px; }
    #MainMenu, footer, header { visibility: hidden; }
    h1,h2,h3,h4 { color: #f8fafc !important; font-weight: 700 !important; letter-spacing: -0.01em; }

    /* TICKER STRIP */
    .ticker-wrap {
        width:100%; overflow:hidden;
        background: rgba(255,255,255,0.025);
        border:1px solid rgba(148,163,184,0.12);
        border-radius:8px; padding:9px 0; margin-bottom:14px;
    }
    .ticker-move { display:inline-block; animation:ticker-scroll 40s linear infinite; font-family:'JetBrains Mono',monospace; font-size:13px; }
    .ticker-wrap:hover .ticker-move { animation-play-state:paused; }
    @keyframes ticker-scroll { 0%{transform:translateX(0)} 100%{transform:translateX(-50%)} }
    .ticker-item { display:inline-block; padding:0 24px; color:#94a3b8; }
    .ticker-up { color:#34d399; } .ticker-down { color:#f87171; }
    .ticker-sym { color:#f8fafc; font-weight:700; margin-right:5px; }

    /* GLASS CARD */
    .glass-card {
        background: linear-gradient(160deg, rgba(255,255,255,0.045), rgba(255,255,255,0.012));
        border:1px solid rgba(148,163,184,0.13);
        border-radius:14px; padding:20px 22px;
        box-shadow:0 8px 28px rgba(0,0,0,0.35); margin-bottom:16px;
    }
    .card-label {
        color:#475569; font-size:10px; text-transform:uppercase;
        letter-spacing:0.12em; font-weight:700; margin-bottom:8px;
    }

    /* HEADER */
    .app-title {
        font-size:24px; font-weight:800;
        background:linear-gradient(90deg,#22d3ee,#818cf8);
        -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin:0;
    }
    .app-subtitle { color:#475569; font-size:12px; font-family:'JetBrains Mono',monospace; letter-spacing:0.05em; }
    .app-badge { border:1px solid rgba(56,189,248,0.4); color:#38bdf8; background:rgba(56,189,248,0.08); padding:4px 12px; border-radius:20px; font-size:11px; font-family:'JetBrains Mono',monospace; font-weight:600; }

    /* METRICS */
    [data-testid="stMetric"] {
        background:linear-gradient(160deg, rgba(255,255,255,0.045), rgba(255,255,255,0.012));
        border:1px solid rgba(148,163,184,0.13); border-radius:14px;
        padding:16px 18px 12px; box-shadow:0 6px 20px rgba(0,0,0,0.28);
    }
    [data-testid="stMetricLabel"] { color:#475569 !important; font-size:10px !important; text-transform:uppercase; letter-spacing:0.1em; font-weight:700 !important; }
    [data-testid="stMetricValue"] { color:#f1f5f9 !important; font-size:24px !important; font-weight:800 !important; font-family:'JetBrains Mono',monospace; }

    /* INPUT */
    div[data-testid="stTextInput"] div[data-baseweb="input"] { background:#070b12 !important; border:1px solid rgba(148,163,184,0.22) !important; border-radius:10px !important; }
    div[data-testid="stTextInput"] div[data-baseweb="input"] > div { background:#070b12 !important; }
    .stTextInput input, div[data-testid="stTextInput"] input {
        background:#070b12 !important; color:#f1f5f9 !important;
        -webkit-text-fill-color:#f1f5f9 !important; border:none !important;
        font-family:'JetBrains Mono',monospace !important; font-size:15px !important;
        font-weight:600 !important; caret-color:#38bdf8 !important;
    }
    .stTextInput input::placeholder { color:#334155 !important; -webkit-text-fill-color:#334155 !important; }
    label[data-testid="stWidgetLabel"] p { color:#475569 !important; font-size:10px !important; text-transform:uppercase; letter-spacing:0.1em; font-weight:700 !important; }

    /* BUTTON */
    .stButton button {
        background:linear-gradient(90deg,#0ea5e9,#6366f1); color:white;
        border-radius:10px; font-weight:700; height:2.8rem; border:none;
        transition:transform 0.15s ease, box-shadow 0.15s ease;
        box-shadow:0 4px 16px rgba(56,189,248,0.2);
    }
    .stButton button:hover { transform:translateY(-1px); box-shadow:0 8px 24px rgba(56,189,248,0.3); }

    /* VERDICT BADGE */
    .verdict-badge {
        display:inline-block; padding:8px 20px; border-radius:26px;
        font-size:18px; font-weight:800; letter-spacing:0.05em;
        font-family:'JetBrains Mono',monospace; border:1.5px solid currentColor;
    }

    /* SCORE RING */
    .score-ring-wrap { text-align:center; padding:10px 0; }
    .score-number { font-family:'JetBrains Mono',monospace; font-size:48px; font-weight:800; }
    .score-label { color:#64748b; font-size:11px; text-transform:uppercase; letter-spacing:0.1em; }

    /* SECTION HEAD */
    .section-head { display:flex; align-items:center; gap:10px; margin:20px 0 10px; color:#475569; font-size:11px; text-transform:uppercase; letter-spacing:0.12em; font-weight:700; }
    .section-line { flex:1; height:1px; background:linear-gradient(90deg,rgba(148,163,184,0.25),transparent); }

    /* BULL/BEAR */
    .bull-item { background:rgba(52,211,153,0.07); border:1px solid rgba(52,211,153,0.2); color:#a7f3d0; padding:9px 13px; border-radius:9px; margin-bottom:7px; font-size:13px; }
    .bear-item { background:rgba(248,113,113,0.07); border:1px solid rgba(248,113,113,0.2); color:#fecaca; padding:9px 13px; border-radius:9px; margin-bottom:7px; font-size:13px; }

    /* TABS */
    .stTabs [data-baseweb="tab-list"] { background:rgba(255,255,255,0.02); border-radius:10px; padding:4px; gap:2px; }
    .stTabs [data-baseweb="tab"] { color:#475569 !important; border-radius:8px !important; font-size:12px !important; font-weight:600 !important; }
    .stTabs [aria-selected="true"] { background:rgba(56,189,248,0.12) !important; color:#38bdf8 !important; }

    /* DATAFRAME */
    [data-testid="stDataFrame"] { border-radius:12px; overflow:hidden; }

    hr { border-color:rgba(148,163,184,0.1); }
    </style>
    """, unsafe_allow_html=True)

def section_head(label):
    st.markdown(f'<div class="section-head">{label}<div class="section-line"></div></div>', unsafe_allow_html=True)

# ============================================================================
# TICKER STRIP
# ============================================================================

@st.cache_data(ttl=120)
def fetch_ticker_strip():
    rows = []
    for sym in TICKER_STRIP_SYMBOLS:
        try:
            t = yf.Ticker(sym)
            fi = t.fast_info
            price = fi.get("lastPrice") or fi.get("last_price")
            prev  = fi.get("previousClose") or fi.get("regularMarketPreviousClose")
            if price and prev and prev != 0:
                rows.append({"symbol": sym.replace("^",""), "price": price, "chg": (price-prev)/prev*100})
        except Exception:
            pass
    return rows

def render_ticker_strip(rows):
    if not rows:
        return
    items = ""
    for r in rows:
        cls = "ticker-up" if r["chg"] >= 0 else "ticker-down"
        arrow = "▲" if r["chg"] >= 0 else "▼"
        items += (f'<span class="ticker-item"><span class="ticker-sym">{r["symbol"]}</span>'
                  f'{r["price"]:.2f} <span class="{cls}">{arrow}{r["chg"]:+.2f}%</span></span>')
    st.markdown(f'<div class="ticker-wrap"><div class="ticker-move">{items}{items}</div></div>',
                unsafe_allow_html=True)

# ============================================================================
# DATA FETCH — all cached
# ============================================================================

def _inject_roce(df):
    df = df.copy()
    if all(x in df.index for x in ['EBIT','Total Assets','Current Liabilities']):
        ce = df.loc['Total Assets'] - df.loc['Current Liabilities']
        df.loc['ROCE %'] = (df.loc['EBIT'] / ce.replace(0, np.nan)) * 100
    return df

@st.cache_data(ttl=3600)
def fetch_statements(ticker):
    s = yf.Ticker(ticker)
    ann = pd.concat([s.financials, s.balance_sheet, s.cashflow])
    qtr = pd.concat([s.quarterly_financials, s.quarterly_balance_sheet, s.quarterly_cashflow])
    for df in [ann, qtr]:
        df = df[~df.index.duplicated(keep='first')]
        df = df.loc[:, ~df.columns.duplicated()]
    ann = ann[~ann.index.duplicated(keep='first')]; ann = ann.loc[:, ~ann.columns.duplicated()]
    qtr = qtr[~qtr.index.duplicated(keep='first')]; qtr = qtr.loc[:, ~qtr.columns.duplicated()]
    return _inject_roce(ann), _inject_roce(qtr)

@st.cache_data(ttl=1800)
def fetch_price_and_info(ticker):
    s = yf.Ticker(ticker)
    hist = s.history(period="2y")
    try:    info = s.info
    except: info = {}
    return hist, info

@st.cache_data(ttl=3600)
def fetch_extended(ticker):
    s = yf.Ticker(ticker)
    out = {}
    for attr, key in [('insider_transactions','itx'),('institutional_holders','inst'),
                       ('earnings_history','ehist'),('earnings_dates','edates')]:
        try:    out[key] = getattr(s, attr)
        except: out[key] = pd.DataFrame()
    return out

@st.cache_data(ttl=900)
def fetch_news_raw(ticker):
    try:
        return yf.Ticker(ticker).news or []
    except:
        return []

@st.cache_data(ttl=3600)
def fetch_options_data(ticker):
    try:
        s = yf.Ticker(ticker)
        exps = s.options
        if not exps: return None
        exp = exps[0]
        ch = s.option_chain(exp)
        calls, puts = ch.calls, ch.puts
        call_oi = calls['openInterest'].fillna(0).sum()
        put_oi  = puts['openInterest'].fillna(0).sum()
        call_vol= calls['volume'].fillna(0).sum()
        put_vol = puts['volume'].fillna(0).sum()

        # Max pain
        strikes = sorted(set(calls['strike'].tolist() + puts['strike'].tolist()))
        pain_values = []
        for s_price in strikes:
            call_pain = ((s_price - calls['strike']).clip(lower=0) * calls['openInterest'].fillna(0)).sum()
            put_pain  = ((puts['strike'] - s_price).clip(lower=0) * puts['openInterest'].fillna(0)).sum()
            pain_values.append((s_price, call_pain + put_pain))
        max_pain = min(pain_values, key=lambda x: x[1])[0] if pain_values else None

        avg_iv_call = round(calls['impliedVolatility'].mean()*100,1) if 'impliedVolatility' in calls else None
        avg_iv_put  = round(puts['impliedVolatility'].mean()*100,1)  if 'impliedVolatility' in puts  else None

        return {
            'expiry': exp, 'call_oi': int(call_oi), 'put_oi': int(put_oi),
            'call_vol': int(call_vol), 'put_vol': int(put_vol),
            'pc_oi_ratio': round(put_oi/call_oi,2) if call_oi else None,
            'pc_vol_ratio': round(put_vol/call_vol,2) if call_vol else None,
            'avg_iv_call': avg_iv_call, 'avg_iv_put': avg_iv_put,
            'max_pain': max_pain,
        }
    except:
        return None

@st.cache_data(ttl=1800)
def fetch_macro_data():
    out = {}
    symbols = {'VIX':'^VIX','10Y Yield':'^TNX','2Y Yield':'^IRX','Dollar':'DX-Y.NYB','Gold':'GC=F','Oil':'CL=F'}
    for label, sym in symbols.items():
        try:
            h = yf.Ticker(sym).history(period='5d')
            if not h.empty:
                v = float(h['Close'].iloc[-1])
                if '2Y' in label or '10Y' in label: v = v/10
                out[label] = round(v,2)
        except:
            out[label] = None
    # Yield curve spread
    try:
        if out.get('10Y Yield') and out.get('2Y Yield'):
            out['Curve Spread (10Y-2Y)'] = round(out['10Y Yield'] - out['2Y Yield'], 2)
    except:
        pass
    return out

@st.cache_data(ttl=3600)
def fetch_sec_filings(ticker):
    headers = {"User-Agent": "Bloomberg-Terminal-Research contact@research.com"}
    try:
        r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=headers, timeout=8)
        data = r.json()
        cik = None
        for _, row in data.items():
            if row.get("ticker","").upper() == ticker.upper():
                cik = str(row["cik_str"]).zfill(10)
                break
        if not cik: return []
        r2 = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=headers, timeout=8)
        recent = r2.json().get("filings",{}).get("recent",{})
        forms = recent.get("form",[]); dates = recent.get("filingDate",[]); accs = recent.get("accessionNumber",[])
        filings = []
        for form, date, acc in zip(forms, dates, accs):
            if form in ("10-K","10-Q","8-K","4","DEF 14A"):
                acc_nd = acc.replace("-","")
                url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nd}/"
                filings.append({"form":form,"date":date,"url":url})
            if len(filings) >= 8: break
        return filings
    except:
        return []

# ============================================================================
# RATIO ENGINE — from Institutional Terminal (proven, correct)
# ============================================================================

def _sg(df, row, idx=0):
    try:    return df.loc[row].iloc[idx]
    except: return np.nan

def _pct(a, b):
    if pd.isna(a) or pd.isna(b) or b==0: return np.nan
    return round((a-b)/abs(b)*100,1)

def _rpct(n,d):
    if pd.isna(n) or pd.isna(d) or d==0: return np.nan
    return round(n/d*100,1)

def _sdiv(n,d):
    if pd.isna(n) or pd.isna(d) or d==0: return np.nan
    return round(n/d,2)

def ttm(ann, qtr, item):
    q = qtr.sort_index(axis=1, ascending=False)
    if item in q.index:
        v = q.loc[item].dropna()
        if len(v)>=4: return v.iloc[:4].sum()
    return _sg(ann.sort_index(axis=1,ascending=False), item, 0)

def ttm_prior(ann, qtr, item):
    q = qtr.sort_index(axis=1, ascending=False)
    if item in q.index:
        v = q.loc[item].dropna()
        if len(v)>=8: return v.iloc[4:8].sum()
    return _sg(ann.sort_index(axis=1,ascending=False), item, 1)

def snap(ann, qtr, item):
    q = qtr.sort_index(axis=1,ascending=False); a = ann.sort_index(axis=1,ascending=False)
    qd = q.columns[0] if len(q.columns)>0 else None
    ad = a.columns[0] if len(a.columns)>0 else None
    cands = []
    if item in q.index and qd is not None:
        v=q.loc[item].iloc[0]
        if not pd.isna(v): cands.append((qd,v))
    if item in a.index and ad is not None:
        v=a.loc[item].iloc[0]
        if not pd.isna(v): cands.append((ad,v))
    if not cands: return np.nan
    return sorted(cands, key=lambda x:x[0], reverse=True)[0][1]

def snap_prior(ann, qtr, item):
    q = qtr.sort_index(axis=1,ascending=False)
    if item in q.index:
        v = q.loc[item].dropna()
        if len(v)>=5: return v.iloc[4]
    return _sg(ann.sort_index(axis=1,ascending=False), item, 1)

def compute_ratios(ann, qtr):
    rev=ttm(ann,qtr,'Total Revenue'); rev_p=ttm_prior(ann,qtr,'Total Revenue')
    gp=ttm(ann,qtr,'Gross Profit'); ni=ttm(ann,qtr,'Net Income')
    ebit=ttm(ann,qtr,'EBIT'); ebitda=ttm(ann,qtr,'EBITDA')
    eps=ttm(ann,qtr,'Diluted EPS'); eps_p=ttm_prior(ann,qtr,'Diluted EPS')
    int_exp=ttm(ann,qtr,'Interest Expense')
    debt=snap(ann,qtr,'Total Debt'); eq=snap(ann,qtr,'Stockholders Equity')
    ca=snap(ann,qtr,'Current Assets'); cl=snap(ann,qtr,'Current Liabilities')
    inv=snap(ann,qtr,'Inventory'); cash=snap(ann,qtr,'Cash And Cash Equivalents')
    ta=snap(ann,qtr,'Total Assets')
    sh_now=snap(ann,qtr,'Ordinary Shares Number'); sh_p=snap_prior(ann,qtr,'Ordinary Shares Number')
    ce = (ta-cl) if not pd.isna(ta) and not pd.isna(cl) else np.nan
    roce = round(_sdiv(ebit,ce)*100,1) if not pd.isna(_sdiv(ebit,ce)) else np.nan
    ebit_p=ttm_prior(ann,qtr,'EBIT')
    ta_p=snap_prior(ann,qtr,'Total Assets'); cl_p=snap_prior(ann,qtr,'Current Liabilities')
    ce_p=(ta_p-cl_p) if not pd.isna(ta_p) and not pd.isna(cl_p) else np.nan
    roce_p=round(_sdiv(ebit_p,ce_p)*100,1) if not pd.isna(_sdiv(ebit_p,ce_p)) else np.nan
    qa = (ca-inv) if not pd.isna(ca) and not pd.isna(inv) else np.nan
    return {
        'Revenue ($B)': round(rev/1e9,2) if not pd.isna(rev) else np.nan,
        'Revenue YoY %': _pct(rev,rev_p),
        'Gross Margin %': _rpct(gp,rev),
        'Net Margin %': _rpct(ni,rev),
        'EBITDA Margin %': _rpct(ebitda,rev),
        'EPS YoY %': _pct(eps,eps_p),
        'ROCE %': roce,
        'ROCE YoY Δ': round(roce-roce_p,1) if not pd.isna(roce) and not pd.isna(roce_p) else np.nan,
        'Debt/Equity': _sdiv(debt,eq),
        'Interest Coverage': _sdiv(ebit,int_exp),
        'Current Ratio': _sdiv(ca,cl),
        'Quick Ratio': _sdiv(qa,cl),
        'Cash/Debt': _sdiv(cash,debt),
        'Equity Ratio %': _rpct(eq,ta),
        'Share Count YoY %': _pct(sh_now,sh_p),
        'FCF ($B)': round(ttm(ann,qtr,'Free Cash Flow')/1e9,2) if not pd.isna(ttm(ann,qtr,'Free Cash Flow')) else np.nan,
    }

# ============================================================================
# PILLAR SCORING (from Institutional Terminal)
# ============================================================================

PILLAR_SCORING = {
    "Quality":  [('Revenue YoY %',(10,0),True),('EPS YoY %',(10,0),True),
                  ('Net Margin %',(15,5),True),('EBITDA Margin %',(20,10),True),('ROCE %',(20,10),True)],
    "Safety":   [('Debt/Equity',(0.5,1.5),False),('Interest Coverage',(8,3),True),('Current Ratio',(1.5,1.0),True)],
    "Liquidity":[('Quick Ratio',(1.0,0.5),True),('Cash/Debt',(0.5,0.2),True)],
    "Capital":  [('Equity Ratio %',(50,30),True),('Share Count YoY %',(-1,1),False)],
}

def score_metric(val, thresholds, higher):
    if pd.isna(val): return None
    s,m = thresholds
    if higher:  return 2 if val>=s else 1 if val>=m else 0
    else:       return 2 if val<=s else 1 if val<=m else 0

def score_pillars(ratios):
    out = {}
    for pillar, metrics in PILLAR_SCORING.items():
        scores, detail = [], []
        for name, thr, h in metrics:
            v = ratios.get(name, np.nan)
            s = score_metric(v, thr, h)
            detail.append((name, v, s))
            if s is not None: scores.append(s)
        if scores:
            avg = sum(scores)/len(scores)
            pct_sc = round(avg/2*100)
            verd = "Strong" if avg>=1.5 else "Moderate" if avg>=0.75 else "Weak"
        else:
            pct_sc, verd = None, "No Data"
        out[pillar] = {'score':pct_sc,'verdict':verd,'detail':detail}
    return out

def roce_trend_flag(qtr, lookback=3):
    q = qtr.sort_index(axis=1,ascending=False)
    if 'ROCE %' not in q.index: return False, []
    series = q.loc['ROCE %'].dropna()
    if len(series)<lookback+1: return False, list(series.items())[:lookback]
    recent = series.iloc[:lookback+1].iloc[::-1]
    vals = recent.tolist()
    declining = all(vals[i]>vals[i+1] for i in range(len(vals)-1))
    return declining, [(c.strftime('%Y-%m-%d'), round(v,1)) for c,v in recent.items()]

# ============================================================================
# ENHANCED TECHNICAL ENGINE — MACD, ATR, BB, RS vs SPY
# ============================================================================

def compute_technicals(hist):
    if hist is None or hist.empty or len(hist)<50:
        return None
    close = hist['Close']; volume = hist.get('Volume', pd.Series(dtype=float))

    # Moving averages
    sma20  = close.rolling(20).mean()
    sma50  = close.rolling(50).mean()
    sma200 = close.rolling(200).mean() if len(close)>=200 else pd.Series([np.nan]*len(close))
    price  = float(close.iloc[-1])

    # RSI
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rsi   = (100 - 100/(1 + gain/loss.replace(0,np.nan))).iloc[-1]

    # MACD
    ema12 = close.ewm(span=12).mean(); ema26 = close.ewm(span=26).mean()
    macd_line   = ema12 - ema26
    macd_signal = macd_line.ewm(span=9).mean()
    macd_hist   = macd_line - macd_signal
    macd_val    = float(macd_line.iloc[-1])
    macd_sig    = float(macd_signal.iloc[-1])
    macd_trend  = "Bullish" if macd_val > macd_sig else "Bearish"

    # ATR
    if 'High' in hist.columns and 'Low' in hist.columns:
        tr = pd.concat([hist['High']-hist['Low'],
                        (hist['High']-close.shift()).abs(),
                        (hist['Low']-close.shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
    else:
        atr = np.nan

    # Bollinger Bands
    bb_mid  = float(sma20.iloc[-1])
    bb_std  = float(close.rolling(20).std().iloc[-1])
    bb_up   = bb_mid + 2*bb_std
    bb_low  = bb_mid - 2*bb_std
    bb_pct  = round((price - bb_low)/(bb_up - bb_low)*100,1) if bb_up!=bb_low else 50

    # Trend classification
    s50  = float(sma50.iloc[-1])  if not pd.isna(sma50.iloc[-1])  else price
    s200 = float(sma200.iloc[-1]) if not pd.isna(sma200.iloc[-1]) else price
    if price > s50 > s200:   trend = "Strong Uptrend"
    elif price > s50:         trend = "Uptrend"
    elif price < s50 < s200:  trend = "Strong Downtrend"
    elif price < s50:         trend = "Downtrend"
    else:                     trend = "Sideways"

    # RSI label
    rsi_note = "Overbought" if rsi>=70 else "Oversold" if rsi<=30 else "Neutral"

    # Technical score 0-100
    tech_score = 50
    if "Uptrend" in trend:  tech_score += 20
    elif "Downtrend" in trend: tech_score -= 20
    if macd_trend=="Bullish": tech_score += 10
    else:                      tech_score -= 10
    if 40<=rsi<=65:            tech_score += 10
    elif rsi>70 or rsi<30:     tech_score -= 10
    if bb_pct < 80:            tech_score += 5
    tech_score = max(0, min(100, tech_score))

    return {
        'price': price, 'sma20': round(bb_mid,2), 'sma50': round(s50,2), 'sma200': round(s200,2),
        'rsi': round(rsi,1), 'rsi_note': rsi_note,
        'macd': round(macd_val,3), 'macd_signal': round(macd_sig,3), 'macd_trend': macd_trend,
        'atr': round(atr,2) if not pd.isna(atr) else None,
        'bb_upper': round(bb_up,2), 'bb_lower': round(bb_low,2), 'bb_pct': bb_pct,
        'trend': trend, 'tech_score': tech_score,
        'close': close, 'sma50_series': sma50, 'sma200_series': sma200,
    }

@st.cache_data(ttl=3600)
def fetch_relative_strength(ticker):
    """Relative strength vs SPY — is this stock outperforming the market?"""
    try:
        data = yf.download([ticker,"SPY"], period="1y", progress=False, auto_adjust=True)['Close']
        if ticker not in data.columns or 'SPY' not in data.columns: return None
        stock_ret = data[ticker].pct_change().dropna()
        spy_ret   = data['SPY'].pct_change().dropna()
        rs = (1+stock_ret).cumprod() / (1+spy_ret).cumprod()
        rs_now   = float(rs.iloc[-1])
        rs_trend = "Outperforming" if rs.iloc[-1]>rs.iloc[-20] else "Underperforming"
        return {'rs_ratio': round(rs_now,3), 'trend': rs_trend, 'series': rs}
    except:
        return None

# ============================================================================
# NEWS SENTIMENT ENGINE
# ============================================================================

POS_WORDS = {"beat","beats","surge","soar","rally","growth","record","strong","upgrade","outperform",
             "bullish","gain","profit","expand","win","boost","positive","raises","exceed","innovation",
             "breakthrough","partnership","deal","acquire","momentum","optimistic","success","high","higher"}
NEG_WORDS = {"miss","misses","plunge","slump","crash","decline","downgrade","underperform","bearish",
             "loss","cut","layoff","lawsuit","investigation","fraud","recall","weak","warning","concern",
             "fall","drop","low","lower","negative","sued","fine","delay","shortfall","trouble","risk"}

def score_sentiment(text):
    words = set(w.strip(".,!?:;()'\"").lower() for w in text.split())
    pos = len(words & POS_WORDS); neg = len(words & NEG_WORDS)
    if pos+neg==0: return 0.0
    return (pos-neg)/(pos+neg)

def analyze_news(raw_news):
    articles = []; total = 0.0
    for item in raw_news[:15]:
        try:
            content = item.get("content", item)
            title   = content.get("title") or item.get("title","")
            if not title: continue
            pub  = (content.get("provider",{}).get("displayName") if isinstance(content.get("provider"),dict)
                    else item.get("publisher",""))
            link = (content.get("canonicalUrl",{}).get("url") if isinstance(content.get("canonicalUrl"),dict)
                    else item.get("link","")) or ""
            sc = score_sentiment(title)
            articles.append({"title":title,"publisher":pub,"link":link,"score":round(sc,2)})
            total += sc
        except:
            pass
    avg = total/len(articles) if articles else 0.0
    label = "Positive 🟢" if avg>0.15 else "Negative 🔴" if avg<-0.15 else "Neutral 🟡"
    return {"articles":articles, "avg":round(avg,2), "label":label}

# ============================================================================
# EARNINGS INTELLIGENCE ENGINE
# ============================================================================

def analyze_earnings_intelligence(ticker, tech_score=50, fund_score=50):
    s = yf.Ticker(ticker)
    result = {
        "next_date":"Unknown","consensus_eps":None,"revision_signal":"Unknown",
        "beat_rate":None,"avg_surprise":None,"history":[],
        "avg_move_pct":None,"implied_move_pct":None,"short_pct":None,
        "EPS_Beat":50.0,"probability_notes":[],
    }
    try:
        cal = s.calendar
        if isinstance(cal,dict):
            ed = cal.get("Earnings Date")
            if isinstance(ed,list) and ed: result["next_date"] = str(ed[0])[:10]
            elif ed: result["next_date"] = str(ed)[:10]
            if cal.get("Earnings Average"): result["consensus_eps"] = cal["Earnings Average"]
    except: pass
    try:
        rev = s.eps_revisions
        if rev is not None and not rev.empty:
            col = next((c for c in rev.columns if "current" in str(c).lower() or str(c)=="0q"), rev.columns[0])
            idx_l = [str(i).lower() for i in rev.index]
            up7 = next((rev.iloc[i][col] for i,l in enumerate(idx_l) if "up" in l and "7" in l), None)
            dn7 = next((rev.iloc[i][col] for i,l in enumerate(idx_l) if "down" in l and "7" in l), None)
            if up7 is not None and dn7 is not None:
                result["revision_signal"] = ("Bullish ↑" if up7>dn7 else "Bearish ↓" if dn7>up7 else "Neutral")
    except: pass
    try:
        ed_df = s.earnings_dates
        if ed_df is not None and not ed_df.empty and "Reported EPS" in ed_df.columns:
            past = ed_df.dropna(subset=["Reported EPS"]).head(8)
            beats,total,surps = 0,0,[]
            for idx,row in past.iterrows():
                rep = row.get("Reported EPS"); est = row.get("EPS Estimate")
                if rep is not None and est is not None and not pd.isna(rep) and not pd.isna(est):
                    total+=1
                    if rep>est: beats+=1
                    if est!=0: surps.append((rep-est)/abs(est)*100)
                    result["history"].append({"Quarter":str(idx.date() if hasattr(idx,'date') else idx)[:10],
                                               "Est":round(float(est),2),"Reported":round(float(rep),2),
                                               "Beat":("✅" if rep>est else "❌")})
            if total>0: result["beat_rate"]=round(beats/total*100,1)
            if surps:   result["avg_surprise"]=round(sum(surps)/len(surps),2)
    except: pass
    try:
        info = s.info
        spf = info.get("shortPercentOfFloat")
        if spf: result["short_pct"] = round(spf*100,2)
    except: pass
    # Compute composite probability
    prob = 50.0
    if result["beat_rate"] is not None:
        prob += (result["beat_rate"]-50)*0.4
        result["probability_notes"].append(f"historical beat rate {result['beat_rate']}%")
    if "Bullish" in result["revision_signal"]:
        prob += 8; result["probability_notes"].append("estimates rising")
    elif "Bearish" in result["revision_signal"]:
        prob -= 8; result["probability_notes"].append("estimates falling")
    prob += (tech_score-50)*0.12 + (fund_score-50)*0.12
    result["EPS_Beat"] = round(max(5, min(95, prob)), 1)
    return result

# ============================================================================
# FORENSIC RED FLAGS
# ============================================================================

def forensic_checks(ann, qtr):
    ni=ttm(ann,qtr,'Net Income'); ocf=ttm(ann,qtr,'Operating Cash Flow')
    ta=snap(ann,qtr,'Total Assets'); gw=snap(ann,qtr,'Goodwill')
    rev=ttm(ann,qtr,'Total Revenue'); rev_p=ttm_prior(ann,qtr,'Total Revenue')
    ar=snap(ann,qtr,'Accounts Receivable'); ar_p=snap_prior(ann,qtr,'Accounts Receivable')
    flags = []
    accrual = (ni-ocf)/ta*100 if not any(pd.isna(x) for x in [ni,ocf,ta]) and ta!=0 else np.nan
    gw_pct  = gw/ta*100       if not any(pd.isna(x) for x in [gw,ta]) and ta!=0 else np.nan
    ar_gr   = _pct(ar,ar_p); rev_gr = _pct(rev,rev_p)
    if not pd.isna(accrual) and accrual>5:
        flags.append(f"High accruals ratio {accrual:.1f}% — earnings quality concern")
    if not pd.isna(gw_pct) and gw_pct>30:
        flags.append(f"Goodwill {gw_pct:.0f}% of assets — impairment risk")
    if not pd.isna(ar_gr) and not pd.isna(rev_gr) and ar_gr>rev_gr+15:
        flags.append(f"Receivables ({ar_gr}%) growing faster than revenue ({rev_gr}%) — channel stuffing risk")
    return {'accrual':round(accrual,1) if not pd.isna(accrual) else None,
            'gw_pct': round(gw_pct,1)  if not pd.isna(gw_pct)  else None,
            'ar_gr':ar_gr,'rev_gr':rev_gr,'flags':flags}

# ============================================================================
# VALUATION & DCF
# ============================================================================

def valuation_timing(hist, info, verdict):
    if hist is None or hist.empty: return None
    price = float(hist['Close'].iloc[-1])
    hi = float(hist['Close'].max()); lo = float(hist['Close'].min())
    pos = (price-lo)/(hi-lo)*100 if hi!=lo else 50
    zone = ("Value Zone" if pos<=33 else "Fair Zone" if pos<=66 else "Extended Zone")
    if verdict=="BUY" and pos<=40: action="ENTRY ✅"
    elif verdict=="BUY" and pos>75: action="WAIT — price extended"
    elif "AVOID" in verdict and pos>60: action="EXIT / TRIM ⚠️"
    else: action="HOLD — monitor"
    return {'price':price,'hi':hi,'lo':lo,'pos_pct':round(pos,1),'zone':zone,'action':action,
            'pe':info.get('trailingPE'),'fpe':info.get('forwardPE')}

def valuation_multiples(info):
    return {k:info.get(v) for k,v in {
        'P/E (TTM)':'trailingPE','P/E (Fwd)':'forwardPE',
        'P/S (TTM)':'priceToSalesTrailing12Months','P/B':'priceToBook',
        'EV/EBITDA':'enterpriseToEbitda','PEG':'pegRatio'}.items()}

def dcf_model(ann, qtr, info, growth, discount, terminal, years=5):
    fcf = ttm(ann,qtr,'Free Cash Flow')
    if pd.isna(fcf):
        ocf=ttm(ann,qtr,'Operating Cash Flow'); capex=ttm(ann,qtr,'Capital Expenditure')
        if not pd.isna(ocf) and not pd.isna(capex): fcf=ocf+capex
    if pd.isna(fcf) or fcf<=0 or discount<=terminal: return None
    debt=snap(ann,qtr,'Total Debt'); cash_=snap(ann,qtr,'Cash And Cash Equivalents')
    shares = info.get('sharesOutstanding') or snap(ann,qtr,'Ordinary Shares Number')
    if not shares or pd.isna(shares): return None
    pv_sum=0; proj=[]
    for t in range(1,years+1):
        ft=fcf*(1+growth)**t; pv=ft/(1+discount)**t
        pv_sum+=pv; proj.append({'Year':t,'FCF ($B)':round(ft/1e9,3),'PV ($B)':round(pv/1e9,3)})
    tv=fcf*(1+growth)**years*(1+terminal)/(discount-terminal)
    pv_tv=tv/(1+discount)**years
    ev=pv_sum+pv_tv
    nd=(debt if not pd.isna(debt) else 0)-(cash_ if not pd.isna(cash_) else 0)
    fair=(ev-nd)/shares
    return {'fair_value':round(fair,2),'ev_b':round(ev/1e9,2),
            'tv_pct':round(pv_tv/ev*100,1) if ev else None,'proj':proj}

# ============================================================================
# ANALYST ENGINE
# ============================================================================

def analyst_data(info):
    tgt=info.get('targetMeanPrice'); cur=info.get('currentPrice') or info.get('regularMarketPrice')
    upside = round((tgt-cur)/cur*100,1) if tgt and cur and cur!=0 else None
    return {
        'Recommendation':info.get('recommendationKey','n/a'),
        'Mean Rating':info.get('recommendationMean'),
        '# Analysts':info.get('numberOfAnalystOpinions'),
        'Target Mean':tgt,'Target High':info.get('targetHighPrice'),
        'Target Low':info.get('targetLowPrice'),'Implied Upside %':upside,
    }

def ownership_data(info, insider_tx):
    ins  = info.get('heldPercentInsiders')
    inst = info.get('heldPercentInstitutions')
    result = {
        'Institutional Ownership %': round(inst*100,1) if inst and not pd.isna(inst) else None,
        'Insider Ownership %':       round(ins*100,1)  if ins  and not pd.isna(ins)  else None,
    }
    try:
        if insider_tx is not None and not insider_tx.empty:
            recent = insider_tx.head(10)
            for col in ['Transaction','Text','transactionText']:
                if col in recent.columns:
                    buys  = recent[col].astype(str).str.contains('Buy',  case=False,na=False).sum()
                    sells = recent[col].astype(str).str.contains('Sale|Sell',case=False,na=False).sum()
                    result['Recent Insider Activity']=f"{buys} buys / {sells} sells"
                    break
    except: pass
    return result

def short_interest_data(info):
    spf = info.get('shortPercentOfFloat')
    spo = info.get('sharesPercentSharesOut')
    si  = info.get('shortRatio')
    squeeze_score = None
    if spf and not pd.isna(spf):
        spf_pct = spf*100
        squeeze_score = min(100, round(spf_pct*4 + (1/si*20 if si and si>0 else 0)))
    return {
        'Short % Float': round(spf*100,2) if spf and not pd.isna(spf) else None,
        'Days to Cover': info.get('shortRatio'),
        'Short % Shares Out': round(spo*100,2) if spo and not pd.isna(spo) else None,
        'Squeeze Score /100': squeeze_score,
    }

# ============================================================================
# INSTITUTIONAL DECISION ENGINE — 100-point scoring brain
# ============================================================================

def institutional_decision_score(ratios, pillar_results, val, analyst, ownership,
                                   short_interest, technical, earnings_intel):
    score = 0; breakdown = {}

    # 1. Business Quality (30 pts)
    q = pillar_results.get("Quality",{}).get("score") or 0
    bq = round(q * 0.30)
    breakdown["Business Quality"] = bq; score += bq

    # 2. Financial Safety (15 pts)
    s = pillar_results.get("Safety",{}).get("score") or 0
    fs = round(s * 0.15)
    breakdown["Financial Safety"] = fs; score += fs

    # 3. Growth (15 pts)
    gr = 0
    rev_g = ratios.get("Revenue YoY %", np.nan)
    eps_g = ratios.get("EPS YoY %",     np.nan)
    if not pd.isna(rev_g): gr += (8 if rev_g>15 else 5 if rev_g>5 else 2 if rev_g>0 else 0)
    if not pd.isna(eps_g): gr += (7 if eps_g>15 else 4 if eps_g>5 else 2 if eps_g>0 else 0)
    breakdown["Growth"] = gr; score += gr

    # 4. Valuation (10 pts)
    vl = 0
    if val:
        pos = val.get("pos_pct", 100)
        vl += (6 if pos<30 else 4 if pos<50 else 2 if pos<70 else 0)
        pe  = val.get("pe")
        if pe and not pd.isna(pe):
            vl += (4 if pe<18 else 3 if pe<25 else 1 if pe<40 else 0)
    breakdown["Valuation"] = vl; score += vl

    # 5. Analyst Sentiment (10 pts)
    al = 0
    upside = analyst.get("Implied Upside %")
    rec    = str(analyst.get("Recommendation","")).lower()
    if upside and not pd.isna(upside):
        al += (6 if upside>25 else 4 if upside>10 else 2 if upside>0 else 0)
    if "strong_buy" in rec or "strong buy" in rec: al += 4
    elif "buy" in rec: al += 3
    elif "hold" in rec: al += 1
    breakdown["Analyst Sentiment"] = min(al,10); score += min(al,10)

    # 6. Earnings Intelligence (10 pts)
    ei = 0
    beat_rate = earnings_intel.get("beat_rate")
    rev_sig   = earnings_intel.get("revision_signal","")
    if beat_rate is not None: ei += (6 if beat_rate>=75 else 4 if beat_rate>=60 else 2 if beat_rate>=50 else 0)
    if "Bullish" in rev_sig: ei += 4
    elif "Bearish" in rev_sig: ei -= 2
    breakdown["Earnings Intelligence"] = max(0,min(ei,10)); score += max(0,min(ei,10))

    # 7. Ownership (5 pts)
    ow = 0
    inst_pct = ownership.get("Institutional Ownership %")
    if inst_pct and not pd.isna(inst_pct):
        ow = (5 if inst_pct>70 else 3 if inst_pct>40 else 1)
    breakdown["Institutional Ownership"] = ow; score += ow

    # 8. Short Interest (5 pts)
    sh = 0
    si_pct = short_interest.get("Short % Float")
    if si_pct and not pd.isna(si_pct):
        sh = (5 if si_pct<3 else 4 if si_pct<5 else 2 if si_pct<10 else 0)
    breakdown["Short Interest"] = sh; score += sh

    # 9. Technical Momentum (5 pts)
    tc = 0
    if technical:
        trend = technical.get("trend","")
        rsi   = technical.get("rsi", 50)
        macd  = technical.get("macd_trend","")
        if "Strong Uptrend" in trend: tc += 3
        elif "Uptrend" in trend:      tc += 2
        if macd=="Bullish": tc += 1
        if 40<=rsi<=65:     tc += 1
    breakdown["Technical Momentum"] = min(tc,5); score += min(tc,5)

    score = max(0, min(100, round(score)))

    if score>=88:    verdict="STRONG BUY"
    elif score>=74:  verdict="BUY"
    elif score>=58:  verdict="HOLD"
    elif pillar_results.get("Safety",{}).get("verdict")=="Weak": verdict="AVOID / HIGH RISK"
    else:            verdict="AVOID"

    grade = "A" if score>=85 else "B" if score>=70 else "C" if score>=55 else "D" if score>=40 else "F"

    return score, verdict, grade, breakdown

# ============================================================================
# AI THESIS GENERATOR
# ============================================================================

def generate_thesis(ticker, verdict, ratios, pillar_results, val, analyst,
                     technical, forensic, earnings_intel, macro, score):
    lines = []
    vcolor = VERDICT_COLORS.get(verdict,"#94a3b8")
    lines.append(f"**{ticker} — {verdict} (Score {score}/100)**")

    qual = pillar_results.get("Quality",{})
    safe = pillar_results.get("Safety",{})
    lines.append(f"Business quality is **{qual.get('verdict','N/A')}** "
                 f"(ROCE {ratios.get('ROCE %','N/A')}%, net margin {ratios.get('Net Margin %','N/A')}%, "
                 f"revenue growth {ratios.get('Revenue YoY %','N/A')}%). "
                 f"Balance sheet safety is **{safe.get('verdict','N/A')}** "
                 f"(D/E {ratios.get('Debt/Equity','N/A')}, interest coverage {ratios.get('Interest Coverage','N/A')}x).")

    beat = earnings_intel.get("beat_rate")
    rev_sig = earnings_intel.get("revision_signal","Unknown")
    if beat: lines.append(f"Earnings track record: **{beat}% historical beat rate** over last 8 quarters. "
                           f"Analyst estimate revisions: **{rev_sig}**.")

    if val: lines.append(f"Price (${val['price']:.2f}) is in the **{val['zone']}** of its 2-year range "
                          f"({val['pos_pct']}% position). Action signal: **{val['action']}**.")

    if analyst.get('Implied Upside %'):
        lines.append(f"Street consensus: **{analyst.get('Recommendation','N/A')}** from "
                     f"{analyst.get('# Analysts','?')} analysts. Mean target ${analyst.get('Target Mean','N/A')}, "
                     f"implied upside **{analyst.get('Implied Upside %','N/A')}%**.")

    if technical: lines.append(f"Technical picture: **{technical.get('trend','N/A')}**, "
                                f"RSI {technical.get('rsi','N/A')} ({technical.get('rsi_note','N/A')}), "
                                f"MACD **{technical.get('macd_trend','N/A')}**.")

    if macro.get("Curve Spread (10Y-2Y)") is not None:
        curve = macro["Curve Spread (10Y-2Y)"]
        env = "inverted (recession risk)" if curve<0 else "normal (expansion)"
        lines.append(f"Macro: VIX {macro.get('VIX','N/A')}, yield curve {curve:.2f}% ({env}), "
                     f"dollar {macro.get('Dollar','N/A')}.")

    if forensic['flags']: lines.append(f"⚠️ Forensic flags: {'; '.join(forensic['flags'])}.")
    else:                  lines.append("✅ No forensic red flags triggered.")

    return "\n\n".join(lines)

# ============================================================================
# SELF-LEARNING CALIBRATION
# ============================================================================

def compute_calibration(ticker):
    rows = get_prediction_history(ticker, limit=30)
    if len(rows)<2: return None
    try:
        hist = yf.download(ticker, period="1y", progress=False, auto_adjust=True)['Close']
        if isinstance(hist, pd.DataFrame): hist=hist.iloc[:,0]
    except: return None
    hits=0; evaluated=0
    for date_str, verdict, score, price_at in rows:
        try:
            pred_date = pd.to_datetime(date_str)
            fwd = hist.index[hist.index>=pred_date]
            if len(fwd)<10: continue
            actual_up = float(hist.loc[fwd[10]])>float(hist.loc[fwd[0]])
            pred_up   = verdict in ("STRONG BUY","BUY")
            if actual_up==pred_up: hits+=1
            evaluated+=1
        except: continue
    if evaluated==0: return None
    return {'accuracy':round(hits/evaluated*100,1),'sample':evaluated}

# ============================================================================
# PORTFOLIO ENGINE
# ============================================================================

@st.cache_data(ttl=3600)
def fetch_portfolio_prices(tickers, period='1y'):
    tickers_with_spy = list(dict.fromkeys(list(tickers)+['SPY']))
    data={}
    for t in tickers_with_spy:
        try:
            h=yf.Ticker(t).history(period=period)
            if not h.empty: data[t]=h['Close']
        except: pass
    return pd.DataFrame(data).dropna(how='all') if data else None

def compute_portfolio_analytics(price_df, holdings):
    if price_df is None or price_df.empty: return None
    rets = price_df.pct_change().dropna(how='all')
    results = []
    total_val = 0
    for tk, shares, cost in holdings:
        if tk not in price_df.columns: continue
        price = float(price_df[tk].dropna().iloc[-1])
        val   = shares*price; pl=(price-cost)*shares; pl_pct=(price-cost)/cost*100 if cost else 0
        beta  = np.nan
        if 'SPY' in rets.columns and tk in rets.columns:
            aligned=rets[[tk,'SPY']].dropna()
            if len(aligned)>=20:
                beta=round(aligned[tk].cov(aligned['SPY'])/aligned['SPY'].var(),2)
        results.append({'Ticker':tk,'Shares':shares,'Price':round(price,2),
                        'Value':round(val,2),'Cost':cost,'P/L':round(pl,2),
                        'P/L %':round(pl_pct,1),'Beta':beta})
        total_val+=val
    if not results: return None
    df = pd.DataFrame(results)
    # Sector allocation (best-effort from yfinance info)
    sectors={}
    for tk in df['Ticker']:
        try:
            sec = yf.Ticker(tk).info.get('sector','Unknown')
            w   = float(df.loc[df['Ticker']==tk,'Value'].values[0])
            sectors[sec] = sectors.get(sec,0)+w
        except: pass
    correlation=None
    valid=[t for t in df['Ticker'] if t in rets.columns]
    if len(valid)>=2:
        correlation=rets[valid].corr()
    return {'holdings':df,'total_value':total_val,'sectors':sectors,'correlation':correlation}

# ============================================================================
# CHARTS
# ============================================================================

def make_price_chart(hist, technical, ticker):
    close = technical['close']; sma50 = technical['sma50_series']; sma200 = technical['sma200_series']
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=close.index, y=close, mode='lines', name=ticker,
                              line=dict(color='#38bdf8',width=2),
                              fill='tozeroy', fillcolor='rgba(56,189,248,0.06)'))
    fig.add_trace(go.Scatter(x=sma50.index, y=sma50, mode='lines', name='SMA50',
                              line=dict(color='#facc15',width=1.2,dash='dot')))
    fig.add_trace(go.Scatter(x=sma200.index, y=sma200, mode='lines', name='SMA200',
                              line=dict(color='#a78bfa',width=1.2,dash='dot')))
    fig.update_layout(height=320, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      font=dict(color='#94a3b8'), margin=dict(l=10,r=10,t=10,b=10),
                      legend=dict(bgcolor='rgba(0,0,0,0)',font=dict(size=11),orientation='h'),
                      xaxis=dict(gridcolor='rgba(148,163,184,0.07)'),
                      yaxis=dict(gridcolor='rgba(148,163,184,0.07)'))
    return fig

def make_gauge(value, title, color):
    fig = go.Figure(go.Indicator(
        mode='gauge+number', value=value,
        number=dict(font=dict(color='#f1f5f9',family='JetBrains Mono',size=30)),
        title=dict(text=title, font=dict(color='#64748b',size=11)),
        gauge=dict(axis=dict(range=[0,100],tickcolor='#334155',tickfont=dict(color='#475569',size=9)),
                   bar=dict(color=color,thickness=0.25), bgcolor='rgba(0,0,0,0)',
                   borderwidth=1, bordercolor='rgba(148,163,184,0.2)',
                   steps=[dict(range=[0,40],color='rgba(248,113,113,0.08)'),
                          dict(range=[40,70],color='rgba(250,204,21,0.08)'),
                          dict(range=[70,100],color='rgba(52,211,153,0.08)')])))
    fig.update_layout(height=210, margin=dict(l=15,r=15,t=35,b=5),
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return fig

def make_score_breakdown_chart(breakdown):
    items = sorted(breakdown.items(), key=lambda x:x[1])
    labels=[k for k,v in items]; vals=[v for k,v in items]
    colors=['#34d399' if v>=7 else '#facc15' if v>=4 else '#f87171' for v in vals]
    fig = go.Figure(go.Bar(x=vals, y=labels, orientation='h',
                            marker=dict(color=colors, line=dict(width=0)),
                            text=[f"{v}" for v in vals], textposition='outside',
                            textfont=dict(color='#e2e8f0',size=12)))
    fig.update_layout(height=280, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      font=dict(color='#94a3b8'), margin=dict(l=10,r=40,t=10,b=10),
                      xaxis=dict(range=[0,max(vals)+3],gridcolor='rgba(148,163,184,0.07)'),
                      yaxis=dict(gridcolor='rgba(0,0,0,0)'))
    return fig

# ============================================================================
# PEER COMPARISON
# ============================================================================

@st.cache_data(ttl=3600)
def fetch_peer_snapshot(peer_ticker):
    try:
        info = yf.Ticker(peer_ticker).info
        return {
            'Ticker':peer_ticker,
            'Price':info.get('currentPrice') or info.get('regularMarketPrice'),
            'Market Cap ($B)':round(info.get('marketCap',0)/1e9,1),
            'P/E (TTM)':info.get('trailingPE'),
            'P/E (Fwd)':info.get('forwardPE'),
            'EV/EBITDA':info.get('enterpriseToEbitda'),
            'Rev Growth %':info.get('revenueGrowth',0) and round(info.get('revenueGrowth',0)*100,1),
            'Net Margin %':info.get('profitMargins',0) and round(info.get('profitMargins',0)*100,1),
        }
    except: return None

# ============================================================================
# MAIN UI
# ============================================================================

def main():
    st.set_page_config(page_title="Bloomberg AI Terminal", page_icon="◆", layout="wide")
    inject_css()

    # Header
    h1, h2 = st.columns([4,1])
    with h1:
        st.markdown(f"""
        <p class="app-title">◆ Bloomberg AI Institutional Terminal</p>
        <p class="app-subtitle">AI-POWERED RESEARCH & DECISION ENGINE · {datetime.datetime.now().strftime('%A %d %B %Y')}</p>
        """, unsafe_allow_html=True)
    with h2:
        st.markdown('<div style="text-align:right;padding-top:8px;"><span class="app-badge">MASTER v2.0</span></div>',
                    unsafe_allow_html=True)

    # Ticker strip
    with st.spinner(""):
        strip = fetch_ticker_strip()
    render_ticker_strip(strip)

    # Mode selector
    mode = st.radio("", ["📊 Single Stock", "📁 My Portfolio"], horizontal=True, label_visibility="collapsed")

    if mode == "📊 Single Stock":
        run_single_stock()
    else:
        run_portfolio()

# ============================================================================
# SINGLE STOCK MODE
# ============================================================================

def run_single_stock():
    col1, col2, col3 = st.columns([3,1,1])
    with col1: ticker = st.text_input("SYMBOL", "AMD").upper()
    with col2:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        analyze = st.button("⚡ Generate Report", use_container_width=True)
    with col3:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("🔄 Clear Cache", use_container_width=True):
            st.cache_data.clear(); st.rerun()

    if not analyze: return

    # ---- FETCH ----
    with st.spinner(f"Pulling intelligence on {ticker}..."):
        try:
            ann, qtr  = fetch_statements(ticker)
            hist, info= fetch_price_and_info(ticker)
            ext       = fetch_extended(ticker)
            raw_news  = fetch_news_raw(ticker)
            opts      = fetch_options_data(ticker)
            macro     = fetch_macro_data()
        except Exception as e:
            st.error(f"Data fetch error: {e}"); return

    if ann.empty:
        st.error("No financial data returned — check the ticker symbol."); return

    # ---- COMPUTE ----
    ratios     = compute_ratios(ann, qtr)
    pillars    = score_pillars(ratios)
    roce_dec, roce_series = roce_trend_flag(qtr)
    val        = valuation_timing(hist, info, "HOLD")   # preliminary
    analyst    = analyst_data(info)
    ownership  = ownership_data(info, ext.get('itx'))
    short_int  = short_interest_data(info)
    technical  = compute_technicals(hist)
    forensic   = forensic_checks(ann, qtr)
    news_intel = analyze_news(raw_news)

    with st.spinner("Running earnings intelligence..."):
        earnings_intel = analyze_earnings_intelligence(
            ticker,
            technical['tech_score'] if technical else 50,
            pillars.get("Quality",{}).get("score") or 50
        )

    # Institutional Decision Score
    inst_score, verdict, grade, breakdown = institutional_decision_score(
        ratios, pillars, val, analyst, ownership, short_int, technical, earnings_intel
    )
    val = valuation_timing(hist, info, verdict)  # recompute with real verdict

    # Thesis
    thesis = generate_thesis(ticker, verdict, ratios, pillars, val, analyst,
                              technical, forensic, earnings_intel, macro, inst_score)

    # Save to memory
    price_now = technical['price'] if technical else 0
    save_prediction(ticker, verdict, inst_score, price_now)

    # ---- COMPANY CARD ----
    vcolor = VERDICT_COLORS.get(verdict, "#94a3b8")
    name   = info.get("longName", ticker)
    sector = info.get("sector","Unknown")
    industry = info.get("industry","Unknown")
    mktcap = info.get("marketCap",0)
    mktcap_str = f"${mktcap/1e12:.2f}T" if mktcap>1e12 else f"${mktcap/1e9:.1f}B" if mktcap else "N/A"

    st.markdown(f"""
    <div class="glass-card">
        <div class="card-label">{sector} · {industry} · Market Cap {mktcap_str}</div>
        <h2 style="margin:4px 0 10px;">{name} <span style="color:#475569;font-size:16px;">({ticker})</span></h2>
        <span class="verdict-badge" style="color:{vcolor};background:{vcolor}18;">{verdict}</span>
        &nbsp;&nbsp;<span style="font-family:'JetBrains Mono';color:#64748b;font-size:14px;">
        Grade <b style="color:{vcolor};">{grade}</b> · Score {inst_score}/100</span>
    </div>
    """, unsafe_allow_html=True)

    # ---- ALERTS ----
    if roce_dec:
        st.warning(f"⚠️ ROCE declining 3+ quarters: " + " → ".join(f"{d}: {v}%" for d,v in roce_series))
    if forensic['flags']:
        for f in forensic['flags']: st.error(f"🚩 {f}")

    # ---- SCORE GAUGES ----
    section_head("Institutional Decision Score")
    g1,g2,g3,g4 = st.columns(4)
    with g1: st.plotly_chart(make_gauge(inst_score,"INSTITUTIONAL SCORE",vcolor), use_container_width=True)
    with g2: st.plotly_chart(make_gauge(pillars.get("Quality",{}).get("score") or 0,"BUSINESS QUALITY","#34d399"), use_container_width=True)
    with g3: st.plotly_chart(make_gauge(earnings_intel.get("EPS_Beat",50),"EARNINGS BEAT PROB","#22d3ee"), use_container_width=True)
    with g4:
        safety_score = 100-(short_int.get("Short % Float") or 0)*3
        safety_score = max(0,min(100,safety_score))
        st.plotly_chart(make_gauge(safety_score,"SAFETY SCORE","#a78bfa"), use_container_width=True)

    # Score breakdown bar
    section_head("Score Breakdown by Factor")
    bc1,bc2 = st.columns([3,2])
    with bc1: st.plotly_chart(make_score_breakdown_chart(breakdown), use_container_width=True)
    with bc2:
        st.markdown('<div class="glass-card"><div class="card-label">Factor Scores</div>', unsafe_allow_html=True)
        for factor, pts in sorted(breakdown.items(), key=lambda x:-x[1]):
            bar_color = "#34d399" if pts>=7 else "#facc15" if pts>=4 else "#f87171"
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;align-items:center;
                        margin-bottom:6px;font-size:13px;">
                <span style="color:#cbd5e1;">{factor}</span>
                <span style="font-family:'JetBrains Mono';color:{bar_color};font-weight:700;">{pts}</span>
            </div>""", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="border-top:1px solid rgba(148,163,184,0.15);margin-top:8px;padding-top:8px;
                    display:flex;justify-content:space-between;font-size:15px;">
            <span style="color:#f1f5f9;font-weight:700;">TOTAL</span>
            <span style="font-family:'JetBrains Mono';color:{vcolor};font-weight:800;">{inst_score}/100</span>
        </div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # ---- KEY METRICS ROW ----
    section_head("Key Metrics")
    m1,m2,m3,m4,m5,m6 = st.columns(6)
    with m1: st.metric("Price", f"${price_now:.2f}" if price_now else "N/A")
    with m2: st.metric("Revenue YoY", f"{ratios.get('Revenue YoY %','N/A')}%")
    with m3: st.metric("ROCE", f"{ratios.get('ROCE %','N/A')}%")
    with m4: st.metric("Net Margin", f"{ratios.get('Net Margin %','N/A')}%")
    with m5: st.metric("D/E Ratio", f"{ratios.get('Debt/Equity','N/A')}")
    with m6: st.metric("FCF", f"${ratios.get('FCF ($B)','N/A')}B")

    # ---- AI THESIS ----
    section_head("🤖 AI Investment Thesis")
    st.markdown(f'<div class="glass-card">{thesis.replace(chr(10),"<br>")}</div>', unsafe_allow_html=True)

    # ---- PRICE CHART ----
    if technical:
        section_head("Price Action · 2Y")
        st.markdown('<div class="glass-card" style="padding:14px;">', unsafe_allow_html=True)
        st.plotly_chart(make_price_chart(hist, technical, ticker), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # ================================================================
    # TABS
    # ================================================================
    tabs = st.tabs([
        "📊 Pillars", "🎯 Earnings Intel", "💰 Valuation & DCF",
        "📰 News Sentiment", "📈 Technicals", "🏛️ Ownership",
        "🩳 Short & Options", "🌍 Macro", "🚩 Forensics",
        "⚖️ Peers", "📄 SEC Filings", "🔁 Calibration", "📜 Raw Financials"
    ])

    # ---- TAB 0: PILLARS ----
    with tabs[0]:
        cols = st.columns(4)
        for i,(pillar,res) in enumerate(pillars.items()):
            with cols[i]:
                sc = res['score']
                clr = "#34d399" if (sc or 0)>=70 else "#facc15" if (sc or 0)>=50 else "#f87171"
                st.markdown(f"""<div class="glass-card">
                <div class="card-label">{pillar}</div>
                <div style="font-family:'JetBrains Mono';font-size:28px;font-weight:800;color:{clr};">{sc or 'N/A'}</div>
                <div style="color:{clr};font-size:12px;font-weight:700;margin-bottom:10px;">{res['verdict']}</div>
                """, unsafe_allow_html=True)
                for name,v,s in res['detail']:
                    mk = "✅" if s==2 else "⚠️" if s==1 else "❌" if s==0 else "—"
                    vstr = f"{v:.1f}" if isinstance(v,(int,float)) and not pd.isna(v) else "N/A"
                    st.markdown(f"<div style='font-size:12px;color:#94a3b8;margin-bottom:4px;'>{mk} {name}: <b style='color:#e2e8f0;'>{vstr}</b></div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

    # ---- TAB 1: EARNINGS INTELLIGENCE ----
    with tabs[1]:
        section_head("🎯 Earnings Intelligence Engine")
        ei = earnings_intel
        ea,eb = st.columns(2)
        with ea:
            st.markdown(f"""<div class="glass-card">
            <div class="card-label">Next Report</div>
            <p style="font-family:'JetBrains Mono';font-size:14px;line-height:2.2;">
            Earnings Date &nbsp;<b style="float:right;">{ei.get('next_date','Unknown')}</b><br>
            Consensus EPS &nbsp;<b style="float:right;">{ei.get('consensus_eps','N/A')}</b><br>
            Estimate Trend &nbsp;<b style="float:right;">{ei.get('revision_signal','Unknown')}</b><br>
            Short % Float &nbsp;<b style="float:right;">{ei.get('short_pct','N/A')}%</b>
            </p></div>""", unsafe_allow_html=True)
        with eb:
            br = ei.get('beat_rate')
            br_color = "#34d399" if br and br>=70 else "#facc15" if br and br>=50 else "#f87171"
            st.markdown(f"""<div class="glass-card">
            <div class="card-label">Track Record</div>
            <p style="font-family:'JetBrains Mono';font-size:14px;line-height:2.2;">
            Beat Rate &nbsp;<b style="float:right;color:{br_color};">{br or 'N/A'}%</b><br>
            Avg Surprise &nbsp;<b style="float:right;">{ei.get('avg_surprise','N/A')}%</b><br>
            EPS Beat Probability &nbsp;<b style="float:right;color:#38bdf8;">{ei.get('EPS_Beat',50)}%</b>
            </p></div>""", unsafe_allow_html=True)
        if ei.get('history'):
            st.markdown('<div class="glass-card"><div class="card-label">Last 8 Quarters — Estimate vs Reported</div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(ei['history']), use_container_width=True, hide_index=True)
            st.markdown('</div>', unsafe_allow_html=True)
        if ei.get('probability_notes'):
            st.markdown(f"<p style='color:#64748b;font-size:12px;'>Probability driven by: {', '.join(ei['probability_notes'])}</p>", unsafe_allow_html=True)

    # ---- TAB 2: VALUATION & DCF ----
    with tabs[2]:
        section_head("Valuation Multiples")
        mults = valuation_multiples(info)
        mc = st.columns(6)
        for i,(k,v) in enumerate(mults.items()):
            mc[i].metric(k, f"{v:.2f}" if v and not pd.isna(v) else "N/A")
        if val:
            st.markdown(f"""<div class="glass-card">
            <div class="card-label">2Y Range Position</div>
            <p style="font-family:'JetBrains Mono';font-size:14px;line-height:2;">
            Zone &nbsp;<b style="float:right;">{val['zone']}</b><br>
            Range Position &nbsp;<b style="float:right;">{val['pos_pct']}%</b><br>
            Action &nbsp;<b style="float:right;">{val['action']}</b>
            </p></div>""", unsafe_allow_html=True)

        section_head("DCF Intrinsic Value")
        dc1,dc2,dc3,dc4 = st.columns(4)
        def_g = ratios.get('Revenue YoY %') or 8
        def_g = min(max(def_g/100, 0.02), 0.25)
        g_inp  = dc1.slider("FCF Growth",  0.0, 0.30, float(round(def_g,2)), 0.01, key="dcf_g")
        d_inp  = dc2.slider("Discount (WACC)", 0.05, 0.15, 0.10, 0.005, key="dcf_d")
        t_inp  = dc3.slider("Terminal Growth", 0.0, 0.04, 0.025, 0.0025, key="dcf_t")
        y_inp  = dc4.selectbox("Years", [3,5,7,10], index=1, key="dcf_y")
        dcf = dcf_model(ann, qtr, info, g_inp, d_inp, t_inp, y_inp)
        if dcf:
            mos = round((dcf['fair_value']-price_now)/price_now*100,1) if price_now else None
            r1,r2,r3 = st.columns(3)
            r1.metric("Fair Value / Share", f"${dcf['fair_value']}")
            r2.metric("Current Price",      f"${price_now:.2f}")
            r3.metric("Margin of Safety",   f"{mos}%" if mos else "N/A")
            if mos:
                if mos>=20:   st.success("Below DCF fair value — margin-of-safety territory ✅")
                elif mos<=-20:st.warning("Above DCF fair value — priced for high growth ⚠️")
                else:          st.info("Near DCF fair value — neutral signal")
            st.caption(f"EV ${dcf['ev_b']}B · Terminal value {dcf['tv_pct']}% of EV")
            st.dataframe(pd.DataFrame(dcf['proj']), use_container_width=True, hide_index=True)
        else:
            st.info("DCF unavailable — negative/missing FCF or insufficient data")

    # ---- TAB 3: NEWS SENTIMENT ----
    with tabs[3]:
        ni = news_intel
        sent_color = "#34d399" if "Positive" in ni['label'] else "#f87171" if "Negative" in ni['label'] else "#facc15"
        st.markdown(f"""<div class="glass-card">
        <div class="card-label">Sentiment Summary</div>
        <span style="font-size:20px;font-weight:800;color:{sent_color};">{ni['label']}</span>
        <span style="color:#64748b;font-size:13px;margin-left:12px;">avg score {ni['avg']} · {len(ni['articles'])} headlines</span>
        </div>""", unsafe_allow_html=True)
        for a in ni['articles']:
            sc_clr = "#34d399" if a['score']>0 else "#f87171" if a['score']<0 else "#64748b"
            st.markdown(f"""<div style="padding:8px 0;border-bottom:1px solid rgba(148,163,184,0.08);">
            <a href="{a['link']}" target="_blank" style="color:#e2e8f0;text-decoration:none;font-size:13px;">
            {a['title']}</a>
            <span style="color:#475569;font-size:11px;"> — {a['publisher']}</span>
            <span style="font-family:'JetBrains Mono';font-size:11px;color:{sc_clr};float:right;">
            {'▲' if a['score']>0 else '▼' if a['score']<0 else '●'} {a['score']}</span>
            </div>""", unsafe_allow_html=True)

    # ---- TAB 4: TECHNICALS ----
    with tabs[4]:
        if technical:
            tc1,tc2,tc3,tc4,tc5 = st.columns(5)
            tc1.metric("Price",   f"${technical['price']:.2f}")
            tc2.metric("RSI(14)", f"{technical['rsi']} — {technical['rsi_note']}")
            tc3.metric("MACD",    f"{technical['macd']} ({technical['macd_trend']})")
            tc4.metric("ATR(14)", f"${technical['atr']}" if technical['atr'] else "N/A")
            tc5.metric("BB %",    f"{technical['bb_pct']}%")
            st.markdown(f"""<div class="glass-card">
            <div class="card-label">Technical Analysis</div>
            <p style="font-family:'JetBrains Mono';font-size:14px;line-height:2.2;">
            Trend &nbsp;<b style="float:right;">{technical['trend']}</b><br>
            SMA 50 &nbsp;<b style="float:right;">${technical['sma50']:.2f}</b><br>
            SMA 200 &nbsp;<b style="float:right;">${technical['sma200']:.2f}</b><br>
            BB Upper &nbsp;<b style="float:right;">${technical['bb_upper']:.2f}</b><br>
            BB Lower &nbsp;<b style="float:right;">${technical['bb_lower']:.2f}</b><br>
            Technical Score &nbsp;<b style="float:right;color:#38bdf8;">{technical['tech_score']}/100</b>
            </p></div>""", unsafe_allow_html=True)
            # RS vs SPY
            rs = fetch_relative_strength(ticker)
            if rs:
                rs_clr = "#34d399" if rs['trend']=="Outperforming" else "#f87171"
                st.markdown(f"""<div class="glass-card">
                <div class="card-label">Relative Strength vs SPY</div>
                <span style="color:{rs_clr};font-size:16px;font-weight:700;">{rs['trend']}</span>
                <span style="color:#64748b;font-size:13px;margin-left:10px;">RS Ratio {rs['rs_ratio']}</span>
                </div>""", unsafe_allow_html=True)
        else:
            st.info("Not enough price history for technical analysis (need 50+ days).")

    # ---- TAB 5: OWNERSHIP ----
    with tabs[5]:
        oa,ob = st.columns(2)
        with oa:
            st.markdown('<div class="glass-card"><div class="card-label">Ownership Breakdown</div>', unsafe_allow_html=True)
            for k,v in ownership.items():
                vstr = f"{v}" if v else "N/A"
                st.markdown(f"<div style='font-size:13px;color:#94a3b8;margin-bottom:6px;'>{k}: <b style='color:#e2e8f0;float:right;'>{vstr}</b></div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
        with ob:
            inst_holders = ext.get('inst')
            if inst_holders is not None and not inst_holders.empty:
                st.markdown('<div class="glass-card"><div class="card-label">Top Institutional Holders</div>', unsafe_allow_html=True)
                for _,row in inst_holders.head(8).iterrows():
                    holder = row.get('Holder','Unknown')
                    shares = row.get('Shares')
                    shares_str = f"{int(shares/1e6):.1f}M" if shares and not pd.isna(shares) else "N/A"
                    st.markdown(f"<div style='font-size:12px;color:#94a3b8;margin-bottom:5px;'>🏛️ {holder} <b style='float:right;color:#e2e8f0;'>{shares_str} shares</b></div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

    # ---- TAB 6: SHORT & OPTIONS ----
    with tabs[6]:
        sa,sb = st.columns(2)
        with sa:
            st.markdown('<div class="glass-card"><div class="card-label">Short Interest</div>', unsafe_allow_html=True)
            for k,v in short_int.items():
                vstr = f"{v}" if v is not None else "N/A"
                sq_clr = ("#f87171" if k=="Short % Float" and v and v>10
                           else "#facc15" if k=="Short % Float" and v and v>5 else "#e2e8f0")
                st.markdown(f"<div style='font-size:13px;color:#94a3b8;margin-bottom:6px;'>{k}: <b style='color:{sq_clr};float:right;'>{vstr}</b></div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
        with sb:
            if opts:
                pcr_color = "#f87171" if (opts.get('pc_oi_ratio') or 0)>1 else "#34d399"
                st.markdown(f"""<div class="glass-card">
                <div class="card-label">Options Flow — {opts['expiry']}</div>
                <p style="font-family:'JetBrains Mono';font-size:13px;line-height:2.2;">
                Put/Call OI &nbsp;<b style="float:right;color:{pcr_color};">{opts.get('pc_oi_ratio','N/A')}</b><br>
                Put/Call Vol &nbsp;<b style="float:right;">{opts.get('pc_vol_ratio','N/A')}</b><br>
                Call OI &nbsp;<b style="float:right;">{opts.get('call_oi','N/A'):,}</b><br>
                Put OI &nbsp;<b style="float:right;">{opts.get('put_oi','N/A'):,}</b><br>
                Avg Call IV % &nbsp;<b style="float:right;">{opts.get('avg_iv_call','N/A')}</b><br>
                Avg Put IV % &nbsp;<b style="float:right;">{opts.get('avg_iv_put','N/A')}</b><br>
                Max Pain &nbsp;<b style="float:right;color:#facc15;">${opts.get('max_pain','N/A')}</b>
                </p></div>""", unsafe_allow_html=True)
            else:
                st.info("No options data available for this ticker.")

    # ---- TAB 7: MACRO ----
    with tabs[7]:
        section_head("Macro Environment")
        macro_labels = list(macro.items())
        mc_cols = st.columns(min(len(macro_labels),4))
        for i,(k,v) in enumerate(macro_labels):
            mc_cols[i%4].metric(k, f"{v}" if v else "N/A")
        curve = macro.get("Curve Spread (10Y-2Y)")
        if curve is not None:
            if curve<0:
                st.error(f"⚠️ Yield curve inverted ({curve:.2f}%) — historically a recession leading indicator")
            else:
                st.success(f"✅ Yield curve normal ({curve:.2f}%) — expansion environment")
        vix_val = macro.get("VIX")
        if vix_val:
            vix_regime = "Low / Calm" if vix_val<15 else "Elevated / Caution" if vix_val<25 else "High / Stress"
            st.info(f"VIX {vix_val} — {vix_regime}")

    # ---- TAB 8: FORENSICS ----
    with tabs[8]:
        fc1,fc2,fc3,fc4 = st.columns(4)
        fc1.metric("Accruals Ratio %", forensic['accrual'] or "N/A")
        fc2.metric("Goodwill/Assets %",forensic['gw_pct'] or "N/A")
        fc3.metric("Receivables YoY %",forensic['ar_gr'] or "N/A")
        fc4.metric("Revenue YoY %",    forensic['rev_gr'] or "N/A")
        if forensic['flags']:
            for f in forensic['flags']: st.error(f"🚩 {f}")
        else:
            st.success("✅ No forensic red flags detected on current thresholds.")

    # ---- TAB 9: PEERS ----
    with tabs[9]:
        peers = PEER_MAP.get(ticker, [])
        if peers:
            with st.spinner("Pulling peer data..."):
                rows = [fetch_peer_snapshot(p) for p in peers]
                rows = [r for r in rows if r]
            if rows:
                st.dataframe(pd.DataFrame(rows).set_index('Ticker'), use_container_width=True)
            else:
                st.info("Could not fetch peer data.")
        else:
            custom = st.text_input("Enter peer tickers (comma-separated):")
            if st.button("Compare"):
                peer_list = [t.strip().upper() for t in custom.split(",") if t.strip()]
                rows = [fetch_peer_snapshot(p) for p in peer_list]
                rows = [r for r in rows if r]
                if rows: st.dataframe(pd.DataFrame(rows).set_index('Ticker'), use_container_width=True)

    # ---- TAB 10: SEC FILINGS ----
    with tabs[10]:
        with st.spinner("Fetching SEC EDGAR filings..."):
            filings = fetch_sec_filings(ticker)
        if filings:
            for f in filings:
                badge_color = {"10-K":"#38bdf8","10-Q":"#34d399","8-K":"#facc15",
                               "4":"#a78bfa","DEF 14A":"#fb923c"}.get(f['form'],"#94a3b8")
                st.markdown(f"""<div style="padding:8px 0;border-bottom:1px solid rgba(148,163,184,0.08);">
                <span style="font-family:'JetBrains Mono';font-weight:700;color:{badge_color};">{f['form']}</span>
                <span style="color:#64748b;font-size:12px;margin-left:10px;">{f['date']}</span>
                <a href="{f['url']}" target="_blank" style="float:right;color:#38bdf8;font-size:12px;">View on EDGAR →</a>
                </div>""", unsafe_allow_html=True)
        else:
            st.info("SEC filings unavailable — ticker may not be a US public company, or EDGAR lookup failed.")

    # ---- TAB 11: CALIBRATION ----
    with tabs[11]:
        calib = compute_calibration(ticker)
        history = get_prediction_history(ticker)
        if calib:
            st.metric("Directional Accuracy (10-day forward)", f"{calib['accuracy']}%",
                      f"over {calib['sample']} past predictions")
        else:
            st.info("Not enough prediction history yet — run analyses over multiple sessions to build calibration data.")
        if history:
            df_hist = pd.DataFrame(history, columns=["Date","Verdict","Score","Price at Prediction"])
            df_hist["Date"] = pd.to_datetime(df_hist["Date"]).dt.strftime("%b %d, %H:%M")
            st.dataframe(df_hist, use_container_width=True, hide_index=True)

    # ---- TAB 12: RAW FINANCIALS ----
    with tabs[12]:
        ann_s = ann.sort_index(axis=1,ascending=False)
        st.subheader("Annual")
        st.dataframe(ann_s.iloc[:, :4].applymap(lambda x: round(x/1e9,3) if isinstance(x,(int,float)) and not pd.isna(x) and abs(x)>1e6 else x),
                     use_container_width=True)
        qtr_s = qtr.sort_index(axis=1,ascending=False)
        st.subheader("Quarterly")
        st.dataframe(qtr_s.iloc[:,:6].applymap(lambda x: round(x/1e9,3) if isinstance(x,(int,float)) and not pd.isna(x) and abs(x)>1e6 else x),
                     use_container_width=True)
        st.caption("Values in $B where applicable")

# ============================================================================
# PORTFOLIO MODE
# ============================================================================

def run_portfolio():
    st.markdown('<div class="glass-card"><div class="card-label">Holdings — one per line: TICKER, SHARES, COST_BASIS</div>', unsafe_allow_html=True)
    default_holdings = "META,50,320\nGOOGL,20,140\nPLTR,100,25\nNVDA,10,500\nAMD,30,120"
    holdings_text = st.text_area("", default_holdings, height=130, label_visibility="collapsed")
    st.markdown("</div>", unsafe_allow_html=True)

    if not st.button("⚡ Analyze Portfolio", use_container_width=True): return

    holdings = []
    for line in holdings_text.strip().split("\n"):
        parts = [p.strip() for p in line.split(",")]
        if len(parts)>=2 and parts[0]:
            try:
                tk=parts[0].upper(); sh=float(parts[1])
                cost=float(parts[2]) if len(parts)>2 and parts[2] else 0.0
                holdings.append((tk,sh,cost))
            except: continue

    if not holdings: st.error("No valid holdings found."); return

    tickers = [h[0] for h in holdings]
    with st.spinner("Pulling portfolio data..."):
        price_df = fetch_portfolio_prices(tuple(tickers))
        analytics = compute_portfolio_analytics(price_df, holdings)

    if not analytics: st.error("Could not compute portfolio analytics."); return

    df = analytics['holdings']
    total_val = analytics['total_value']
    total_pl  = df['P/L'].sum()

    # Summary metrics
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Total Value",    f"${total_val:,.0f}")
    m2.metric("Total P/L",      f"${total_pl:,.0f}")
    m3.metric("Positions",      len(df))
    avg_beta = df['Beta'].mean() if df['Beta'].notna().any() else None
    m4.metric("Portfolio Beta", f"{avg_beta:.2f}" if avg_beta else "N/A")

    section_head("Holdings")
    st.dataframe(df.set_index('Ticker'), use_container_width=True)

    # Sector exposure
    section_head("Sector Allocation")
    if analytics['sectors']:
        sec_df = pd.DataFrame(list(analytics['sectors'].items()), columns=['Sector','Value'])
        sec_df['Weight %'] = (sec_df['Value']/total_val*100).round(1)
        sec_df = sec_df.sort_values('Weight %', ascending=False)
        sc1,sc2 = st.columns([2,3])
        with sc1: st.dataframe(sec_df.set_index('Sector'), use_container_width=True)
        with sc2:
            fig = go.Figure(go.Pie(
                labels=sec_df['Sector'], values=sec_df['Weight %'],
                hole=0.5, textfont=dict(size=11),
                marker=dict(colors=['#38bdf8','#34d399','#a78bfa','#facc15','#fb923c','#f87171','#22d3ee'])))
            fig.update_layout(height=250, paper_bgcolor='rgba(0,0,0,0)', margin=dict(l=0,r=0,t=0,b=0),
                               showlegend=True, legend=dict(font=dict(color='#94a3b8',size=10)))
            st.plotly_chart(fig, use_container_width=True)

    # Correlation
    if analytics.get('correlation') is not None:
        section_head("Correlation Matrix (1Y Returns)")
        st.dataframe(analytics['correlation'].round(2), use_container_width=True)

if __name__ == "__main__":
    main()