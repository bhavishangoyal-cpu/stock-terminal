# ============================================================================
# BLOOMBERG AI INSTITUTIONAL TERMINAL — FINAL v4.0
# Single File Edition
# Free sources: yfinance · OpenBB 4.x · FRED · SEC EDGAR · FMP · Tiingo
# ============================================================================
import datetime,math,sqlite3,warnings,re,io
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf
warnings.filterwarnings("ignore")
pd.set_option("future.no_silent_downcasting",True)

APP_VERSION="FINAL v4.0"
TICKER_STRIP=["SPY","QQQ","^VIX","^TNX","DX-Y.NYB","GC=F","CL=F","BTC-USD","^GSPC"]
VERDICT_COLORS={"STRONG BUY":"#22d3ee","BUY":"#34d399","HOLD":"#facc15",
    "AVOID":"#fb923c","AVOID / HIGH RISK":"#f87171","NO DATA":"#94a3b8"}
PEER_MAP={
    "NVDA":["AMD","AVGO","INTC","QCOM"],"AMD":["NVDA","INTC","QCOM","AVGO"],
    "TSLA":["RIVN","GM","F","STLA"],"GOOG":["META","MSFT","AMZN"],
    "GOOGL":["META","MSFT","AMZN"],"META":["GOOGL","SNAP","PINS","RDDT"],
    "MSFT":["GOOGL","AMZN","ORCL","CRM"],"AAPL":["MSFT","GOOGL","DELL"],
    "AMZN":["WMT","TGT","GOOGL","MSFT"],"PLTR":["SNOW","AI","MDB","DDOG"],
    "ASTS":["RKLB","IRDM","GSAT"],"RKLB":["ASTS","SPCE","LUNR"],
    "ORCL":["MSFT","SAP","CRM","NOW"],"CRM":["MSFT","ORCL","NOW","WDAY"],
    "V":["MA","AXP","PYPL","SQ"],"JPM":["BAC","WFC","C","GS"],
    "NFLX":["DIS","WBD","PARA","ROKU"],"UBER":["LYFT","DASH","ABNB"],
    "SNOW":["DDOG","MDB","PLTR","AI"],"NOW":["CRM","WDAY","ORCL","ADBE"],
    "ADBE":["CRM","NOW","MSFT"],"INTC":["AMD","NVDA","AVGO","ARM"],
    "BA":["LMT","RTX","NOC","GD"],"XOM":["CVX","COP","SLB"],
    "JNJ":["PFE","MRK","ABT","BMY"],"PFE":["JNJ","MRK","ABBV","LLY"],
    "COIN":["MSTR","HOOD","SQ","PYPL"],"SHOP":["AMZN","WIX","ETSY"],
}
FMP_API_KEY="lxQA8BfErgcKkzfmKKXGPYWv5Y5uJsF9"   # free key: financialmodelingprep.com
TIINGO_API_KEY="675faa17e5b4477baf75fa29f2cdb425cdde2f99"

# ── MEMORY ──
@st.cache_resource
def get_memory():
    conn=sqlite3.connect("bloomberg_v4.db",check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS predictions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT,date TEXT,verdict TEXT,score REAL,price REAL)""")
    conn.commit(); return conn

def save_pred(ticker,verdict,score,price):
    try:
        c=get_memory()
        c.execute("INSERT INTO predictions(ticker,date,verdict,score,price) VALUES(?,?,?,?,?)",
            (ticker,str(datetime.datetime.now()),verdict,score,price)); c.commit()
    except: pass

def get_preds(ticker,limit=30):
    try:
        return get_memory().execute(
            "SELECT date,verdict,score,price FROM predictions WHERE ticker=? ORDER BY id DESC LIMIT ?",
            (ticker,limit)).fetchall()
    except: return []

# ── CSS ──
def inject_css():
    st.markdown("""<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');
    html,body,[class*="css"]{font-family:'Inter',sans-serif;}
    .stApp{background:radial-gradient(circle at 10% 0%,rgba(56,189,248,0.07),transparent 40%),
        radial-gradient(circle at 90% 5%,rgba(129,140,248,0.07),transparent 40%),
        linear-gradient(180deg,#03050a 0%,#080c14 50%,#04060c 100%);color:#e2e8f0;}
    .block-container{padding-top:0.5rem;padding-bottom:2rem;max-width:1500px;}
    #MainMenu,footer,header{visibility:hidden;}
    h1,h2,h3,h4{color:#f8fafc!important;font-weight:700!important;letter-spacing:-0.01em;}
    .ticker-wrap{width:100%;overflow:hidden;background:rgba(255,255,255,0.025);
        border:1px solid rgba(148,163,184,0.12);border-radius:8px;padding:9px 0;margin-bottom:12px;}
    .ticker-move{display:inline-block;animation:ticker-scroll 45s linear infinite;
        font-family:'JetBrains Mono',monospace;font-size:13px;}
    .ticker-wrap:hover .ticker-move{animation-play-state:paused;}
    @keyframes ticker-scroll{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
    .ticker-item{display:inline-block;padding:0 22px;color:#94a3b8;}
    .ticker-up{color:#34d399;}.ticker-down{color:#f87171;}
    .ticker-sym{color:#f8fafc;font-weight:700;margin-right:5px;}
    .glass-card{background:linear-gradient(160deg,rgba(255,255,255,0.045),rgba(255,255,255,0.012));
        border:1px solid rgba(148,163,184,0.13);border-radius:14px;padding:18px 20px;
        box-shadow:0 8px 28px rgba(0,0,0,0.35);margin-bottom:14px;}
    .card-label{color:#475569;font-size:10px;text-transform:uppercase;letter-spacing:0.12em;font-weight:700;margin-bottom:8px;}
    .app-title{font-size:23px;font-weight:800;background:linear-gradient(90deg,#22d3ee,#818cf8);
        -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin:0;}
    .app-subtitle{color:#475569;font-size:11px;font-family:'JetBrains Mono',monospace;letter-spacing:0.05em;}
    .app-badge{border:1px solid rgba(56,189,248,0.4);color:#38bdf8;background:rgba(56,189,248,0.08);
        padding:4px 12px;border-radius:20px;font-size:11px;font-family:'JetBrains Mono',monospace;font-weight:600;}
    [data-testid="stMetric"]{background:linear-gradient(160deg,rgba(255,255,255,0.045),rgba(255,255,255,0.012));
        border:1px solid rgba(148,163,184,0.13);border-radius:14px;padding:14px 16px 10px;box-shadow:0 6px 20px rgba(0,0,0,0.28);}
    [data-testid="stMetricLabel"]{color:#475569!important;font-size:10px!important;text-transform:uppercase;letter-spacing:0.1em;font-weight:700!important;}
    [data-testid="stMetricValue"]{color:#f1f5f9!important;font-size:22px!important;font-weight:800!important;font-family:'JetBrains Mono',monospace;}
    div[data-testid="stTextInput"] div[data-baseweb="input"]{background:#070b12!important;border:1px solid rgba(148,163,184,0.22)!important;border-radius:10px!important;}
    div[data-testid="stTextInput"] div[data-baseweb="input"]>div{background:#070b12!important;}
    .stTextInput input,div[data-testid="stTextInput"] input{background:#070b12!important;color:#f1f5f9!important;
        -webkit-text-fill-color:#f1f5f9!important;border:none!important;font-family:'JetBrains Mono',monospace!important;
        font-size:15px!important;font-weight:600!important;caret-color:#38bdf8!important;}
    .stTextInput input::placeholder{color:#334155!important;-webkit-text-fill-color:#334155!important;}
    label[data-testid="stWidgetLabel"] p{color:#475569!important;font-size:10px!important;text-transform:uppercase;letter-spacing:0.1em;font-weight:700!important;}
    .stButton button{background:linear-gradient(90deg,#0ea5e9,#6366f1);color:white;border-radius:10px;
        font-weight:700;height:2.8rem;border:none;transition:transform 0.15s ease,box-shadow 0.15s ease;
        box-shadow:0 4px 16px rgba(56,189,248,0.2);}
    .stButton button:hover{transform:translateY(-1px);box-shadow:0 8px 24px rgba(56,189,248,0.3);}
    .verdict-badge{display:inline-block;padding:8px 20px;border-radius:26px;font-size:18px;font-weight:800;
        letter-spacing:0.05em;font-family:'JetBrains Mono',monospace;border:1.5px solid currentColor;}
    .section-head{display:flex;align-items:center;gap:10px;margin:18px 0 10px;color:#475569;
        font-size:11px;text-transform:uppercase;letter-spacing:0.12em;font-weight:700;}
    .section-line{flex:1;height:1px;background:linear-gradient(90deg,rgba(148,163,184,0.25),transparent);}
    .stTabs [data-baseweb="tab-list"]{background:rgba(255,255,255,0.02);border-radius:10px;padding:4px;gap:2px;}
    .stTabs [data-baseweb="tab"]{color:#475569!important;border-radius:8px!important;font-size:11px!important;font-weight:600!important;}
    .stTabs [aria-selected="true"]{background:rgba(56,189,248,0.12)!important;color:#38bdf8!important;}
    [data-testid="stDataFrame"]{border-radius:12px;overflow:hidden;}
    hr{border-color:rgba(148,163,184,0.1);}
    </style>""",unsafe_allow_html=True)

def sh(label):
    st.markdown(f'<div class="section-head">{label}<div class="section-line"></div></div>',unsafe_allow_html=True)

# ── TICKER STRIP ──
@st.cache_data(ttl=120)
def fetch_strip():
    rows=[]
    for sym in TICKER_STRIP:
        try:
            fi=yf.Ticker(sym).fast_info
            p=fi.get("lastPrice") or fi.get("last_price")
            pv=fi.get("previousClose") or fi.get("regularMarketPreviousClose")
            if p and pv and pv!=0: rows.append({"s":sym.replace("^",""),"p":p,"c":(p-pv)/pv*100})
        except: pass
    return rows

def render_strip(rows):
    if not rows: return
    items=""
    for r in rows:
        cl="ticker-up" if r["c"]>=0 else "ticker-down"
        ar="▲" if r["c"]>=0 else "▼"
        items+=f'<span class="ticker-item"><span class="ticker-sym">{r["s"]}</span>{r["p"]:.2f} <span class="{cl}">{ar}{r["c"]:+.2f}%</span></span>'
    st.markdown(f'<div class="ticker-wrap"><div class="ticker-move">{items}{items}</div></div>',unsafe_allow_html=True)

# ── OPENBB LAZY LOAD ──
_OBB=None; _OBB_TRIED=False
def obb():
    global _OBB,_OBB_TRIED
    if _OBB_TRIED: return _OBB
    _OBB_TRIED=True
    try:
        from openbb import obb as _o
        _o.user.preferences.output_type="dataframe"; _OBB=_o
    except: _OBB=None
    return _OBB

def _oc(fn,*args,**kwargs):
    try:
        r=fn(*args,**kwargs)
        if r is None: return None
        if hasattr(r,"to_df"): df=r.to_df()
        elif hasattr(r,"results") and r.results:
            df=pd.DataFrame([x.__dict__ if hasattr(x,"__dict__") else x for x in r.results])
        elif isinstance(r,pd.DataFrame): df=r
        else: return None
        return df if not df.empty else None
    except: return None

# ── FMP DIRECT ──
def fmp(ep, params=None):
    """Call FMP API. Works with or without key (free tier has limits)."""
    base = "https://financialmodelingprep.com/api/v3"
    p = params or {}
    if FMP_API_KEY:
        p["apikey"] = FMP_API_KEY
    try:
        r = requests.get(f"{base}/{ep}", params=p, timeout=10)
        if r.status_code == 200:
            data = r.json()
            # FMP returns error dict when key invalid or plan too low
            if isinstance(data, dict) and ("Error Message" in data or "error" in str(data).lower()):
                return None
            return data
        return None
    except: return None

def fmp_key_ok():
    """Check if FMP key is set and working."""
    return bool(FMP_API_KEY and FMP_API_KEY.strip())

# No cache on FMP so key changes work immediately without Clear Cache
def fmp_earnings_cal(t):
    d=fmp(f"historical/earning_calendar/{t}")
    return pd.DataFrame(d[:8]) if d and isinstance(d,list) else None

def fmp_surprises(t):
    d=fmp(f"earnings-surprises/{t}")
    return pd.DataFrame(d[:8]) if d and isinstance(d,list) else None

def fmp_upgrades(t):
    d=fmp(f"upgrades-downgrades/{t}")
    return pd.DataFrame(d[:12]) if d and isinstance(d,list) else None

def fmp_inst(t):
    d=fmp(f"institutional-holder/{t}")
    return pd.DataFrame(d[:15]) if d and isinstance(d,list) else None

def fmp_insider(t):
    d=fmp(f"insider-trading/{t}", {"limit":20})
    return pd.DataFrame(d) if d and isinstance(d,list) else None

def fmp_news(t):
    d=fmp("stock_news", {"tickers":t,"limit":20})
    return pd.DataFrame(d) if d and isinstance(d,list) else None

def fmp_econ_cal():
    today=datetime.date.today().strftime("%Y-%m-%d")
    end=(datetime.date.today()+datetime.timedelta(days=30)).strftime("%Y-%m-%d")
    d=fmp("economic_calendar",{"from":today,"to":end})
    return pd.DataFrame(d) if d and isinstance(d,list) else None

def fmp_ratios(t):
    d=fmp(f"ratios/{t}", {"limit":4})
    return pd.DataFrame(d) if d and isinstance(d,list) else None

def fmp_analyst(t):
    pt=fmp(f"price-target/{t}")
    pt_df=pd.DataFrame(pt[:8]) if pt and isinstance(pt,list) else None
    est=fmp(f"analyst-estimates/{t}")
    est_df=pd.DataFrame(est[:6]) if est and isinstance(est,list) else None
    return {"targets":pt_df,"estimates":est_df}

@st.cache_data(ttl=3600)
def yf_upgrades_downgrades(ticker):
    """Free upgrades/downgrades via yfinance — no API key needed."""
    try:
        s = yf.Ticker(ticker)
        ud = s.upgrades_downgrades
        if ud is not None and not ud.empty:
            ud = ud.reset_index()
            ud = ud.sort_values(ud.columns[0], ascending=False).head(15)
            return ud
    except: pass
    try:
        rec = s.recommendations
        if rec is not None and not rec.empty:
            return rec.reset_index().sort_values(rec.columns[0] if rec.index.name is None else "index", ascending=False).head(15)
    except: pass
    return None

@st.cache_data(ttl=3600)
def yf_recommendations_summary(ticker):
    """Free analyst consensus summary via yfinance."""
    try:
        s = yf.Ticker(ticker)
        rs = s.recommendations_summary
        if rs is not None and not rs.empty:
            return rs
    except: pass
    return None

# ── TIINGO ──
def tiingo_get(ep,params=None):
    if not TIINGO_API_KEY: return None
    hdrs={"Content-Type":"application/json","Authorization":f"Token {TIINGO_API_KEY}"}
    try:
        r=requests.get(f"https://api.tiingo.com/{ep}",params=params,headers=hdrs,timeout=8)
        return r.json() if r.status_code==200 else None
    except: return None

@st.cache_data(ttl=900)
def tiingo_news(t): d=tiingo_get("tiingo/news",{"tickers":t,"limit":20}); return pd.DataFrame(d) if d and isinstance(d,list) else None

# ── OBB CACHED CALLS ──
@st.cache_data(ttl=3600)
def obb_inst(t):
    o=obb()
    if o:
        df=_oc(o.equity.ownership.institutional,t,provider="fmp")
        if df is not None: return df
        df=_oc(o.equity.ownership.institutional,t,provider="yfinance")
        if df is not None: return df
    return None

@st.cache_data(ttl=3600)
def obb_insider_t(t):
    o=obb()
    if o:
        df=_oc(o.equity.ownership.insider_trading,t,provider="fmp")
        if df is not None: return df.head(20)
        df=_oc(o.equity.ownership.insider_trading,t,provider="sec")
        if df is not None: return df.head(20)
    return None

@st.cache_data(ttl=900)
def obb_news(t):
    o=obb()
    if o:
        df=_oc(o.news.company,t,limit=25,provider="benzinga")
        if df is not None: return df
        if TIINGO_API_KEY:
            df=_oc(o.news.company,t,limit=25,provider="tiingo")
            if df is not None: return df
        df=_oc(o.news.company,t,limit=25,provider="yfinance")
        if df is not None: return df
    return None

@st.cache_data(ttl=1800)
def obb_econ_cal():
    o=obb()
    if not o: return None
    s=datetime.datetime.now().strftime("%Y-%m-%d")
    e=(datetime.datetime.now()+datetime.timedelta(days=30)).strftime("%Y-%m-%d")
    df=_oc(o.economy.calendar,start_date=s,end_date=e,provider="econdb")
    return df

@st.cache_data(ttl=60)
def obb_providers():
    o=obb()
    if not o: return {"OpenBB":"Not loaded"}
    result={"OpenBB":"4.7.2 ✅"}
    tests=[("yfinance",lambda:_oc(o.equity.price.quote,"AAPL",provider="yfinance")),
           ("fmp",lambda:_oc(o.equity.fundamental.income,"AAPL",period="annual",limit=1,provider="fmp")),
           ("fred",lambda:_oc(o.economy.fred_series,"FEDFUNDS",provider="fred")),
           ("benzinga",lambda:_oc(o.news.company,"AAPL",limit=1,provider="benzinga")),
           ("sec",lambda:_oc(o.equity.fundamental.filings,symbol="AAPL",provider="sec")),
           ("tiingo",lambda:_oc(o.news.company,"AAPL",limit=1,provider="tiingo"))]
    for name,fn in tests:
        try: r=fn(); result[name]="✅ working" if r is not None else "⚠️ no data"
        except Exception as e: result[name]=f"❌ {str(e)[:50]}"
    return result

# ── DATA FETCH ──
def _roce(df):
    df=df.copy()
    if all(x in df.index for x in ["EBIT","Total Assets","Current Liabilities"]):
        ce=df.loc["Total Assets"]-df.loc["Current Liabilities"]
        df.loc["ROCE %"]=(df.loc["EBIT"]/ce.replace(0,np.nan))*100
    return df

@st.cache_data(ttl=3600)
def fetch_stmts(ticker):
    s=yf.Ticker(ticker)
    ann=pd.concat([s.financials,s.balance_sheet,s.cashflow])
    qtr=pd.concat([s.quarterly_financials,s.quarterly_balance_sheet,s.quarterly_cashflow])
    ann=ann[~ann.index.duplicated(keep="first")]; ann=ann.loc[:,~ann.columns.duplicated()]
    qtr=qtr[~qtr.index.duplicated(keep="first")]; qtr=qtr.loc[:,~qtr.columns.duplicated()]
    return _roce(ann),_roce(qtr)

@st.cache_data(ttl=1800)
def fetch_price_info(ticker):
    s=yf.Ticker(ticker); h=s.history(period="2y")
    try: info=s.info
    except: info={}
    return h,info

@st.cache_data(ttl=3600)
def fetch_ext(ticker):
    s=yf.Ticker(ticker); out={}
    for attr,key in [("insider_transactions","itx"),("institutional_holders","inst"),
                     ("earnings_history","ehist"),("earnings_dates","edates"),
                     ("dividends","divs"),("major_holders","major")]:
        try: out[key]=getattr(s,attr)
        except: out[key]=pd.DataFrame() if key!="divs" else pd.Series(dtype=float)
    return out

@st.cache_data(ttl=900)
def fetch_news_yf(ticker):
    try: return yf.Ticker(ticker).news or []
    except: return []

@st.cache_data(ttl=3600)
def fetch_opts(ticker):
    try:
        s=yf.Ticker(ticker); exps=s.options
        if not exps: return None
        exp=exps[0]; ch=s.option_chain(exp); calls,puts=ch.calls,ch.puts
        coi=calls["openInterest"].fillna(0).sum(); poi=puts["openInterest"].fillna(0).sum()
        cvol=calls["volume"].fillna(0).sum(); pvol=puts["volume"].fillna(0).sum()
        strikes=sorted(set(calls["strike"].tolist()+puts["strike"].tolist()))
        pv=[]
        for sp in strikes:
            cp=((sp-calls["strike"]).clip(lower=0)*calls["openInterest"].fillna(0)).sum()
            pp=((puts["strike"]-sp).clip(lower=0)*puts["openInterest"].fillna(0)).sum()
            pv.append((sp,cp+pp))
        mp=min(pv,key=lambda x:x[1])[0] if pv else None
        ivc=round(calls["impliedVolatility"].mean()*100,1) if "impliedVolatility" in calls.columns else None
        ivp=round(puts["impliedVolatility"].mean()*100,1) if "impliedVolatility" in puts.columns else None
        return {"exp":exp,"coi":int(coi),"poi":int(poi),"cvol":int(cvol),"pvol":int(pvol),
                "pc_oi":round(poi/coi,2) if coi else None,"pc_vol":round(pvol/cvol,2) if cvol else None,
                "ivc":ivc,"ivp":ivp,"mp":mp,"calls":calls,"puts":puts,"exps":exps}
    except: return None

@st.cache_data(ttl=1800)
def fetch_macro():
    out={}
    for lbl,sym in {"VIX":"^VIX","SPY":"SPY","Dollar":"DX-Y.NYB","Gold":"GC=F","Oil":"CL=F"}.items():
        try:
            h=yf.Ticker(sym).history(period="5d")
            if not h.empty: out[lbl]=round(float(h["Close"].iloc[-1]),2)
        except: pass
    fred={"Fed Funds %":"FEDFUNDS","CPI YoY %":"CPIAUCSL","Core CPI %":"CPILFESL",
          "Unemployment %":"UNRATE","GDP Growth %":"A191RL1Q225SBEA",
          "10Y Treasury":"DGS10","2Y Treasury":"DGS2","HY Spread":"BAMLH0A0HYM2",
          "M2 Supply":"M2SL","PCE YoY %":"PCEPI"}
    for lbl,sid in fred.items():
        try:
            df=pd.read_csv(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}",parse_dates=["DATE"])
            df=df[df.iloc[:,1]!="."]
            df.iloc[:,1]=pd.to_numeric(df.iloc[:,1],errors="coerce")
            vals=df.iloc[:,1].dropna()
            if vals.empty: continue
            v=float(vals.iloc[-1])
            if ("CPI" in lbl or "PCE" in lbl) and len(vals)>=13:
                vp=float(vals.iloc[-13]); v=round((v-vp)/vp*100,2) if vp else round(v,2)
            else: v=round(v,2)
            out[lbl]=v
        except: pass
    if out.get("10Y Treasury") and out.get("2Y Treasury"):
        out["Yield Curve(10-2Y)"]=round(out["10Y Treasury"]-out["2Y Treasury"],2)
    if out.get("Fed Funds %") and out.get("CPI YoY %"):
        out["Real Rate"]=round(out["Fed Funds %"]-out["CPI YoY %"],2)
    return out

@st.cache_data(ttl=3600)
def fetch_sec_filings(ticker):
    hdrs={"User-Agent":"Bloomberg-Terminal contact@research.com"}
    try:
        r=requests.get("https://www.sec.gov/files/company_tickers.json",headers=hdrs,timeout=8)
        cik=None
        for _,row in r.json().items():
            if row.get("ticker","").upper()==ticker.upper():
                cik=str(row["cik_str"]).zfill(10); break
        if not cik: return [],None
        r2=requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",headers=hdrs,timeout=8)
        recent=r2.json().get("filings",{}).get("recent",{})
        forms=recent.get("form",[]); dates=recent.get("filingDate",[])
        accs=recent.get("accessionNumber",[]); docs=recent.get("primaryDocument",[])
        filings=[]
        for form,date,acc,doc in zip(forms,dates,accs,docs):
            if form in ("10-K","10-Q","8-K","4","DEF 14A"):
                acdn=acc.replace("-","")
                url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acdn}/{doc}"
                filings.append({"form":form,"date":date,"url":url})
            if len(filings)>=12: break
        return filings,cik
    except: return [],None

# ── SEC ADVANCED: 8-K TRANSCRIPT + SEGMENT REVENUE ──
@st.cache_data(ttl=3600)
def sec_8k_transcript(ticker,cik=None):
    if not cik: _,cik=fetch_sec_filings(ticker)
    if not cik: return None
    hdrs={"User-Agent":"Bloomberg-Terminal contact@research.com"}
    try:
        r=requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",headers=hdrs,timeout=8)
        recent=r.json().get("filings",{}).get("recent",{})
        forms=recent.get("form",[]); accs=recent.get("accessionNumber",[]); docs=recent.get("primaryDocument",[]); dates=recent.get("filingDate",[])
        for form,acc,doc,date in zip(forms,accs,docs,dates):
            if form=="8-K":
                acdn=acc.replace("-","")
                url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acdn}/{doc}"
                r2=requests.get(url,headers=hdrs,timeout=10)
                if r2.status_code==200:
                    text=r2.text; clean=re.sub(r"<[^>]+>"," ",text); clean=re.sub(r"\s+"," ",clean).strip()
                    lower=clean.lower(); kpos=[]
                    for kw in ["revenue","earnings","net income","eps","per share","guidance","outlook"]:
                        idx=lower.find(kw)
                        if idx>0: kpos.append(idx)
                    if kpos:
                        start=max(0,min(kpos)-200)
                        return {"date":date,"url":url,"text":clean[start:start+3000],"full_len":len(clean)}
        return None
    except: return None

@st.cache_data(ttl=3600)
def sec_segment_revenue(ticker,cik=None):
    if not cik: _,cik=fetch_sec_filings(ticker)
    if not cik: return None
    hdrs={"User-Agent":"Bloomberg-Terminal contact@research.com"}
    try:
        r=requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",headers=hdrs,timeout=12)
        if r.status_code!=200: return None
        us_gaap=r.json().get("facts",{}).get("us-gaap",{})
        rkeys=[k for k in us_gaap.keys() if any(x in k.lower() for x in ["revenue","sales","segment"])]
        rows=[]
        for key in rkeys[:20]:
            usd=us_gaap[key].get("units",{}).get("USD",[])
            recent=[v for v in usd if v.get("form") in ("10-K","10-Q") and v.get("val")]
            if recent:
                latest=sorted(recent,key=lambda x:x.get("end",""),reverse=True)[:1]
                if latest:
                    rows.append({"Concept":us_gaap[key].get("label",key),
                                 "Value($B)":round(latest[0].get("val")/1e9,2),
                                 "Period":latest[0].get("end")})
        if rows:
            df=pd.DataFrame(rows).sort_values("Value($B)",ascending=False)
            return df
        return None
    except: return None

# ── RATIO ENGINE ──
def _sg(df,row,idx=0):
    try: return df.loc[row].iloc[idx]
    except: return np.nan
def _pct(a,b):
    if pd.isna(a) or pd.isna(b) or b==0: return np.nan
    return round((a-b)/abs(b)*100,1)
def _rpct(n,d):
    if pd.isna(n) or pd.isna(d) or d==0: return np.nan
    return round(n/d*100,1)
def _sdiv(n,d):
    if pd.isna(n) or pd.isna(d) or d==0: return np.nan
    return round(n/d,2)
def ttm(ann,qtr,item):
    q=qtr.sort_index(axis=1,ascending=False)
    if item in q.index:
        v=q.loc[item].dropna()
        if len(v)>=4: return v.iloc[:4].sum()
    return _sg(ann.sort_index(axis=1,ascending=False),item,0)
def ttm_p(ann,qtr,item):
    q=qtr.sort_index(axis=1,ascending=False)
    if item in q.index:
        v=q.loc[item].dropna()
        if len(v)>=8: return v.iloc[4:8].sum()
    return _sg(ann.sort_index(axis=1,ascending=False),item,1)
def snap(ann,qtr,item):
    q=qtr.sort_index(axis=1,ascending=False); a=ann.sort_index(axis=1,ascending=False)
    cands=[]
    if item in q.index and len(q.columns)>0:
        v=q.loc[item].iloc[0]
        if not pd.isna(v): cands.append((q.columns[0],v))
    if item in a.index and len(a.columns)>0:
        v=a.loc[item].iloc[0]
        if not pd.isna(v): cands.append((a.columns[0],v))
    if not cands: return np.nan
    return sorted(cands,key=lambda x:x[0],reverse=True)[0][1]
def snap_p(ann,qtr,item):
    q=qtr.sort_index(axis=1,ascending=False)
    if item in q.index:
        v=q.loc[item].dropna()
        if len(v)>=5: return v.iloc[4]
    return _sg(ann.sort_index(axis=1,ascending=False),item,1)

def compute_ratios(ann,qtr):
    rev=ttm(ann,qtr,"Total Revenue"); rev_p=ttm_p(ann,qtr,"Total Revenue")
    gp=ttm(ann,qtr,"Gross Profit"); ni=ttm(ann,qtr,"Net Income")
    ebit=ttm(ann,qtr,"EBIT"); ebitda=ttm(ann,qtr,"EBITDA")
    eps=ttm(ann,qtr,"Diluted EPS"); eps_p=ttm_p(ann,qtr,"Diluted EPS")
    iexp=ttm(ann,qtr,"Interest Expense")
    debt=snap(ann,qtr,"Total Debt"); eq=snap(ann,qtr,"Stockholders Equity")
    ca=snap(ann,qtr,"Current Assets"); cl=snap(ann,qtr,"Current Liabilities")
    inv=snap(ann,qtr,"Inventory"); cash=snap(ann,qtr,"Cash And Cash Equivalents")
    ta=snap(ann,qtr,"Total Assets"); shn=snap(ann,qtr,"Ordinary Shares Number"); shp=snap_p(ann,qtr,"Ordinary Shares Number")
    ocf=ttm(ann,qtr,"Operating Cash Flow"); capex=ttm(ann,qtr,"Capital Expenditure")
    fcf=ttm(ann,qtr,"Free Cash Flow")
    if pd.isna(fcf) and not pd.isna(ocf) and not pd.isna(capex): fcf=ocf+capex
    ce=(ta-cl) if not any(pd.isna(x) for x in [ta,cl]) else np.nan
    roce=round(_sdiv(ebit,ce)*100,1) if not pd.isna(_sdiv(ebit,ce)) else np.nan
    ebitp=ttm_p(ann,qtr,"EBIT"); tap=snap_p(ann,qtr,"Total Assets"); clp=snap_p(ann,qtr,"Current Liabilities")
    cep=(tap-clp) if not any(pd.isna(x) for x in [tap,clp]) else np.nan
    rocep=round(_sdiv(ebitp,cep)*100,1) if not pd.isna(_sdiv(ebitp,cep)) else np.nan
    qa=(ca-inv) if not any(pd.isna(x) for x in [ca,inv]) else np.nan
    roe=_sdiv(ni,eq); roa=_sdiv(ni,ta)
    return {
        "Revenue($B)":round(rev/1e9,2) if not pd.isna(rev) else np.nan,
        "Revenue YoY %":_pct(rev,rev_p),"Gross Margin %":_rpct(gp,rev),
        "Net Margin %":_rpct(ni,rev),"EBITDA Margin %":_rpct(ebitda,rev),
        "EPS YoY %":_pct(eps,eps_p),"ROCE %":roce,
        "ROCE YoY Δ":round(roce-rocep,1) if not any(pd.isna(x) for x in [roce,rocep]) else np.nan,
        "Debt/Equity":_sdiv(debt,eq),"Interest Coverage":_sdiv(ebit,iexp),
        "Current Ratio":_sdiv(ca,cl),"Quick Ratio":_sdiv(qa,cl),
        "Cash/Debt":_sdiv(cash,debt),"Equity Ratio %":_rpct(eq,ta),
        "Share Count YoY %":_pct(shn,shp),
        "FCF($B)":round(fcf/1e9,2) if not pd.isna(fcf) else np.nan,
        "FCF Margin %":_rpct(fcf,rev),"FCF/Net Income":_sdiv(fcf,ni),
        "ROE %":round(roe*100,1) if not pd.isna(roe) else np.nan,
        "ROA %":round(roa*100,1) if not pd.isna(roa) else np.nan,
        "Asset Turnover":_sdiv(rev,ta),"Equity Multiplier":_sdiv(ta,eq),
        "_ni":ni,"_ocf":ocf,"_ta":ta,"_gw":snap(ann,qtr,"Goodwill"),
        "_ar":snap(ann,qtr,"Accounts Receivable"),"_ar_p":snap_p(ann,qtr,"Accounts Receivable"),
        "_rev_p":rev_p,"_fcf":fcf,
    }

PILLARS={
    "Quality":[("Revenue YoY %",(10,0),True),("EPS YoY %",(10,0),True),
               ("Net Margin %",(15,5),True),("EBITDA Margin %",(20,10),True),("ROCE %",(20,10),True)],
    "Safety":[("Debt/Equity",(0.5,1.5),False),("Interest Coverage",(8,3),True),("Current Ratio",(1.5,1.0),True)],
    "Liquidity":[("Quick Ratio",(1.0,0.5),True),("Cash/Debt",(0.5,0.2),True)],
    "Capital":[("Equity Ratio %",(50,30),True),("Share Count YoY %",(-1,1),False)],
}
def sm(val,thr,h):
    if pd.isna(val): return None
    s,m=thr
    if h: return 2 if val>=s else 1 if val>=m else 0
    else: return 2 if val<=s else 1 if val<=m else 0
def score_pillars(ratios):
    out={}
    for pillar,metrics in PILLARS.items():
        scores,detail=[],[]
        for name,thr,h in metrics:
            v=ratios.get(name,np.nan); s=sm(v,thr,h); detail.append((name,v,s))
            if s is not None: scores.append(s)
        if scores:
            avg=sum(scores)/len(scores); psc=round(avg/2*100)
            verd="Strong" if avg>=1.5 else "Moderate" if avg>=0.75 else "Weak"
        else: psc,verd=None,"No Data"
        out[pillar]={"score":psc,"verdict":verd,"detail":detail}
    return out

def roce_flag(qtr,lb=3):
    q=qtr.sort_index(axis=1,ascending=False)
    if "ROCE %" not in q.index: return False,[]
    s=q.loc["ROCE %"].dropna()
    if len(s)<lb+1: return False,list(s.items())[:lb]
    recent=s.iloc[:lb+1].iloc[::-1]; vals=recent.tolist()
    dec=all(vals[i]>vals[i+1] for i in range(len(vals)-1))
    return dec,[(c.strftime("%Y-%m-%d"),round(v,1)) for c,v in recent.items()]

# ── TECHNICALS ──
def compute_tech(hist):
    if hist is None or hist.empty or len(hist)<50: return None
    close=hist["Close"]
    if isinstance(close,pd.DataFrame): close=close.iloc[:,0]
    price=float(close.iloc[-1])
    sma20=close.rolling(20).mean(); sma50=close.rolling(50).mean()
    sma200=close.rolling(200).mean() if len(close)>=200 else pd.Series([np.nan]*len(close),index=close.index)
    delta=close.diff(); gain=delta.clip(lower=0).rolling(14).mean()
    loss=(-delta.clip(upper=0)).rolling(14).mean()
    rsi=float((100-100/(1+gain/loss.replace(0,np.nan))).iloc[-1])
    ema12=close.ewm(span=12).mean(); ema26=close.ewm(span=26).mean()
    ml=ema12-ema26; ms=ml.ewm(span=9).mean()
    mv=float(ml.iloc[-1]); msv=float(ms.iloc[-1]); macd_t="Bullish" if mv>msv else "Bearish"
    if "High" in hist.columns and "Low" in hist.columns:
        tr=pd.concat([hist["High"]-hist["Low"],(hist["High"]-close.shift()).abs(),(hist["Low"]-close.shift()).abs()],axis=1).max(axis=1)
        atr=float(tr.rolling(14).mean().iloc[-1])
    else: atr=np.nan
    bm=float(sma20.iloc[-1]); bstd=float(close.rolling(20).std().iloc[-1])
    bu=bm+2*bstd; bl=bm-2*bstd; bbp=round((price-bl)/(bu-bl)*100,1) if bu!=bl else 50
    obv=pd.Series(0.0,index=close.index)
    if "Volume" in hist.columns:
        vol=hist["Volume"]
        for i in range(1,len(close)):
            if close.iloc[i]>close.iloc[i-1]: obv.iloc[i]=obv.iloc[i-1]+vol.iloc[i]
            elif close.iloc[i]<close.iloc[i-1]: obv.iloc[i]=obv.iloc[i-1]-vol.iloc[i]
            else: obv.iloc[i]=obv.iloc[i-1]
    obv_t="Rising" if float(obv.iloc[-1])>float(obv.rolling(20).mean().iloc[-1]) else "Falling"
    h52=float(close.rolling(252).max().iloc[-1]) if len(close)>=252 else float(close.max())
    l52=float(close.rolling(252).min().iloc[-1]) if len(close)>=252 else float(close.min())
    s50=float(sma50.iloc[-1]) if not pd.isna(sma50.iloc[-1]) else price
    s200=float(sma200.iloc[-1]) if not pd.isna(sma200.iloc[-1]) else price
    if price>s50>s200: trend="Strong Uptrend"
    elif price>s50: trend="Uptrend"
    elif price<s50<s200: trend="Strong Downtrend"
    elif price<s50: trend="Downtrend"
    else: trend="Sideways"
    rn="Overbought" if rsi>=70 else "Oversold" if rsi<=30 else "Neutral"
    ts=50
    if "Strong Uptrend" in trend: ts+=25
    elif "Uptrend" in trend: ts+=15
    elif "Strong Downtrend" in trend: ts-=25
    elif "Downtrend" in trend: ts-=15
    if macd_t=="Bullish": ts+=10
    else: ts-=10
    if 40<=rsi<=65: ts+=10
    elif rsi>75 or rsi<25: ts-=15
    if obv_t=="Rising": ts+=5
    ts=max(0,min(100,ts))
    return {"price":price,"sma20":round(bm,2),"sma50":round(s50,2),"sma200":round(s200,2),
            "rsi":round(rsi,1),"rsi_n":rn,"macd":round(mv,3),"macd_sig":round(msv,3),"macd_t":macd_t,
            "atr":round(atr,2) if not pd.isna(atr) else None,"bb_u":round(bu,2),"bb_l":round(bl,2),"bbp":bbp,
            "obv":obv,"obv_t":obv_t,"trend":trend,"ts":ts,
            "h52":round(h52,2),"l52":round(l52,2),"dh":round((price-h52)/h52*100,1),"dl":round((price-l52)/l52*100,1),
            "close":close,"sma50s":sma50,"sma200s":sma200}

@st.cache_data(ttl=3600)
def fetch_rs(ticker):
    try:
        data=yf.download([ticker,"SPY"],period="1y",progress=False,auto_adjust=True)["Close"]
        if ticker not in data.columns or "SPY" not in data.columns: return None
        sr=data[ticker].pct_change().dropna(); sp=data["SPY"].pct_change().dropna()
        rs=(1+sr).cumprod()/(1+sp).cumprod()
        return {"ratio":round(float(rs.iloc[-1]),3),
                "trend":"Outperforming" if rs.iloc[-1]>rs.iloc[-20] else "Underperforming","series":rs}
    except: return None

# ── GREEKS ──
def _bs(S,K,T,r,sigma,typ="call"):
    if T<=0 or sigma<=0 or S<=0 or K<=0: return {}
    try:
        from scipy.stats import norm
        d1=(math.log(S/K)+(r+0.5*sigma**2)*T)/(sigma*math.sqrt(T)); d2=d1-sigma*math.sqrt(T)
        if typ=="call": delta=norm.cdf(d1)
        else: delta=-norm.cdf(-d1)
        gamma=norm.pdf(d1)/(S*sigma*math.sqrt(T))
        theta=(-(S*norm.pdf(d1)*sigma)/(2*math.sqrt(T))-r*K*math.exp(-r*T)*(norm.cdf(d2) if typ=="call" else norm.cdf(-d2)))/365
        vega=S*norm.pdf(d1)*math.sqrt(T)/100
        return {"delta":round(delta,3),"gamma":round(gamma,4),"theta":round(theta,4),"vega":round(vega,4)}
    except: return {}

def compute_greeks(opts,price,r=0.05):
    if not opts or not price: return None
    try:
        calls=opts["calls"]; puts=opts["puts"]; exp_date=pd.to_datetime(opts["exp"])
        T=max((exp_date-pd.Timestamp.now()).days/365,0.001)
        ca=calls.iloc[(calls["strike"]-price).abs().argsort()[:1]]
        pa=puts.iloc[(puts["strike"]-price).abs().argsort()[:1]]
        civ=float(ca["impliedVolatility"].values[0]) if not ca.empty else 0.3
        piv=float(pa["impliedVolatility"].values[0]) if not pa.empty else 0.3
        straddle=float(ca["lastPrice"].values[0])+float(pa["lastPrice"].values[0])
        return {"call":_bs(price,float(ca["strike"].values[0]),T,r,civ,"call"),
                "put":_bs(price,float(pa["strike"].values[0]),T,r,piv,"put"),
                "impl_move":round(straddle/price*100,2),"civ":round(civ*100,1),"piv":round(piv*100,1),"T":round(T,3)}
    except: return None

# ── NEWS SENTIMENT ──
POS_W={"beat","beats","surge","soar","rally","growth","record","strong","upgrade","outperform",
       "bullish","gain","profit","expand","win","boost","positive","raises","exceed","innovation",
       "breakthrough","partnership","deal","acquire","momentum","optimistic","success","higher","raised"}
NEG_W={"miss","misses","plunge","slump","crash","decline","downgrade","underperform","bearish",
       "loss","cut","layoff","lawsuit","investigation","fraud","recall","weak","warning","concern",
       "fall","drop","lower","negative","sued","fine","delay","shortfall","trouble","risk","fired"}
def sent(text):
    w=set(x.strip(".,!?:;()'\"").lower() for x in str(text).split())
    p=len(w&POS_W); n=len(w&NEG_W)
    return (p-n)/(p+n) if p+n>0 else 0.0
def analyze_news_yf(raw):
    arts=[]; tot=0.0
    for item in raw[:15]:
        try:
            c=item.get("content",item)
            t=c.get("title") or item.get("title","")
            if not t: continue
            pub=(c.get("provider",{}).get("displayName") if isinstance(c.get("provider"),dict) else item.get("publisher",""))
            lnk=(c.get("canonicalUrl",{}).get("url") if isinstance(c.get("canonicalUrl"),dict) else item.get("link","")) or ""
            sc=sent(t); arts.append({"title":t,"pub":pub,"link":lnk,"score":round(sc,2)}); tot+=sc
        except: pass
    avg=tot/len(arts) if arts else 0.0
    return {"arts":arts,"avg":round(avg,2),"label":"Positive 🟢" if avg>0.15 else "Negative 🔴" if avg<-0.15 else "Neutral 🟡"}

# ── EARNINGS INTELLIGENCE ──
def earnings_intel(ticker,ts=50,fs=50):
    s=yf.Ticker(ticker)
    r={"next_date":"Unknown","consensus_eps":None,"revision":"Unknown",
       "beat_rate":None,"avg_surp":None,"history":[],"EPS_Beat":50.0,"notes":[]}
    try:
        cal=s.calendar
        if isinstance(cal,dict):
            ed=cal.get("Earnings Date")
            if isinstance(ed,list) and ed: r["next_date"]=str(ed[0])[:10]
            elif ed: r["next_date"]=str(ed)[:10]
            if cal.get("Earnings Average"): r["consensus_eps"]=cal["Earnings Average"]
    except: pass
    try:
        rev=s.eps_revisions
        if rev is not None and not rev.empty:
            col=next((c for c in rev.columns if "current" in str(c).lower() or str(c)=="0q"),rev.columns[0])
            idxl=[str(i).lower() for i in rev.index]
            up7=next((rev.iloc[i][col] for i,l in enumerate(idxl) if "up" in l and "7" in l),None)
            dn7=next((rev.iloc[i][col] for i,l in enumerate(idxl) if "down" in l and "7" in l),None)
            if up7 is not None and dn7 is not None:
                r["revision"]="Bullish ↑" if up7>dn7 else "Bearish ↓" if dn7>up7 else "Neutral"
    except: pass
    try:
        ed_df=s.earnings_dates
        if ed_df is not None and not ed_df.empty and "Reported EPS" in ed_df.columns:
            past=ed_df.dropna(subset=["Reported EPS"]).head(8)
            beats,tot,surps=0,0,[]
            for idx,row in past.iterrows():
                rep=row.get("Reported EPS"); est=row.get("EPS Estimate")
                if rep is not None and est is not None and not pd.isna(rep) and not pd.isna(est):
                    tot+=1
                    if rep>est: beats+=1
                    if est!=0: surps.append((rep-est)/abs(est)*100)
                    dstr=str(idx.date())[:10] if hasattr(idx,"date") else str(idx)[:10]
                    r["history"].append({"Q":dstr,"Est":round(float(est),2),"Rep":round(float(rep),2),
                                          "Beat":"yes" if rep>est else "no",
                                          "Surp%":round((rep-est)/abs(est)*100,1) if est!=0 else 0})
            if tot>0: r["beat_rate"]=round(beats/tot*100,1)
            if surps: r["avg_surp"]=round(sum(surps)/len(surps),2)
    except: pass
    try:
        fdf=fmp_surprises(ticker)
        if fdf is not None and not fdf.empty and not r["history"]:
            for _,row in fdf.head(8).iterrows():
                est=row.get("estimatedEps") or row.get("epsEstimated")
                act=row.get("actualEarningResult") or row.get("actualEarnings") or row.get("eps")
                if est and act:
                    try:
                        r["history"].append({"Q":str(row.get("date",""))[:10],
                            "Est":round(float(est),2),"Rep":round(float(act),2),
                            "Beat":"yes" if float(act)>float(est) else "no",
                            "Surp%":round((float(act)-float(est))/abs(float(est))*100,1) if float(est)!=0 else 0})
                    except: pass
    except: pass
    prob=50.0
    if r["beat_rate"] is not None: prob+=(r["beat_rate"]-50)*0.4; r["notes"].append(f"beat rate {r['beat_rate']}%")
    if "Bullish" in r["revision"]: prob+=8; r["notes"].append("estimates rising")
    elif "Bearish" in r["revision"]: prob-=8; r["notes"].append("estimates falling")
    prob+=(ts-50)*0.12+(fs-50)*0.12
    r["EPS_Beat"]=round(max(5,min(95,prob)),1)
    return r

# ── FORENSIC ──
def forensic(ratios):
    ni=ratios.get("_ni",np.nan); ocf=ratios.get("_ocf",np.nan)
    ta=ratios.get("_ta",np.nan); gw=ratios.get("_gw",np.nan)
    ar=ratios.get("_ar",np.nan); ar_p=ratios.get("_ar_p",np.nan)
    rev_gr=ratios.get("Revenue YoY %",np.nan); flags=[]
    accrual=(ni-ocf)/ta*100 if not any(pd.isna(x) for x in [ni,ocf,ta]) and ta!=0 else np.nan
    gw_pct=gw/ta*100 if not any(pd.isna(x) for x in [gw,ta]) and ta!=0 else np.nan
    ar_gr=_pct(ar,ar_p)
    if not pd.isna(accrual) and accrual>5: flags.append(f"High accruals {accrual:.1f}% — earnings quality concern")
    if not pd.isna(gw_pct) and gw_pct>30: flags.append(f"Goodwill {gw_pct:.0f}% of assets — impairment risk")
    if not pd.isna(ar_gr) and not pd.isna(rev_gr) and ar_gr>rev_gr+15:
        flags.append(f"Receivables ({ar_gr}%) >> revenue ({rev_gr}%) — channel stuffing risk")
    fcf_conv=ratios.get("FCF/Net Income",np.nan)
    if not pd.isna(fcf_conv) and fcf_conv<0.5: flags.append(f"FCF/NI only {fcf_conv}x — earnings not converting to cash")
    return {"accrual":round(accrual,1) if not pd.isna(accrual) else None,
            "gw_pct":round(gw_pct,1) if not pd.isna(gw_pct) else None,
            "ar_gr":ar_gr,"rev_gr":rev_gr,"flags":flags}

# ── VALUATION + DCF ──
def val_timing(hist,info,verdict):
    if hist is None or hist.empty: return None
    price=float(hist["Close"].iloc[-1])
    hi=float(hist["Close"].max()); lo=float(hist["Close"].min())
    pos=(price-lo)/(hi-lo)*100 if hi!=lo else 50
    zone="Value Zone" if pos<=33 else "Fair Zone" if pos<=66 else "Extended Zone"
    if verdict=="BUY" and pos<=40: action="ENTRY ✅"
    elif verdict=="BUY" and pos>75: action="WAIT — extended"
    elif "AVOID" in verdict and pos>60: action="EXIT / TRIM ⚠️"
    else: action="HOLD — monitor"
    return {"price":price,"hi":hi,"lo":lo,"pos":round(pos,1),"zone":zone,"action":action,
            "pe":info.get("trailingPE"),"fpe":info.get("forwardPE")}

def val_mults(info):
    return {k:info.get(v) for k,v in {"P/E(TTM)":"trailingPE","P/E(Fwd)":"forwardPE",
        "P/S":"priceToSalesTrailing12Months","P/B":"priceToBook",
        "EV/EBITDA":"enterpriseToEbitda","PEG":"pegRatio","EV/Rev":"enterpriseToRevenue"}.items()}

def dcf(ann,qtr,info,g,d,tg,yrs=5):
    fcf=ratios.get("_fcf",np.nan) if "ratios" in dir() else np.nan
    fcf2=ttm(ann,qtr,"Free Cash Flow")
    if pd.isna(fcf2):
        ocf=ttm(ann,qtr,"Operating Cash Flow"); capex=ttm(ann,qtr,"Capital Expenditure")
        if not pd.isna(ocf) and not pd.isna(capex): fcf2=ocf+capex
    if pd.isna(fcf2) or fcf2<=0 or d<=tg: return None
    debt=snap(ann,qtr,"Total Debt"); cash_=snap(ann,qtr,"Cash And Cash Equivalents")
    shares=info.get("sharesOutstanding") or snap(ann,qtr,"Ordinary Shares Number")
    if not shares or pd.isna(shares): return None
    pv_sum=0; proj=[]
    for t in range(1,yrs+1):
        ft=fcf2*(1+g)**t; pv=ft/(1+d)**t
        pv_sum+=pv; proj.append({"Year":t,"FCF($B)":round(ft/1e9,3),"PV($B)":round(pv/1e9,3)})
    tv=fcf2*(1+g)**yrs*(1+tg)/(d-tg); pvtv=tv/(1+d)**yrs; ev=pv_sum+pvtv
    nd=(debt if not pd.isna(debt) else 0)-(cash_ if not pd.isna(cash_) else 0)
    fair=(ev-nd)/shares
    return {"fair":round(fair,2),"ev_b":round(ev/1e9,2),"tv_pct":round(pvtv/ev*100,1) if ev else None,"proj":proj}

# ── ANALYST / OWNERSHIP / SHORT ──
def analyst_d(info):
    tgt=info.get("targetMeanPrice"); cur=info.get("currentPrice") or info.get("regularMarketPrice")
    up=round((tgt-cur)/cur*100,1) if tgt and cur and cur!=0 else None
    return {"Recommendation":info.get("recommendationKey","n/a"),"Mean Rating":info.get("recommendationMean"),
            "# Analysts":info.get("numberOfAnalystOpinions"),"Target Mean":tgt,
            "Target High":info.get("targetHighPrice"),"Target Low":info.get("targetLowPrice"),"Upside %":up}

def ownership_d(info,itx):
    ins=info.get("heldPercentInsiders"); inst=info.get("heldPercentInstitutions")
    r={"Institutional %":round(inst*100,1) if inst and not pd.isna(inst) else None,
       "Insider %":round(ins*100,1) if ins and not pd.isna(ins) else None}
    try:
        if itx is not None and not itx.empty:
            recent=itx.head(12)
            for col in ["Transaction","Text","transactionText"]:
                if col in recent.columns:
                    b=recent[col].astype(str).str.contains("Buy",case=False,na=False).sum()
                    s=recent[col].astype(str).str.contains("Sale|Sell",case=False,na=False).sum()
                    r["Recent Activity"]=f"{b} buys / {s} sells"; break
    except: pass
    return r

def short_d(info):
    spf=info.get("shortPercentOfFloat"); spo=info.get("sharesPercentSharesOut"); si=info.get("shortRatio")
    sq=min(100,round(spf*100*4+(1/si*20 if si and si>0 else 0))) if spf and not pd.isna(spf) else None
    return {"Short % Float":round(spf*100,2) if spf and not pd.isna(spf) else None,
            "Days to Cover":si,"Short % Shares Out":round(spo*100,2) if spo and not pd.isna(spo) else None,
            "Squeeze Score":sq}

# ── 100-POINT INSTITUTIONAL DECISION SCORE ──
def inst_score(ratios,pillars,val,analyst,own,short,tech,ei,forensic_flags,macro):
    score=0; bd={}
    q=(pillars.get("Quality",{}).get("score") or 0); bq=round(q*0.28); bd["Business Quality"]=bq; score+=bq
    s=(pillars.get("Safety",{}).get("score") or 0); fs=round(s*0.14); bd["Financial Safety"]=fs; score+=fs
    gr=0; rg=ratios.get("Revenue YoY %",np.nan); eg=ratios.get("EPS YoY %",np.nan)
    if not pd.isna(rg): gr+=(8 if rg>20 else 6 if rg>10 else 4 if rg>5 else 2 if rg>0 else 0)
    if not pd.isna(eg): gr+=(6 if eg>20 else 4 if eg>10 else 2 if eg>0 else 0)
    bd["Growth"]=min(gr,14); score+=min(gr,14)
    vl=0
    if val:
        pos=val.get("pos",100); vl+=(6 if pos<25 else 4 if pos<40 else 2 if pos<60 else 0)
        pe=val.get("pe")
        if pe and not pd.isna(pe): vl+=(4 if pe<15 else 3 if pe<22 else 2 if pe<35 else 0)
    bd["Valuation"]=min(vl,10); score+=min(vl,10)
    al=0; up=analyst.get("Upside %"); rec=str(analyst.get("Recommendation","")).lower()
    if up and not pd.isna(up): al+=(6 if up>30 else 4 if up>15 else 2 if up>5 else 0)
    if "strong_buy" in rec or "strong buy" in rec: al+=4
    elif "buy" in rec: al+=3
    elif "hold" in rec: al+=1
    bd["Analyst Consensus"]=min(al,10); score+=min(al,10)
    ei_sc=0; br=ei.get("beat_rate"); rs=ei.get("revision","")
    if br is not None: ei_sc+=(6 if br>=80 else 4 if br>=65 else 2 if br>=50 else 0)
    if "Bullish" in rs: ei_sc+=4
    elif "Bearish" in rs: ei_sc-=2
    bd["Earnings Intel"]=max(0,min(ei_sc,10)); score+=max(0,min(ei_sc,10))
    ow=0; ip=own.get("Institutional %")
    if ip and not pd.isna(ip): ow=(5 if ip>75 else 3 if ip>50 else 1)
    bd["Inst. Ownership"]=ow; score+=ow
    sh_sc=0; sf=short.get("Short % Float")
    if sf and not pd.isna(sf): sh_sc=(5 if sf<2 else 4 if sf<5 else 2 if sf<10 else 0)
    bd["Short Interest"]=sh_sc; score+=sh_sc
    tc=0
    if tech:
        trend=tech.get("trend",""); rsi=tech.get("rsi",50); macd=tech.get("macd_t",""); obv=tech.get("obv_t","")
        if "Strong Uptrend" in trend: tc+=3
        elif "Uptrend" in trend: tc+=2
        if macd=="Bullish": tc+=1
        if 40<=rsi<=65: tc+=1
        if obv=="Rising": tc+=1
    bd["Technical"]=min(tc,5); score+=min(tc,5)
    mc=0; curve=macro.get("Yield Curve(10-2Y)")
    if curve and curve>0: mc+=1
    vix=macro.get("VIX")
    if vix and vix<20: mc+=2
    bd["Macro"]=min(mc,3); score+=min(mc,3)
    ff=0 if forensic_flags else 3; bd["Forensic Clean"]=ff; score+=ff
    fcfm=ratios.get("FCF Margin %",np.nan)
    fq=0 if pd.isna(fcfm) else (3 if fcfm>15 else 2 if fcfm>8 else 1 if fcfm>0 else 0)
    bd["FCF Quality"]=fq; score+=fq
    score=max(0,min(100,round(score)))
    if score>=88: verdict="STRONG BUY"
    elif score>=74: verdict="BUY"
    elif score>=58: verdict="HOLD"
    elif pillars.get("Safety",{}).get("verdict")=="Weak": verdict="AVOID / HIGH RISK"
    else: verdict="AVOID"
    grade="A+" if score>=92 else "A" if score>=85 else "B+" if score>=78 else "B" if score>=70 else "C" if score>=55 else "D" if score>=40 else "F"
    return score,verdict,grade,bd

# ── AI THESIS ──
def generate_thesis(ticker,verdict,ratios,pillars,val,analyst,tech,for_r,ei,macro,score):
    q=pillars.get("Quality",{}); s=pillars.get("Safety",{})
    lines=[f"**{ticker} — {verdict} · Score {score}/100**"]
    lines.append(f"Business quality is **{q.get('verdict','N/A')}** (ROCE {ratios.get('ROCE %','N/A')}%, "
                 f"net margin {ratios.get('Net Margin %','N/A')}%, revenue YoY {ratios.get('Revenue YoY %','N/A')}%, "
                 f"FCF margin {ratios.get('FCF Margin %','N/A')}%). "
                 f"Safety **{s.get('verdict','N/A')}** (D/E {ratios.get('Debt/Equity','N/A')}, coverage {ratios.get('Interest Coverage','N/A')}x).")
    br=ei.get("beat_rate"); rs=ei.get("revision","Unknown")
    if br: lines.append(f"Earnings: **{br}% beat rate**, next report {ei.get('next_date','Unknown')}. Revisions: **{rs}**. Beat prob: **{ei.get('EPS_Beat',50)}%**.")
    if val: lines.append(f"Price ${val['price']:.2f} in **{val['zone']}** ({val['pos']}% of 2Y range). Action: **{val['action']}**.")
    up=analyst.get("Upside %")
    if up: lines.append(f"Street: **{analyst.get('Recommendation','n/a')}** from {analyst.get('# Analysts','?')} analysts. Target ${analyst.get('Target Mean','N/A')}, upside **{up}%**.")
    if tech: lines.append(f"Technical: **{tech.get('trend','N/A')}**, RSI {tech.get('rsi','N/A')} ({tech.get('rsi_n','N/A')}), MACD **{tech.get('macd_t','N/A')}**, OBV **{tech.get('obv_t','N/A')}**.")
    curve=macro.get("Yield Curve(10-2Y)")
    if curve is not None:
        env="inverted ⚠️" if curve<0 else "normal ✅"
        lines.append(f"Macro: VIX {macro.get('VIX','N/A')}, curve {curve:.2f}% ({env}), Fed Funds {macro.get('Fed Funds %','N/A')}%, real rate {macro.get('Real Rate','N/A')}%.")
    if for_r["flags"]: lines.append("⚠️ Forensic: "+" | ".join(for_r["flags"]))
    else: lines.append("✅ No forensic red flags.")
    return "\n\n".join(lines)

# ── CALIBRATION ──
def calibrate(ticker):
    rows=get_preds(ticker,30)
    if len(rows)<2: return None
    try:
        hist=yf.download(ticker,period="1y",progress=False,auto_adjust=True)["Close"]
        if isinstance(hist,pd.DataFrame): hist=hist.iloc[:,0]
    except: return None
    hits=0; ev=0
    for ds,verdict,score,price_at in rows:
        try:
            pd_=pd.to_datetime(ds); fwd=hist.index[hist.index>=pd_]
            if len(fwd)<10: continue
            up=float(hist.loc[fwd[10]])>float(hist.loc[fwd[0]])
            pu=verdict in ("STRONG BUY","BUY")
            if up==pu: hits+=1
            ev+=1
        except: continue
    return {"acc":round(hits/ev*100,1),"n":ev} if ev>0 else None

# ── VaR ──
def compute_var(price_df,holdings):
    if price_df is None or price_df.empty: return None
    try:
        rets=price_df.pct_change().dropna(how="all")
        total_vals=pd.Series(0.0,index=rets.index)
        for tk,shares,cost in holdings:
            if tk in price_df.columns:
                pos_vals=price_df[tk]*shares
                total_vals=total_vals.add(pos_vals.reindex(total_vals.index,fill_value=0))
        port_rets=total_vals.pct_change().dropna()
        if len(port_rets)<20: return None
        cv=total_vals.iloc[-1]; result={"current_value":cv}
        for cl in [0.95,0.99]:
            vp=float(np.percentile(port_rets,(1-cl)*100))
            result[f"VaR_{int(cl*100)}pct"]=round(vp*100,2)
            result[f"VaR_{int(cl*100)}dollar"]=round(abs(vp*cv),0)
        v95=np.percentile(port_rets,5); cvar=float(port_rets[port_rets<=v95].mean())
        result["CVaR_95pct"]=round(cvar*100,2); result["CVaR_95dollar"]=round(abs(cvar*cv),0)
        cumulative=(1+port_rets).cumprod(); rolling_max=cumulative.expanding().max()
        result["max_drawdown_pct"]=round(float(((cumulative-rolling_max)/rolling_max).min())*100,2)
        result["port_rets"]=port_rets
        return result
    except: return None

# ── PORTFOLIO ──
@st.cache_data(ttl=3600)
def port_prices(tickers,period="1y"):
    tks=list(dict.fromkeys(list(tickers)+["SPY"])); data={}
    for t in tks:
        try:
            h=yf.Ticker(t).history(period=period)
            if not h.empty: data[t]=h["Close"]
        except: pass
    return pd.DataFrame(data).dropna(how="all") if data else None

def port_analytics(price_df,holdings):
    if price_df is None or price_df.empty: return None
    rets=price_df.pct_change().dropna(how="all"); results=[]; tv=0
    for tk,sh_,cost in holdings:
        if tk not in price_df.columns: continue
        price=float(price_df[tk].dropna().iloc[-1])
        val_=sh_*price; pl=(price-cost)*sh_; plp=(price-cost)/cost*100 if cost else 0
        beta=np.nan
        if "SPY" in rets.columns and tk in rets.columns:
            al=rets[[tk,"SPY"]].dropna()
            if len(al)>=20: beta=round(al[tk].cov(al["SPY"])/al["SPY"].var(),2)
        results.append({"Ticker":tk,"Shares":sh_,"Price":round(price,2),"Value":round(val_,2),
                        "Cost":cost,"P/L":round(pl,2),"P/L %":round(plp,1),"Beta":beta}); tv+=val_
    if not results: return None
    df=pd.DataFrame(results); sectors={}
    for tk in df["Ticker"]:
        try:
            sec=yf.Ticker(tk).info.get("sector","Unknown")
            w=float(df.loc[df["Ticker"]==tk,"Value"].values[0]); sectors[sec]=sectors.get(sec,0)+w
        except: pass
    valid=[t for t in df["Ticker"] if t in rets.columns]
    corr=rets[valid].corr() if len(valid)>=2 else None
    var=compute_var(price_df,holdings)
    return {"df":df,"tv":tv,"sectors":sectors,"corr":corr,"var":var}

@st.cache_data(ttl=3600)
def peer_snap(pt):
    try:
        info=yf.Ticker(pt).info
        return {"Ticker":pt,"Price":info.get("currentPrice") or info.get("regularMarketPrice"),
                "Mkt Cap($B)":round((info.get("marketCap") or 0)/1e9,1),
                "P/E(TTM)":info.get("trailingPE"),"P/E(Fwd)":info.get("forwardPE"),
                "EV/EBITDA":info.get("enterpriseToEbitda"),
                "Rev Gr%":round((info.get("revenueGrowth") or 0)*100,1),
                "Net Mar%":round((info.get("profitMargins") or 0)*100,1),
                "ROE%":round((info.get("returnOnEquity") or 0)*100,1)}
    except: return None

# ── CHARTS ──
def price_chart(hist,tech,ticker):
    close=tech["close"]; s50=tech["sma50s"]; s200=tech["sma200s"]
    bb_u=tech["sma20"]+2*close.rolling(20).std()
    bb_l=tech["sma20"]-2*close.rolling(20).std()
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=close.index,y=bb_u,mode="lines",name="BB Upper",line=dict(color="rgba(100,116,139,0.4)",width=1)))
    fig.add_trace(go.Scatter(x=close.index,y=bb_l,mode="lines",name="BB Lower",line=dict(color="rgba(100,116,139,0.4)",width=1),fill="tonexty",fillcolor="rgba(100,116,139,0.04)"))
    fig.add_trace(go.Scatter(x=close.index,y=close,mode="lines",name=ticker,line=dict(color="#38bdf8",width=2),fill="tozeroy",fillcolor="rgba(56,189,248,0.05)"))
    fig.add_trace(go.Scatter(x=s50.index,y=s50,mode="lines",name="SMA50",line=dict(color="#facc15",width=1.2,dash="dot")))
    fig.add_trace(go.Scatter(x=s200.index,y=s200,mode="lines",name="SMA200",line=dict(color="#a78bfa",width=1.2,dash="dot")))
    fig.update_layout(height=340,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#94a3b8"),margin=dict(l=10,r=10,t=10,b=10),
                      legend=dict(bgcolor="rgba(0,0,0,0)",font=dict(size=11),orientation="h"),
                      xaxis=dict(gridcolor="rgba(148,163,184,0.06)"),yaxis=dict(gridcolor="rgba(148,163,184,0.06)"))
    return fig

def gauge(v,title,color):
    fig=go.Figure(go.Indicator(mode="gauge+number",value=v,
        number=dict(font=dict(color="#f1f5f9",family="JetBrains Mono",size=28)),
        title=dict(text=title,font=dict(color="#64748b",size=10)),
        gauge=dict(axis=dict(range=[0,100],tickcolor="#334155",tickfont=dict(color="#475569",size=8)),
                   bar=dict(color=color,thickness=0.24),bgcolor="rgba(0,0,0,0)",
                   borderwidth=1,bordercolor="rgba(148,163,184,0.15)",
                   steps=[dict(range=[0,40],color="rgba(248,113,113,0.07)"),
                          dict(range=[40,70],color="rgba(250,204,21,0.07)"),
                          dict(range=[70,100],color="rgba(52,211,153,0.07)")])))
    fig.update_layout(height=200,margin=dict(l=12,r=12,t=30,b=5),paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)")
    return fig

def score_bar(bd):
    items=sorted(bd.items(),key=lambda x:x[1])
    labels=[k for k,v in items]; vals=[v for k,v in items]
    colors=["#34d399" if v>=7 else "#facc15" if v>=4 else "#f87171" for v in vals]
    fig=go.Figure(go.Bar(x=vals,y=labels,orientation="h",marker=dict(color=colors,line=dict(width=0)),
                          text=[f"{v}" for v in vals],textposition="outside",textfont=dict(color="#e2e8f0",size=11)))
    fig.update_layout(height=max(260,len(bd)*22),paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#94a3b8"),margin=dict(l=10,r=40,t=10,b=10),
                      xaxis=dict(range=[0,max(vals)+4] if vals else [0,10],gridcolor="rgba(148,163,184,0.06)"),
                      yaxis=dict(gridcolor="rgba(0,0,0,0)"))
    return fig


# ============================================================================
# ADDITION 1 — HISTORICAL P/E BAND (real point-in-time, proven correct math)
# ============================================================================

@st.cache_data(ttl=3600)
def pe_band(hist, qtr):
    """Real trailing P/E at each quarter-end = actual price / trailing 4Q EPS."""
    if hist is None or hist.empty: return None
    q = qtr.sort_index(axis=1, ascending=True)
    if "Diluted EPS" not in q.index: return None
    eps_row = q.loc["Diluted EPS"].dropna()
    if len(eps_row) < 4: return None
    ttm_eps = eps_row.rolling(4).sum().dropna()
    if ttm_eps.empty: return None
    points = []
    hist_tz = hist.index.tz
    for dt, eps_val in ttm_eps.items():
        if pd.isna(eps_val) or eps_val == 0: continue
        dt_c = dt.tz_localize(hist_tz) if hist_tz and dt.tzinfo is None else dt
        fp = hist.loc[hist.index >= dt_c]
        if fp.empty: continue
        price_at = float(fp["Close"].iloc[0])
        pe_val = round(price_at / eps_val, 1)
        if 0 < pe_val < 500:
            points.append({"date": dt.strftime("%Y-%m-%d"), "pe": pe_val, "price": round(price_at, 2), "eps": round(float(eps_val), 2)})
    if not points: return None
    values = [p["pe"] for p in points]
    current_eps = float(ttm_eps.iloc[-1])
    current_price = float(hist["Close"].iloc[-1])
    current_pe = round(current_price / current_eps, 1) if current_eps != 0 else None
    return {
        "points": points, "min": round(min(values), 1), "max": round(max(values), 1),
        "median": round(float(pd.Series(values).median()), 1), "current": current_pe,
        "n": len(points)
    }

# ============================================================================
# ADDITION 2 — 13F INSTITUTIONAL OWNERSHIP CHANGE (QoQ diff via SEC EDGAR)
# ============================================================================

@st.cache_data(ttl=3600)
def sec_13f_ownership_change(ticker, cik=None):
    """
    Pull two consecutive 13F filings from EDGAR, diff them to show
    who bought/sold/new/exited this quarter vs last quarter.
    """
    if not cik:
        _, cik = fetch_sec_filings(ticker)
    if not cik: return None
    hdrs = {"User-Agent": "Bloomberg-Terminal contact@research.com"}
    try:
        r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=hdrs, timeout=8)
        recent = r.json().get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accs = recent.get("accessionNumber", [])
        dates = recent.get("filingDate", [])
        # Find 13F-HR filings
        filings_13f = [(acc, date) for form, acc, date in zip(forms, accs, dates) if form in ("13F-HR", "13F")]
        if len(filings_13f) < 2: return None
        def parse_13f(acc):
            acdn = acc.replace("-", "")
            # Get filing index
            idx_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acdn}/{acc}-index.htm"
            r2 = requests.get(idx_url, headers=hdrs, timeout=8)
            # Try to find infotable XML
            import re
            links = re.findall(r'href="([^"]+\.xml)"', r2.text, re.IGNORECASE)
            info_links = [l for l in links if "infotable" in l.lower() or "form13f" in l.lower()]
            if not info_links:
                links2 = re.findall(r'href="([^"]*)"', r2.text)
                info_links = [l for l in links2 if l.endswith(".xml")]
            if not info_links: return None
            xml_url = "https://www.sec.gov" + info_links[0] if info_links[0].startswith("/") else info_links[0]
            r3 = requests.get(xml_url, headers=hdrs, timeout=10)
            if r3.status_code != 200: return None
            # Parse holdings
            holdings = {}
            names = re.findall(r"<nameOfIssuer>(.*?)</nameOfIssuer>", r3.text, re.IGNORECASE)
            values = re.findall(r"<value>(.*?)</value>", r3.text, re.IGNORECASE)
            shrqtys = re.findall(r"<sshPrnamt>(.*?)</sshPrnamt>", r3.text, re.IGNORECASE)
            for name, val, qty in zip(names, values, shrqtys):
                try: holdings[name.strip()] = {"value_k": int(val.strip()), "shares": int(qty.strip())}
                except: pass
            return holdings
        curr_acc, curr_date = filings_13f[0]
        prev_acc, prev_date = filings_13f[1]
        curr = parse_13f(curr_acc)
        prev = parse_13f(prev_acc)
        if not curr or not prev: return None
        rows = []
        all_names = set(list(curr.keys())[:50])
        for name in all_names:
            c = curr.get(name, {})
            p = prev.get(name, {})
            c_val = c.get("value_k", 0) or 0
            p_val = p.get("value_k", 0) or 0
            c_shr = c.get("shares", 0) or 0
            p_shr = p.get("shares", 0) or 0
            chg = c_shr - p_shr
            if abs(c_val) < 100: continue
            status = "New" if p_shr == 0 else "Exited" if c_shr == 0 else "Increased" if chg > 0 else "Decreased" if chg < 0 else "Unchanged"
            rows.append({"Holder": name, "Curr Shares": f"{c_shr:,}", "Prev Shares": f"{p_shr:,}",
                         "Change": f"{chg:+,}", "Status": status, "Value($K)": f"{c_val:,}"})
        if not rows: return None
        df = pd.DataFrame(rows)
        order = {"New": 0, "Increased": 1, "Decreased": 2, "Exited": 3, "Unchanged": 4}
        df["_ord"] = df["Status"].map(order)
        df = df.sort_values("_ord").drop(columns=["_ord"]).head(30)
        return {"df": df, "curr_date": curr_date, "prev_date": prev_date}
    except: return None

# ============================================================================
# ADDITION 3 — EARNINGS TRANSCRIPT NLP (key phrase extraction from 8-K)
# ============================================================================

BULLISH_PHRASES = [
    "raised guidance", "raised our guidance", "increased guidance", "raised full year",
    "beat expectations", "exceeded expectations", "above expectations", "record revenue",
    "record quarter", "strong demand", "accelerating growth", "expanding margins",
    "margin expansion", "share buyback", "repurchase", "dividend increase",
    "raised dividend", "market share gains", "outperformed", "ahead of plan",
    "strong pipeline", "robust demand", "raised outlook", "positive momentum",
    "exceeded our expectations", "better than expected", "strong execution"
]

BEARISH_PHRASES = [
    "lowered guidance", "reduced guidance", "below expectations", "missed expectations",
    "slower growth", "headwinds", "macro uncertainty", "challenging environment",
    "increased competition", "margin pressure", "cost pressures", "supply chain",
    "inventory build", "deferred purchases", "cautious outlook", "pausing investments",
    "restructuring", "layoffs", "workforce reduction", "weaker demand",
    "softness in demand", "disappointing", "fell short", "below plan",
    "suspended guidance", "withdrew guidance", "challenging macro"
]

GUIDANCE_PHRASES = [
    "guidance", "outlook", "expect", "anticipate", "forecast", "project",
    "full year", "next quarter", "fiscal year", "annual revenue"
]

def analyze_transcript_nlp(text):
    """Extract key signals from 8-K earnings call text."""
    if not text: return None
    lower = text.lower()
    bullish_hits = [p for p in BULLISH_PHRASES if p in lower]
    bearish_hits = [p for p in BEARISH_PHRASES if p in lower]
    guidance_hits = [p for p in GUIDANCE_PHRASES if p in lower]
    bull_score = len(bullish_hits)
    bear_score = len(bearish_hits)
    total = bull_score + bear_score
    if total == 0:
        tone = "Neutral / Insufficient data"
        tone_color = "#94a3b8"
    elif bull_score > bear_score * 1.5:
        tone = "Bullish 🟢"
        tone_color = "#34d399"
    elif bear_score > bull_score * 1.5:
        tone = "Bearish 🔴"
        tone_color = "#f87171"
    else:
        tone = "Mixed 🟡"
        tone_color = "#facc15"
    # Extract sentences containing guidance keywords
    sentences = [s.strip() for s in re.split(r"[.!?]", text) if len(s.strip()) > 30]
    guidance_sentences = [s for s in sentences if any(g in s.lower() for g in ["guidance", "expect", "outlook", "full year", "next quarter"])][:5]
    return {
        "tone": tone, "tone_color": tone_color,
        "bull_score": bull_score, "bear_score": bear_score,
        "bullish_hits": bullish_hits[:8], "bearish_hits": bearish_hits[:8],
        "guidance_sentences": guidance_sentences,
        "has_guidance": len(guidance_hits) > 2,
    }

# ============================================================================
# ADDITION 4 — ENHANCED 8-K FETCH that also does NLP automatically
# ============================================================================

@st.cache_data(ttl=3600)
def fetch_8k_with_nlp(ticker, cik=None):
    """Fetch 8-K and immediately run NLP on it."""
    if not cik:
        _, cik = fetch_sec_filings(ticker)
    if not cik: return None
    hdrs = {"User-Agent": "Bloomberg-Terminal contact@research.com"}
    try:
        r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=hdrs, timeout=8)
        recent = r.json().get("filings", {}).get("recent", {})
        forms = recent.get("form", []); accs = recent.get("accessionNumber", [])
        docs = recent.get("primaryDocument", []); dates = recent.get("filingDate", [])
        for form, acc, doc, date in zip(forms, accs, docs, dates):
            if form == "8-K":
                acdn = acc.replace("-", "")
                url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acdn}/{doc}"
                r2 = requests.get(url, headers=hdrs, timeout=10)
                if r2.status_code == 200:
                    text = r2.text
                    clean = re.sub(r"<[^>]+>", " ", text)
                    clean = re.sub(r"\s+", " ", clean).strip()
                    lower = clean.lower()
                    kpos = []
                    for kw in ["revenue", "earnings", "net income", "eps", "per share", "guidance", "outlook"]:
                        idx = lower.find(kw)
                        if idx > 0: kpos.append(idx)
                    if kpos:
                        start = max(0, min(kpos) - 200)
                        snippet = clean[start:start+4000]
                        nlp = analyze_transcript_nlp(snippet)
                        return {"date": date, "url": url, "text": snippet,
                                "full_len": len(clean), "nlp": nlp}
        return None
    except: return None

# ============================================================================
# ADDITION 5 — HISTORICAL P/E BAND CHART
# ============================================================================

def pe_band_chart(band_data, current_price):
    """Plotly chart showing P/E over time with min/median/max bands."""
    if not band_data or not band_data.get("points"): return None
    df = pd.DataFrame(band_data["points"])
    df["date"] = pd.to_datetime(df["date"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df["pe"], mode="lines+markers",
                              name="Trailing P/E", line=dict(color="#38bdf8", width=2),
                              marker=dict(size=6)))
    fig.add_hline(y=band_data["median"], line=dict(color="#facc15", dash="dash", width=1.5),
                  annotation_text=f"Median {band_data['median']}x")
    fig.add_hline(y=band_data["max"], line=dict(color="#f87171", dash="dot", width=1),
                  annotation_text=f"High {band_data['max']}x")
    fig.add_hline(y=band_data["min"], line=dict(color="#34d399", dash="dot", width=1),
                  annotation_text=f"Low {band_data['min']}x")
    if band_data.get("current"):
        fig.add_hline(y=band_data["current"], line=dict(color="#a78bfa", width=2),
                      annotation_text=f"Current {band_data['current']}x")
    fig.update_layout(height=280, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#94a3b8"), margin=dict(l=10, r=80, t=10, b=10),
                      xaxis=dict(gridcolor="rgba(148,163,184,0.06)"),
                      yaxis=dict(gridcolor="rgba(148,163,184,0.06)", title="P/E Multiple"),
                      legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10)))
    return fig


# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(page_title="Bloomberg AI Terminal",page_icon="◆",layout="wide")
    inject_css()
    h1,h2=st.columns([4,1])
    with h1:
        st.markdown(f"""<p class="app-title">◆ Bloomberg AI Institutional Terminal</p>
        <p class="app-subtitle">{APP_VERSION} · AI DECISION ENGINE · FREE DATA · {datetime.datetime.now().strftime("%A %d %B %Y")}</p>""",unsafe_allow_html=True)
    with h2:
        st.markdown(f'<div style="text-align:right;padding-top:8px;"><span class="app-badge">{APP_VERSION}</span></div>',unsafe_allow_html=True)
    with st.spinner(""): render_strip(fetch_strip())
    # API key status bar
    k1,k2,k3=st.columns(3)
    with k1:
        if FMP_API_KEY and FMP_API_KEY.strip():
            st.success(f"✅ FMP Key set ({FMP_API_KEY[:4]}...)")
        else:
            st.warning("⚠️ FMP_API_KEY empty — set in file line 36")
    with k2:
        if TIINGO_API_KEY and TIINGO_API_KEY.strip():
            st.success(f"✅ Tiingo Key set ({TIINGO_API_KEY[:4]}...)")
        else:
            st.info("ℹ️ TIINGO_API_KEY empty — set in file line 37")
    with k3:
        try:
            from scipy.stats import norm
            st.success("✅ scipy installed — Greeks enabled")
        except:
            st.warning("⚠️ scipy missing — run: pip install scipy")
    mode=st.radio("",["📊 Single Stock","📁 My Portfolio"],horizontal=True,label_visibility="collapsed")
    if mode=="📊 Single Stock": run_stock()
    else: run_portfolio()

def run_stock():
    c1,c2,c3=st.columns([3,1,1])
    with c1: ticker=st.text_input("SYMBOL","AMD").upper()
    with c2:
        st.markdown("<div style='height:28px'></div>",unsafe_allow_html=True)
        go_=st.button("⚡ Generate Report",use_container_width=True)
    with c3:
        st.markdown("<div style='height:28px'></div>",unsafe_allow_html=True)
        if st.button("🔄 Clear Cache",use_container_width=True): st.cache_data.clear(); st.rerun()
    if not go_: return

    with st.spinner(f"Pulling full intelligence on {ticker}..."):
        try:
            ann,qtr=fetch_stmts(ticker); hist,info=fetch_price_info(ticker)
            ext=fetch_ext(ticker); raw_news=fetch_news_yf(ticker)
            opts=fetch_opts(ticker); macro=fetch_macro(); sec_filings,cik=fetch_sec_filings(ticker)
        except Exception as e:
            st.error(f"Data error: {e}"); return

    if ann.empty: st.error("No financial data — check ticker."); return

    ratios=compute_ratios(ann,qtr); pils=score_pillars(ratios); rd,rs_=roce_flag(qtr)
    val=val_timing(hist,info,"HOLD"); analyst=analyst_d(info)
    own=ownership_d(info,ext.get("itx")); short=short_d(info)
    tech=compute_tech(hist); for_r=forensic(ratios); news=analyze_news_yf(raw_news)
    greeks=compute_greeks(opts,tech["price"] if tech else None) if opts else None
    with st.spinner("Earnings intelligence..."): ei=earnings_intel(ticker,tech["ts"] if tech else 50,pils.get("Quality",{}).get("score") or 50)
    sc,verdict,grade,bd=inst_score(ratios,pils,val,analyst,own,short,tech,ei,for_r["flags"],macro)
    val=val_timing(hist,info,verdict)
    th=generate_thesis(ticker,verdict,ratios,pils,val,analyst,tech,for_r,ei,macro,sc)
    price_now=tech["price"] if tech else 0
    save_pred(ticker,verdict,sc,price_now)

    vc=VERDICT_COLORS.get(verdict,"#94a3b8"); name=info.get("longName",ticker)
    mc_=info.get("marketCap",0); mcs=f"${mc_/1e12:.2f}T" if mc_>1e12 else f"${mc_/1e9:.1f}B" if mc_ else "N/A"
    h52t=f" · 52W {tech['l52']}—{tech['h52']}" if tech else ""
    st.markdown(f"""<div class="glass-card">
    <div class="card-label">{info.get("sector","Unknown")} · {info.get("industry","Unknown")} · {mcs}{h52t}</div>
    <h2 style="margin:4px 0 10px;">{name} <span style="color:#475569;font-size:16px;">({ticker})</span></h2>
    <span class="verdict-badge" style="color:{vc};background:{vc}18;">{verdict}</span>
    &nbsp;&nbsp;<span style="font-family:'JetBrains Mono';color:#64748b;font-size:14px;">Grade <b style="color:{vc};">{grade}</b> · {sc}/100</span>
    </div>""",unsafe_allow_html=True)

    if rd: st.warning("⚠️ ROCE declining: "+" → ".join(f"{d}:{v}%" for d,v in rs_))
    for f in for_r["flags"]: st.error(f"🚩 {f}")

    sh("Institutional Decision Score")
    g1,g2,g3,g4,g5=st.columns(5)
    with g1: st.plotly_chart(gauge(sc,"INST. SCORE",vc),use_container_width=True)
    with g2: st.plotly_chart(gauge(pils.get("Quality",{}).get("score") or 0,"QUALITY","#34d399"),use_container_width=True)
    with g3: st.plotly_chart(gauge(ei.get("EPS_Beat",50),"EARNINGS BEAT","#22d3ee"),use_container_width=True)
    with g4: st.plotly_chart(gauge(tech["ts"] if tech else 50,"TECHNICAL","#a78bfa"),use_container_width=True)
    with g5:
        sf=short.get("Short % Float") or 0
        st.plotly_chart(gauge(max(0,min(100,100-sf*3)),"SAFETY","#fb923c"),use_container_width=True)

    sh("Score Breakdown")
    bc1,bc2=st.columns([3,2])
    with bc1: st.plotly_chart(score_bar(bd),use_container_width=True)
    with bc2:
        st.markdown('<div class="glass-card"><div class="card-label">Factor Points</div>',unsafe_allow_html=True)
        for k,v in sorted(bd.items(),key=lambda x:-x[1]):
            clr="#34d399" if v>=7 else "#facc15" if v>=4 else "#f87171"
            st.markdown(f'<div style="display:flex;justify-content:space-between;margin-bottom:5px;font-size:12px;"><span style="color:#cbd5e1;">{k}</span><span style="font-family:JetBrains Mono;color:{clr};font-weight:700;">{v}</span></div>',unsafe_allow_html=True)
        st.markdown(f'<div style="border-top:1px solid rgba(148,163,184,0.15);margin-top:6px;padding-top:6px;display:flex;justify-content:space-between;font-size:14px;"><span style="color:#f1f5f9;font-weight:700;">TOTAL</span><span style="font-family:JetBrains Mono;color:{vc};font-weight:800;">{sc}/100</span></div>',unsafe_allow_html=True)
        st.markdown("</div>",unsafe_allow_html=True)

    sh("Key Metrics")
    m1,m2,m3,m4,m5,m6,m7,m8=st.columns(8)
    m1.metric("Price",f"${price_now:.2f}" if price_now else "N/A"); m2.metric("Rev YoY",f"{ratios.get('Revenue YoY %','N/A')}%")
    m3.metric("ROCE",f"{ratios.get('ROCE %','N/A')}%"); m4.metric("Net Margin",f"{ratios.get('Net Margin %','N/A')}%")
    m5.metric("FCF Margin",f"{ratios.get('FCF Margin %','N/A')}%"); m6.metric("ROE",f"{ratios.get('ROE %','N/A')}%")
    m7.metric("D/E",f"{ratios.get('Debt/Equity','N/A')}"); m8.metric("Beat Prob",f"{ei.get('EPS_Beat',50)}%")

    sh("🤖 AI Investment Thesis")
    st.markdown(f'<div class="glass-card">{th.replace(chr(10),"<br>")}</div>',unsafe_allow_html=True)

    if tech:
        sh("Price Action · 2Y + Bollinger Bands")
        st.markdown('<div class="glass-card" style="padding:12px;">',unsafe_allow_html=True)
        st.plotly_chart(price_chart(hist,tech,ticker),use_container_width=True)
        st.markdown("</div>",unsafe_allow_html=True)

    # ── TABS ──
    tabs=st.tabs(["📊 Pillars","🎯 Earnings","💰 Valuation","📰 News",
                  "📈 Technicals","🏛️ Ownership","🩳 Short & Options","⚙️ Greeks",
                  "🌍 Macro","🚩 Forensics","⚖️ Peers","📄 SEC & Transcripts",
                  "📐 Segments","🔁 Calibration","👤 Insiders","📜 Financials"])

    with tabs[0]:
        cols=st.columns(4)
        for i,(p,res) in enumerate(pils.items()):
            with cols[i]:
                sc2=res["score"]; clr="#34d399" if (sc2 or 0)>=70 else "#facc15" if (sc2 or 0)>=50 else "#f87171"
                st.markdown(f'<div class="glass-card"><div class="card-label">{p}</div><div style="font-family:JetBrains Mono;font-size:26px;font-weight:800;color:{clr};">{sc2 or "N/A"}</div><div style="color:{clr};font-size:11px;font-weight:700;margin-bottom:8px;">{res["verdict"]}</div>',unsafe_allow_html=True)
                for nm,v,s in res["detail"]:
                    mk="✅" if s==2 else "⚠️" if s==1 else "❌" if s==0 else "—"
                    vs=f"{v:.1f}" if isinstance(v,(int,float)) and not pd.isna(v) else "N/A"
                    st.markdown(f'<div style="font-size:11px;color:#94a3b8;margin-bottom:3px;">{mk} {nm}: <b style="color:#e2e8f0;">{vs}</b></div>',unsafe_allow_html=True)
                st.markdown("</div>",unsafe_allow_html=True)
        sh("DuPont ROE"); dp=st.columns(5)
        dp[0].metric("ROE %",ratios.get("ROE %","N/A")); dp[1].metric("Net Margin %",ratios.get("Net Margin %","N/A"))
        dp[2].metric("Asset Turnover",ratios.get("Asset Turnover","N/A")); dp[3].metric("Equity Multiplier",ratios.get("Equity Multiplier","N/A")); dp[4].metric("ROA %",ratios.get("ROA %","N/A"))
        sh("FCF Quality"); fq=st.columns(3)
        fq[0].metric("FCF($B)",ratios.get("FCF($B)","N/A")); fq[1].metric("FCF Margin %",ratios.get("FCF Margin %","N/A")); fq[2].metric("FCF/Net Income",ratios.get("FCF/Net Income","N/A"))

    with tabs[1]:
        sh("Earnings Intelligence")
        ea,eb=st.columns(2)
        with ea:
            br=ei.get("beat_rate"); brc="#34d399" if br and br>=70 else "#facc15" if br and br>=50 else "#f87171"
            st.markdown(f'''<div class="glass-card"><div class="card-label">Next Report</div>
            <p style="font-family:JetBrains Mono;font-size:13px;line-height:2.2;">
            Date &nbsp;<b style="float:right;">{ei.get("next_date","Unknown")}</b><br>
            Consensus EPS &nbsp;<b style="float:right;">{ei.get("consensus_eps","N/A")}</b><br>
            Revision Trend &nbsp;<b style="float:right;">{ei.get("revision","Unknown")}</b><br>
            Beat Rate &nbsp;<b style="float:right;color:{brc};">{br or "N/A"}%</b><br>
            Avg Surprise &nbsp;<b style="float:right;">{ei.get("avg_surp","N/A")}%</b><br>
            Beat Probability &nbsp;<b style="float:right;color:#38bdf8;">{ei.get("EPS_Beat",50)}%</b>
            </p></div>''',unsafe_allow_html=True)
        with eb:
            fc=fmp_earnings_cal(ticker)
            if fc is not None and not fc.empty:
                st.markdown('<div class="glass-card"><div class="card-label">FMP Earnings Calendar</div>',unsafe_allow_html=True)
                st.dataframe(fc,use_container_width=True,hide_index=True); st.markdown("</div>",unsafe_allow_html=True)
            elif opts and greeks:
                st.markdown(f'<div class="glass-card"><div class="card-label">Options Implied Move</div><p style="font-family:JetBrains Mono;font-size:14px;">Expiry: {opts["exp"]}<br>±{greeks.get("impl_move","N/A")}%</p></div>',unsafe_allow_html=True)
        if ei.get("history"):
            st.markdown('<div class="glass-card"><div class="card-label">Last 8 Quarters</div>',unsafe_allow_html=True)
            df_h=pd.DataFrame(ei["history"]); st.dataframe(df_h,use_container_width=True,hide_index=True)
            if len(df_h)>1:
                fig_ei=go.Figure(go.Bar(x=df_h["Q"],y=df_h["Surp%"],marker_color=["#34d399" if v>0 else "#f87171" for v in df_h["Surp%"]],name="Surprise %"))
                fig_ei.update_layout(height=200,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#94a3b8"),margin=dict(l=10,r=10,t=10,b=10),xaxis=dict(gridcolor="rgba(148,163,184,0.06)"),yaxis=dict(gridcolor="rgba(148,163,184,0.06)"))
                st.plotly_chart(fig_ei,use_container_width=True)
            st.markdown("</div>",unsafe_allow_html=True)
        sh("Analyst Upgrades/Downgrades")
        # Free via yfinance first, FMP as secondary
        ud = yf_upgrades_downgrades(ticker)
        if ud is not None and not ud.empty:
            st.markdown('<div class="glass-card"><div class="card-label">Analyst Rating Changes (yfinance — free)</div>', unsafe_allow_html=True)
            st.dataframe(ud, use_container_width=True, hide_index=True)
            st.markdown("</div>", unsafe_allow_html=True)
            # Also show summary
            rs = yf_recommendations_summary(ticker)
            if rs is not None and not rs.empty:
                sh("Analyst Consensus Summary")
                st.dataframe(rs, use_container_width=True, hide_index=True)
        else:
            # Try FMP
            ud_fmp = fmp_upgrades(ticker)
            if ud_fmp is not None and not ud_fmp.empty:
                st.dataframe(ud_fmp, use_container_width=True, hide_index=True)
            else:
                st.info("No recent upgrades/downgrades found for this ticker.")
        sh("FMP Price Targets & Estimates")
        fa=fmp_analyst(ticker)
        if fa.get("targets") is not None: st.dataframe(fa["targets"],use_container_width=True,hide_index=True)
        if fa.get("estimates") is not None: st.dataframe(fa["estimates"],use_container_width=True,hide_index=True)

    with tabs[2]:
        sh("Valuation Multiples")
        mults=val_mults(info); mc2=st.columns(7)
        for i,(k,v) in enumerate(mults.items()): mc2[i].metric(k,f"{v:.2f}" if v and not pd.isna(v) else "N/A")
        if val:
            st.markdown(f'''<div class="glass-card"><div class="card-label">2Y Range Position</div>
            <p style="font-family:JetBrains Mono;font-size:13px;line-height:2.2;">
            Zone &nbsp;<b style="float:right;">{val["zone"]}</b><br>
            Position &nbsp;<b style="float:right;">{val["pos"]}%</b><br>
            2Y High &nbsp;<b style="float:right;">${val["hi"]:.2f}</b><br>
            2Y Low &nbsp;<b style="float:right;">${val["lo"]:.2f}</b><br>
            Action &nbsp;<b style="float:right;">{val["action"]}</b></p></div>''',unsafe_allow_html=True)
        sh("Historical P/E Band (real point-in-time trailing P/E)")
        band = pe_band(hist, qtr)
        if band:
            bp1,bp2,bp3,bp4,bp5=st.columns(5)
            bp1.metric("P/E Low",f"{band['min']}x"); bp2.metric("P/E Median",f"{band['median']}x")
            bp3.metric("P/E High",f"{band['max']}x"); bp4.metric("P/E Current",f"{band['current']}x" if band['current'] else "N/A")
            bp5.metric("Data Points",band["n"])
            fig_pe=pe_band_chart(band,price_now)
            if fig_pe:
                st.markdown('<div class="glass-card" style="padding:12px;">',unsafe_allow_html=True)
                st.plotly_chart(fig_pe,use_container_width=True)
                st.markdown("</div>",unsafe_allow_html=True)
            if band.get("current") and band.get("median"):
                prem=round((band["current"]-band["median"])/band["median"]*100,1)
                if prem>20: st.warning(f"Trading at {prem}% PREMIUM to historical median P/E")
                elif prem<-20: st.success(f"Trading at {abs(prem)}% DISCOUNT to historical median P/E — historically cheap")
                else: st.info(f"Trading near historical median P/E ({prem:+.1f}%)")
        else: st.info("Need 4+ quarters of EPS history for P/E band.")
        sh("DCF Intrinsic Value")
        dc1,dc2,dc3,dc4=st.columns(4)
        defg=ratios.get("Revenue YoY %") or 8; defg=min(max(defg/100,0.02),0.25)
        gi=dc1.slider("FCF Growth",0.0,0.30,float(round(defg,2)),0.01,key="g")
        di=dc2.slider("Discount (WACC)",0.05,0.15,0.10,0.005,key="d")
        ti=dc3.slider("Terminal Growth",0.0,0.04,0.025,0.0025,key="t")
        yi=dc4.selectbox("Years",[3,5,7,10],index=1,key="y")
        dcf_r=dcf(ann,qtr,info,gi,di,ti,yi)
        if dcf_r:
            mos=round((dcf_r["fair"]-price_now)/price_now*100,1) if price_now else None
            r1,r2,r3=st.columns(3)
            r1.metric("Fair Value/Share",f"${dcf_r['fair']}"); r2.metric("Current Price",f"${price_now:.2f}"); r3.metric("Margin of Safety",f"{mos}%" if mos else "N/A")
            if mos:
                if mos>=20: st.success("Below DCF fair value ✅")
                elif mos<=-20: st.warning("Above DCF fair value ⚠️")
                else: st.info("Near DCF fair value")
            st.caption(f"EV ${dcf_r['ev_b']}B · TV {dcf_r['tv_pct']}% of EV")
            st.dataframe(pd.DataFrame(dcf_r["proj"]),use_container_width=True,hide_index=True)
        else: st.info("DCF unavailable — negative/missing FCF")

    with tabs[3]:
        df_news_obb=obb_news(ticker)
        if df_news_obb is None: df_news_obb=fmp_news(ticker)
        if TIINGO_API_KEY: df_ti=tiingo_news(ticker)
        else: df_ti=None
        ni=news; sc_c="#34d399" if "Positive" in ni["label"] else "#f87171" if "Negative" in ni["label"] else "#facc15"
        st.markdown(f'<div class="glass-card"><div class="card-label">Sentiment</div><span style="font-size:18px;font-weight:800;color:{sc_c};">{ni["label"]}</span><span style="color:#64748b;font-size:12px;margin-left:12px;">avg {ni["avg"]} · {len(ni["arts"])} headlines</span></div>',unsafe_allow_html=True)
        src=df_news_obb if df_news_obb is not None and not df_news_obb.empty else None
        if src is not None:
            sh("News via OpenBB/Benzinga/FMP")
            tc=next((c for c in src.columns if "title" in c.lower()),None)
            uc=next((c for c in src.columns if "url" in c.lower() or "link" in c.lower()),None)
            pc=next((c for c in src.columns if "source" in c.lower() or "publisher" in c.lower() or "author" in c.lower()),None)
            for _,row in src.head(20).iterrows():
                t_=str(row.get(tc,"") if tc else row.iloc[0]); u_=str(row.get(uc,"#") if uc else "#"); p_=str(row.get(pc,"") if pc else "")
                s_=sent(t_); sc_2="#34d399" if s_>0 else "#f87171" if s_<0 else "#64748b"
                st.markdown(f'<div style="padding:7px 0;border-bottom:1px solid rgba(148,163,184,0.07);"><a href="{u_}" target="_blank" style="color:#e2e8f0;text-decoration:none;font-size:12px;">{t_}</a><span style="color:#475569;font-size:10px;"> — {p_}</span><span style="font-family:JetBrains Mono;font-size:10px;color:{sc_2};float:right;">{"▲" if s_>0 else "▼" if s_<0 else "●"} {round(s_,2)}</span></div>',unsafe_allow_html=True)
        else:
            for a in ni["arts"]:
                ac="#34d399" if a["score"]>0 else "#f87171" if a["score"]<0 else "#64748b"
                st.markdown(f'<div style="padding:7px 0;border-bottom:1px solid rgba(148,163,184,0.07);"><a href="{a["link"]}" target="_blank" style="color:#e2e8f0;text-decoration:none;font-size:12px;">{a["title"]}</a><span style="color:#475569;font-size:10px;"> — {a["pub"]}</span><span style="font-family:JetBrains Mono;font-size:10px;color:{ac};float:right;">{"▲" if a["score"]>0 else "▼" if a["score"]<0 else "●"} {a["score"]}</span></div>',unsafe_allow_html=True)

    with tabs[4]:
        if tech:
            tc1,tc2,tc3,tc4,tc5,tc6=st.columns(6)
            tc1.metric("Price",f"${tech['price']:.2f}"); tc2.metric("RSI(14)",f"{tech['rsi']} ({tech['rsi_n']})")
            tc3.metric("MACD",tech["macd_t"]); tc4.metric("ATR(14)",f"${tech['atr']}" if tech["atr"] else "N/A")
            tc5.metric("OBV",tech["obv_t"]); tc6.metric("BB Pos %",f"{tech['bbp']}%")
            ta_a,ta_b=st.columns(2)
            with ta_a:
                st.markdown(f'''<div class="glass-card"><div class="card-label">Technical Summary</div>
                <p style="font-family:JetBrains Mono;font-size:12px;line-height:2.2;">
                Trend &nbsp;<b style="float:right;">{tech["trend"]}</b><br>
                SMA 20 &nbsp;<b style="float:right;">${tech["sma20"]:.2f}</b><br>
                SMA 50 &nbsp;<b style="float:right;">${tech["sma50"]:.2f}</b><br>
                SMA 200 &nbsp;<b style="float:right;">${tech["sma200"]:.2f}</b><br>
                BB Upper &nbsp;<b style="float:right;">${tech["bb_u"]:.2f}</b><br>
                BB Lower &nbsp;<b style="float:right;">${tech["bb_l"]:.2f}</b><br>
                52W High &nbsp;<b style="float:right;">${tech["h52"]} ({tech["dh"]}%)</b><br>
                52W Low &nbsp;<b style="float:right;">${tech["l52"]} (+{tech["dl"]}%)</b><br>
                Tech Score &nbsp;<b style="float:right;color:#38bdf8;">{tech["ts"]}/100</b>
                </p></div>''',unsafe_allow_html=True)
            with ta_b:
                rs_d=fetch_rs(ticker)
                if rs_d:
                    rsc="#34d399" if rs_d["trend"]=="Outperforming" else "#f87171"
                    fill_rgba="rgba(52,211,153,0.08)" if rsc=="#34d399" else "rgba(248,113,113,0.08)"
                    st.markdown(f'<div class="glass-card"><div class="card-label">RS vs SPY (1Y)</div><span style="color:{rsc};font-size:15px;font-weight:700;">{rs_d["trend"]}</span><span style="color:#64748b;font-size:12px;margin-left:8px;">RS {rs_d["ratio"]}</span></div>',unsafe_allow_html=True)
                    fig_rs=go.Figure(go.Scatter(x=rs_d["series"].index,y=rs_d["series"],mode="lines",line=dict(color=rsc,width=2),fill="tozeroy",fillcolor=fill_rgba))
                    fig_rs.add_hline(y=1,line=dict(color="#64748b",dash="dot"))
                    fig_rs.update_layout(height=180,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#94a3b8"),margin=dict(l=10,r=10,t=10,b=10),xaxis=dict(gridcolor="rgba(148,163,184,0.06)"),yaxis=dict(gridcolor="rgba(148,163,184,0.06)"))
                    st.plotly_chart(fig_rs,use_container_width=True)
        else: st.info("Need 50+ days price history.")

    with tabs[5]:
        oa,ob=st.columns(2)
        with oa:
            st.markdown('<div class="glass-card"><div class="card-label">Ownership Summary</div>',unsafe_allow_html=True)
            for k,v in own.items(): st.markdown(f'<div style="font-size:12px;color:#94a3b8;margin-bottom:5px;">{k}: <b style="color:#e2e8f0;float:right;">{v or "N/A"}</b></div>',unsafe_allow_html=True)
            st.markdown("</div>",unsafe_allow_html=True)
        with ob:
            ih=obb_inst(ticker)
            if ih is None: ih=fmp_inst(ticker)
            if ih is None: ih=ext.get("inst")
            if ih is not None and not ih.empty:
                st.markdown('<div class="glass-card"><div class="card-label">Top Institutional Holders</div>',unsafe_allow_html=True)
                st.dataframe(ih.head(12),use_container_width=True,hide_index=True); st.markdown("</div>",unsafe_allow_html=True)
        sh("13F Institutional Ownership Change (Quarter vs Quarter)")
        if st.button("📊 Fetch 13F QoQ Changes",key="13f"):
            with st.spinner("Parsing SEC 13F filings — comparing this quarter vs last..."):
                qoq=sec_13f_ownership_change(ticker,cik)
            if qoq:
                st.caption(f"Comparing {qoq['curr_date']} vs {qoq['prev_date']}")
                df_qoq=qoq["df"]
                new_pos=df_qoq[df_qoq["Status"]=="New"]
                increased=df_qoq[df_qoq["Status"]=="Increased"]
                decreased=df_qoq[df_qoq["Status"]=="Decreased"]
                exited=df_qoq[df_qoq["Status"]=="Exited"]
                qq1,qq2,qq3,qq4=st.columns(4)
                qq1.metric("New Positions",len(new_pos))
                qq2.metric("Increased",len(increased))
                qq3.metric("Decreased",len(decreased))
                qq4.metric("Exited",len(exited))
                st.dataframe(df_qoq,use_container_width=True,hide_index=True)
            else:
                st.info("13F QoQ change not available. This works for companies that file 13F (mainly US-listed). The SEC data is delayed 45 days by law.")
        divs=ext.get("divs")
        if divs is not None and isinstance(divs,pd.Series) and len(divs)>0:
            sh("Dividend History")
            dy=info.get("dividendYield"); pr=info.get("payoutRatio")
            d1,d2,d3=st.columns(3)
            d1.metric("Div Yield %",f"{round(dy*100,2)}" if dy else "N/A"); d2.metric("Payout Ratio %",f"{round(pr*100,1)}" if pr else "N/A"); d3.metric("Annual Div/Share",f"${info.get('dividendRate','N/A')}")
            fig_d=go.Figure(go.Bar(x=divs.index,y=divs.values,marker_color="#38bdf8"))
            fig_d.update_layout(height=200,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#94a3b8"),margin=dict(l=10,r=10,t=10,b=10))
            st.plotly_chart(fig_d,use_container_width=True)

    with tabs[6]:
        sa,sb=st.columns(2)
        with sa:
            st.markdown('<div class="glass-card"><div class="card-label">Short Interest</div>',unsafe_allow_html=True)
            for k,v in short.items():
                vc_="#f87171" if k=="Short % Float" and v and v>10 else "#facc15" if k=="Short % Float" and v and v>5 else "#e2e8f0"
                st.markdown(f'<div style="font-size:12px;color:#94a3b8;margin-bottom:5px;">{k}: <b style="color:{vc_};float:right;">{v or "N/A"}</b></div>',unsafe_allow_html=True)
            st.markdown("</div>",unsafe_allow_html=True)
        with sb:
            if opts:
                pc_c="#f87171" if (opts.get("pc_oi") or 0)>1 else "#34d399"
                st.markdown(f'''<div class="glass-card"><div class="card-label">Options — {opts["exp"]}</div>
                <p style="font-family:JetBrains Mono;font-size:12px;line-height:2.2;">
                P/C OI &nbsp;<b style="float:right;color:{pc_c};">{opts.get("pc_oi","N/A")}</b><br>
                P/C Vol &nbsp;<b style="float:right;">{opts.get("pc_vol","N/A")}</b><br>
                Call OI &nbsp;<b style="float:right;">{opts.get("coi",0):,}</b><br>
                Put OI &nbsp;<b style="float:right;">{opts.get("poi",0):,}</b><br>
                Call IV% &nbsp;<b style="float:right;">{opts.get("ivc","N/A")}</b><br>
                Put IV% &nbsp;<b style="float:right;">{opts.get("ivp","N/A")}</b><br>
                Max Pain &nbsp;<b style="float:right;color:#facc15;">${opts.get("mp","N/A")}</b><br>
                Expiries &nbsp;<b style="float:right;">{len(opts.get("exps",[]))}</b>
                </p></div>''',unsafe_allow_html=True)
            else: st.info("No options data.")

    with tabs[7]:
        if greeks:
            ga,gb,gc=st.columns(3)
            with ga:
                cg=greeks.get("call",{})
                st.markdown('<div class="glass-card"><div class="card-label">ATM Call Greeks</div>',unsafe_allow_html=True)
                for k,v in cg.items(): st.markdown(f'<div style="font-size:12px;color:#94a3b8;margin-bottom:5px;">{k.title()}: <b style="color:#34d399;float:right;">{v}</b></div>',unsafe_allow_html=True)
                st.markdown("</div>",unsafe_allow_html=True)
            with gb:
                pg=greeks.get("put",{})
                st.markdown('<div class="glass-card"><div class="card-label">ATM Put Greeks</div>',unsafe_allow_html=True)
                for k,v in pg.items(): st.markdown(f'<div style="font-size:12px;color:#94a3b8;margin-bottom:5px;">{k.title()}: <b style="color:#f87171;float:right;">{v}</b></div>',unsafe_allow_html=True)
                st.markdown("</div>",unsafe_allow_html=True)
            with gc:
                st.markdown(f'''<div class="glass-card"><div class="card-label">Summary</div>
                <p style="font-family:JetBrains Mono;font-size:13px;line-height:2.2;">
                Impl. Move &nbsp;<b style="float:right;color:#facc15;">±{greeks.get("impl_move","N/A")}%</b><br>
                Call IV% &nbsp;<b style="float:right;">{greeks.get("civ","N/A")}</b><br>
                Put IV% &nbsp;<b style="float:right;">{greeks.get("piv","N/A")}</b><br>
                Days to Exp &nbsp;<b style="float:right;">{round(greeks.get("T",0)*365)}</b>
                </p></div>''',unsafe_allow_html=True)
        else:
            try:
                from scipy.stats import norm
                st.info("No options chain. scipy ✅ — Greeks will appear when options data exists.")
            except: st.warning("Install scipy: `pip install scipy` for Greeks.")

    with tabs[8]:
        sh("Macro Environment")
        mdisplay=[(k,v) for k,v in macro.items() if v is not None]
        mc_cols=st.columns(min(len(mdisplay),4))
        for i,(k,v) in enumerate(mdisplay): mc_cols[i%4].metric(k,f"{v}")
        curve=macro.get("Yield Curve(10-2Y)")
        if curve is not None:
            if curve<0: st.error(f"⚠️ Yield curve INVERTED {curve:.2f}%")
            else: st.success(f"✅ Yield curve NORMAL {curve:.2f}%")
        rr=macro.get("Real Rate")
        if rr is not None:
            if rr<0: st.success(f"Real rate NEGATIVE ({rr}%) — historically bullish for equities")
            else: st.info(f"Real rate POSITIVE ({rr}%) — restrictive environment")
        hy=macro.get("HY Spread")
        if hy: st.info(f"HY Credit Spread: {hy}% — {'Tight (risk-on)' if hy<3.5 else 'Wide (risk-off)' if hy>5 else 'Normal'}")
        sh("Economic Calendar")
        ec=obb_econ_cal()
        if ec is None: ec=fmp_econ_cal()
        if ec is not None and not ec.empty:
            st.dataframe(ec,use_container_width=True,hide_index=True)
        elif fmp_key_ok():
            st.warning("FMP key set but economic calendar returned no data. Trying FRED fallback...")
            # FRED doesn't have a calendar but we can show upcoming dates from known schedule
            st.info("Economic calendar requires FMP paid plan. FRED data above shows current macro readings.")
        else:
            st.info("Set FMP_API_KEY at top of file for economic calendar.")

    with tabs[9]:
        fc1,fc2,fc3,fc4=st.columns(4)
        fc1.metric("Accruals %",for_r["accrual"] or "N/A"); fc2.metric("Goodwill/Assets %",for_r["gw_pct"] or "N/A")
        fc3.metric("Receivables YoY %",for_r["ar_gr"] or "N/A"); fc4.metric("Revenue YoY %",for_r["rev_gr"] or "N/A")
        if for_r["flags"]:
            for f in for_r["flags"]: st.error(f"🚩 {f}")
        else: st.success("✅ No forensic red flags.")

    with tabs[10]:
        peers=PEER_MAP.get(ticker,[])
        if peers:
            with st.spinner("Pulling peers..."): rows=[peer_snap(p) for p in peers]; rows=[r for r in rows if r]
            if rows: st.dataframe(pd.DataFrame(rows).set_index("Ticker"),use_container_width=True)
        custom=st.text_input("Custom peers (comma-separated):",key="cp")
        if st.button("Compare",key="cmp"):
            pl=[t.strip().upper() for t in custom.split(",") if t.strip()]
            rows=[peer_snap(p) for p in pl]; rows=[r for r in rows if r]
            if rows: st.dataframe(pd.DataFrame(rows).set_index("Ticker"),use_container_width=True)

    with tabs[11]:
        if sec_filings:
            for f in sec_filings:
                bc={"10-K":"#38bdf8","10-Q":"#34d399","8-K":"#facc15","4":"#a78bfa","DEF 14A":"#fb923c"}.get(f["form"],"#94a3b8")
                st.markdown(f'<div style="padding:7px 0;border-bottom:1px solid rgba(148,163,184,0.07);"><span style="font-family:JetBrains Mono;font-weight:700;color:{bc};">{f["form"]}</span><span style="color:#64748b;font-size:11px;margin-left:10px;">{f["date"]}</span><a href="{f["url"]}" target="_blank" style="float:right;color:#38bdf8;font-size:11px;">EDGAR →</a></div>',unsafe_allow_html=True)
        else: st.info("SEC filings unavailable.")
        sh("Latest 8-K Earnings Transcript + NLP Analysis")
        if st.button("📄 Fetch & Analyse 8-K Transcript",key="trans"):
            with st.spinner("Scraping SEC EDGAR 8-K and running NLP..."):
                transcript=fetch_8k_with_nlp(ticker,cik)
            if transcript:
                nlp=transcript.get("nlp")
                if nlp:
                    sh("Management Tone Detection")
                    t1,t2,t3=st.columns(3)
                    t1.metric("Management Tone",nlp["tone"])
                    t2.metric("Bullish Signals",nlp["bull_score"])
                    t3.metric("Bearish Signals",nlp["bear_score"])
                    if nlp["bullish_hits"]:
                        st.markdown('<div class="glass-card"><div class="card-label">Bullish Phrases Detected</div>',unsafe_allow_html=True)
                        for ph in nlp["bullish_hits"]:
                            st.markdown(f'<div style="color:#34d399;font-size:12px;margin-bottom:4px;">✅ {ph}</div>',unsafe_allow_html=True)
                        st.markdown("</div>",unsafe_allow_html=True)
                    if nlp["bearish_hits"]:
                        st.markdown('<div class="glass-card"><div class="card-label">Bearish Phrases Detected</div>',unsafe_allow_html=True)
                        for ph in nlp["bearish_hits"]:
                            st.markdown(f'<div style="color:#f87171;font-size:12px;margin-bottom:4px;">⚠️ {ph}</div>',unsafe_allow_html=True)
                        st.markdown("</div>",unsafe_allow_html=True)
                    if nlp["guidance_sentences"]:
                        sh("Guidance / Outlook Sentences")
                        for s in nlp["guidance_sentences"]:
                            st.markdown(f'<div style="color:#facc15;font-size:12px;margin-bottom:6px;padding:6px;background:rgba(250,204,21,0.06);border-radius:6px;">📋 {s}</div>',unsafe_allow_html=True)
                st.markdown(f'<div class="glass-card"><div class="card-label">8-K Raw Text — {transcript["date"]} <a href="{transcript["url"]}" target="_blank" style="color:#38bdf8;">View full →</a></div><div style="font-size:11px;color:#94a3b8;line-height:1.7;white-space:pre-wrap;">{transcript["text"][:3000]}</div></div>',unsafe_allow_html=True)
                st.caption(f"Full document {transcript['full_len']:,} chars. Showing first 3,000 chars from earnings-relevant section.")
            else: st.info("8-K not found for this ticker. Works best with major US companies.")

    with tabs[12]:
        sh("Segment Revenue (10-K XBRL)")
        st.caption("Parses EDGAR XBRL — shows Azure vs Office vs Gaming etc.")
        if st.button("Parse Segment Data",key="seg"):
            with st.spinner("Parsing EDGAR XBRL (~15s)..."):
                seg_df=sec_segment_revenue(ticker,cik)
            if seg_df is not None and not seg_df.empty:
                st.dataframe(seg_df,use_container_width=True,hide_index=True)
                top=seg_df.dropna(subset=["Value($B)"]).nlargest(8,"Value($B)")
                fig_s=go.Figure(go.Bar(x=top["Value($B)"],y=top["Concept"],orientation="h",marker_color="#38bdf8",text=[f"${v}B" for v in top["Value($B)"]],textposition="outside"))
                fig_s.update_layout(height=300,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#94a3b8"),margin=dict(l=10,r=60,t=10,b=10),xaxis=dict(gridcolor="rgba(148,163,184,0.06)"),yaxis=dict(gridcolor="rgba(0,0,0,0)"))
                st.plotly_chart(fig_s,use_container_width=True)
            else: st.info("Segment XBRL not available. Best with large US companies (MSFT, AAPL, GOOGL).")

    with tabs[13]:
        calib=calibrate(ticker); hist_db=get_preds(ticker)
        if calib: st.metric("Directional Accuracy (10-day)",f"{calib['acc']}%",f"over {calib['n']} predictions")
        else: st.info("Run multiple analyses to build calibration history.")
        if hist_db:
            df_db=pd.DataFrame(hist_db,columns=["Date","Verdict","Score","Price"])
            df_db["Date"]=pd.to_datetime(df_db["Date"]).dt.strftime("%b %d, %H:%M")
            st.dataframe(df_db,use_container_width=True,hide_index=True)

    with tabs[14]:
        sh("Insider Transactions (SEC Form 4)")
        ins=obb_insider_t(ticker)
        if ins is None: ins=fmp_insider(ticker)
        if ins is None: ins=ext.get("itx")
        if ins is not None and not ins.empty:
            tc_=next((c for c in ins.columns if any(x in c.lower() for x in ["type","transaction","text"])),None)
            if tc_:
                buys=ins[ins[tc_].astype(str).str.contains("buy|purchase|acquire",case=False,na=False)]
                sells=ins[ins[tc_].astype(str).str.contains("sell|sale|dispose",case=False,na=False)]
                ic1,ic2=st.columns(2); ic1.metric("Insider Buys",len(buys)); ic2.metric("Insider Sells",len(sells))
            st.dataframe(ins,use_container_width=True,hide_index=True)
        elif fmp_key_ok():
            st.warning("FMP key set but insider data returned empty. This may need FMP paid plan, or no recent insider activity for this ticker.")
        else:
            st.info("Set FMP_API_KEY at top of file for insider transaction data.")

    with tabs[15]:
        ann_s=ann.sort_index(axis=1,ascending=False); st.subheader("Annual ($B)")
        st.dataframe(ann_s.iloc[:,:4].map(lambda x:round(x/1e9,3) if isinstance(x,(int,float)) and not pd.isna(x) and abs(x)>1e6 else x),use_container_width=True)
        qtr_s=qtr.sort_index(axis=1,ascending=False); st.subheader("Quarterly ($B)")
        st.dataframe(qtr_s.iloc[:,:8].map(lambda x:round(x/1e9,3) if isinstance(x,(int,float)) and not pd.isna(x) and abs(x)>1e6 else x),use_container_width=True)
        sh("FMP Ratios")
        fr=fmp_ratios(ticker)
        if fr is not None and not fr.empty: st.dataframe(fr.T,use_container_width=True)
        elif fmp_key_ok():
            st.warning("FMP key set but ratios returned empty for this ticker.")
        else:
            st.info("Set FMP_API_KEY at top of file for FMP ratio set.")
        sh("OpenBB Provider Status")
        if st.button("Test Providers",key="prov"):
            with st.spinner("Testing..."):
                status=obb_providers()
            for prov,res in status.items():
                clr="#34d399" if "working" in str(res) else "#facc15" if "no data" in str(res) else "#f87171"
                st.markdown(f'<div style="padding:5px 0;font-size:12px;"><span style="font-family:JetBrains Mono;color:{clr};">{prov}</span><span style="color:#64748b;margin-left:12px;">{res}</span></div>',unsafe_allow_html=True)

def run_portfolio():
    st.markdown('<div class="glass-card"><div class="card-label">Holdings: TICKER, SHARES, COST_BASIS per line</div>',unsafe_allow_html=True)
    dh="META,50,320\nGOOGL,20,140\nPLTR,100,25\nNVDA,10,500\nAMD,30,120\nAAPL,15,180"
    ht=st.text_area("",dh,height=130,label_visibility="collapsed"); st.markdown("</div>",unsafe_allow_html=True)
    if not st.button("⚡ Analyze Portfolio",use_container_width=True): return
    holdings=[]
    for line in ht.strip().split("\n"):
        parts=[p.strip() for p in line.split(",")]
        if len(parts)>=2 and parts[0]:
            try: holdings.append((parts[0].upper(),float(parts[1]),float(parts[2]) if len(parts)>2 and parts[2] else 0.0))
            except: continue
    if not holdings: st.error("No valid holdings."); return
    tks=[h[0] for h in holdings]
    with st.spinner("Pulling portfolio data..."):
        pdf=port_prices(tuple(tks)); an=port_analytics(pdf,holdings)
    if not an: st.error("Could not compute analytics."); return
    df=an["df"]; tv=an["tv"]; tpl=df["P/L"].sum()
    m1,m2,m3,m4=st.columns(4)
    m1.metric("Total Value",f"${tv:,.0f}"); m2.metric("Total P/L",f"${tpl:,.0f}"); m3.metric("Positions",len(df))
    ab=df["Beta"].mean() if df["Beta"].notna().any() else None; m4.metric("Portfolio Beta",f"{ab:.2f}" if ab else "N/A")
    sh("Holdings"); st.dataframe(df.set_index("Ticker"),use_container_width=True)
    var=an.get("var")
    if var:
        sh("Portfolio Risk — Value at Risk (Historical Simulation)")
        v1,v2,v3,v4=st.columns(4)
        v1.metric("VaR 95% (daily)",f"${var.get('VaR_95dollar',0):,.0f}",f"{var.get('VaR_95pct',0)}%")
        v2.metric("VaR 99% (daily)",f"${var.get('VaR_99dollar',0):,.0f}",f"{var.get('VaR_99pct',0)}%")
        v3.metric("CVaR 95%",f"${var.get('CVaR_95dollar',0):,.0f}",f"{var.get('CVaR_95pct',0)}%")
        v4.metric("Max Drawdown",f"{var.get('max_drawdown_pct',0):.1f}%")
        st.caption("VaR = max daily loss at confidence level. CVaR = avg loss beyond VaR. Historical simulation on 1Y data.")
        if var.get("port_rets") is not None:
            rets_s=var["port_rets"].sort_values()
            fig_var=go.Figure()
            fig_var.add_trace(go.Histogram(x=rets_s*100,nbinsx=50,name="Daily Returns %",marker_color="#38bdf8",opacity=0.7))
            fig_var.add_vline(x=var.get("VaR_95pct",0),line=dict(color="#facc15",dash="dash"),annotation_text="VaR 95%")
            fig_var.add_vline(x=var.get("VaR_99pct",0),line=dict(color="#f87171",dash="dash"),annotation_text="VaR 99%")
            fig_var.update_layout(height=250,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#94a3b8"),margin=dict(l=10,r=10,t=30,b=10),xaxis=dict(title="Daily Return %",gridcolor="rgba(148,163,184,0.06)"),yaxis=dict(gridcolor="rgba(148,163,184,0.06)"))
            st.plotly_chart(fig_var,use_container_width=True)
    sh("Sector Allocation")
    if an["sectors"]:
        sd=pd.DataFrame(list(an["sectors"].items()),columns=["Sector","Value"]); sd["Weight %"]=(sd["Value"]/tv*100).round(1); sd=sd.sort_values("Weight %",ascending=False)
        sc1,sc2=st.columns([2,3])
        with sc1: st.dataframe(sd.set_index("Sector"),use_container_width=True)
        with sc2:
            fig=go.Figure(go.Pie(labels=sd["Sector"],values=sd["Weight %"],hole=0.5,textfont=dict(size=10),marker=dict(colors=["#38bdf8","#34d399","#a78bfa","#facc15","#fb923c","#f87171","#22d3ee"])))
            fig.update_layout(height=240,paper_bgcolor="rgba(0,0,0,0)",margin=dict(l=0,r=0,t=0,b=0),showlegend=True,legend=dict(font=dict(color="#94a3b8",size=10)))
            st.plotly_chart(fig,use_container_width=True)
    if an.get("corr") is not None:
        sh("Correlation Matrix (1Y Returns)"); st.dataframe(an["corr"].round(2),use_container_width=True)

if __name__=="__main__":
    main()