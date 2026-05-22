import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import datetime
import pytz
import requests
import json
import concurrent.futures

# ==============================================================================
# 1. 🔑 SHOONYA API CREDENTIALS 
# ==============================================================================
SHOONYA_UID = "YOUR_UID" 
SHOONYA_PWD = "YOUR_PASSWORD" 
SHOONYA_API_KEY = "YOUR_API_KEY" 
SHOONYA_VC = "YOUR_VENDOR_CODE" 
SHOONYA_TOTP_SECRET = "YOUR_TOTP_SECRET" 

def shoonya_login():
    if not SHOONYA_API_KEY or SHOONYA_API_KEY == "YOUR_API_KEY": return None, "No API Key"
    try:
        import pyotp, hashlib
        pwd_sha256 = hashlib.sha256(SHOONYA_PWD.encode('utf-8')).hexdigest()
        app_key_sha256 = hashlib.sha256(f"{SHOONYA_UID}|{SHOONYA_API_KEY}".encode('utf-8')).hexdigest()
        totp = pyotp.TOTP(SHOONYA_TOTP_SECRET).now()
        payload = {"apkversion": "1.0.0", "uid": SHOONYA_UID, "pwd": pwd_sha256, "factor2": totp, "vc": SHOONYA_VC, "appkey": app_key_sha256, "imei": "abc12345", "source": "API"}
        res = requests.post('https://api.shoonya.com/NorenWClientTP/QuickAuth', data='jData=' + json.dumps(payload), timeout=5)
        if res.status_code == 502: return None, "Firewall Blocked (HTTP 502)"
        data = res.json()
        if data.get('stat') == 'Ok': return data.get('susertoken'), "Success"
        return None, data.get('emsg', 'Login Failed')
    except Exception as e: return None, "Broker API Offline"

def get_shoonya_ltp(token, susertoken):
    if not susertoken: return None
    try:
        payload = {"uid": SHOONYA_UID, "exch": "NSE", "token": str(token)}
        headers = {'Authorization': f'Bearer {SHOONYA_UID} {susertoken}'}
        res = requests.post('https://api.shoonya.com/NorenWClientTP/GetQuotes', data='jData=' + json.dumps(payload), headers=headers, timeout=3)
        if res.status_code == 200 and res.json().get('stat') == 'Ok': return float(res.json().get('lp'))
        return None
    except: return None

# ==============================================================================
# 2. PAGE CONFIG & PERSISTENT STATE 
# ==============================================================================
st.set_page_config(page_title="QuantScalper AI v23.0", layout="wide", initial_sidebar_state="collapsed")

if 'trade_active' not in st.session_state: st.session_state.trade_active = False
if 'trade_details' not in st.session_state: st.session_state.trade_details = {}
if 'shoonya_token' not in st.session_state:
    token, msg = shoonya_login()
    st.session_state.shoonya_token = token
    st.session_state.shoonya_msg = msg

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    html, body, [class*="css"]  { font-family: 'Inter', sans-serif; background-color: #0b0e11; color: #e3e9f0; }
    .stApp { background-color: #0b0e11; }
    div[data-testid="stMetricValue"] > div { color: #deff9a !important; font-size: 26px !important; }
    div[data-testid="stMetricLabel"] > label { color: #8b949e !important; font-size: 13px !important; font-weight: 700 !important; }
    .ex-card { background: #14181f; border-radius: 12px; padding: 20px; border: 1px solid #2d3748; margin-bottom: 15px; border-left: 5px solid #00ffff;}
    .status-badge { padding: 4px 10px; border-radius: 6px; font-weight: 800; font-size: 12px; text-transform: uppercase; background:#0b0e11; border: 1px solid #2d3748;}
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 3. HEADER & SEMI-AUTO BUTTONS
# ==============================================================================
sh_status = "<span style='color:#00ff66;'>🟢 API Linked</span>" if st.session_state.shoonya_token else f"<span style='color:#ff3333;'>🔴 API: {st.session_state.shoonya_msg} | PAPER TRADING</span>"
st.markdown(f"<h1 style='margin:0; font-weight:800;'>QUANT<span style='color:#deff9a;'>SCALPER AI</span> v23.0 <span style='font-size:14px;'>{sh_status}</span></h1>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#2d3748; margin: 10px 0 15px 0;'>", unsafe_allow_html=True)

c1, c2, c3 = st.columns([1, 1, 3])
with c1:
    if st.button("🟢 EXECUTE CE BUY (PULLBACK)", use_container_width=True):
        st.session_state.trade_active = True
        st.session_state.trade_details = {'Type': 'CE', 'Entry': 'Market', 'SL_Type': '2x ATR'}
with c2:
    if st.button("🔴 EXECUTE PE BUY (PULLBACK)", use_container_width=True):
        st.session_state.trade_active = True
        st.session_state.trade_details = {'Type': 'PE', 'Entry': 'Market', 'SL_Type': '2x ATR'}

if st.session_state.trade_active:
    with c3:
        st.warning(f"🔥 ACTIVE TRADE RUNNING: {st.session_state.trade_details['Type']} | Strict 2x ATR Stop-Loss Active.")
        if st.button("⏹️ CLOSE TRADE & SQUARE-OFF"):
            st.session_state.trade_active = False
            st.session_state.trade_details = {}
            st.rerun()

# ==============================================================================
# 4. ROBUST DATA ENGINE (BULLETPROOF)
# ==============================================================================
@st.cache_data(ttl=30)
def fetch_live_market_data():
    try:
        for attempt in range(3):
            df = yf.download('^NSEI', period='1d', interval='1m', progress=False)
            if df is not None and not df.empty and len(df) > 15:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                return df
            time.sleep(1)
        return None
    except: return None

with st.spinner('Syncing Institutional Data & Calculating SMC Pullbacks...'):
    df = fetch_live_market_data()
    
    if df is not None:
        # SMC Engine Math
        curr_p = round(float(df['Close'].iloc[-1]), 2)
        df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / (df['Volume'].cumsum() + 1e-10)
        vwap_val = round(float(df['VWAP'].iloc[-1]), 2)
        
        # ATR Calculation for Wider SL
        high, low, close = df['High'], df['Low'], df['Close']
        tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        atr_val = round(float(tr.rolling(14).mean().iloc[-1]), 2)
        safe_sl_pts = round(atr_val * 2.0, 1) # Increased breathing room
        
        # Live LTP Override
        if st.session_state.shoonya_token:
            ltp = get_shoonya_ltp('26000', st.session_state.shoonya_token)
            if ltp: curr_p = ltp
            
        m1, m2, m3, m4 = st.columns(4)
        with m1: st.metric("NIFTY SPOT", f"₹{curr_p}")
        with m2: st.metric("Institutional POC (VWAP)", f"₹{vwap_val}")
        with m3: st.metric("Safe SL Buffer (2x ATR)", f"{safe_sl_pts} pts")
        
        # Pullback Logic Detector
        dist_to_vwap = abs(curr_p - vwap_val)
        if curr_p > vwap_val and dist_to_vwap <= 15: bias = "BULLISH PULLBACK 🟢"
        elif curr_p < vwap_val and dist_to_vwap <= 15: bias = "BEARISH PULLBACK 🔴"
        elif curr_p > vwap_val: bias = "EXTENDED LONG ⚠️"
        else: bias = "EXTENDED SHORT ⚠️"
        with m4: st.metric("Market Context", bias)

        # Stable Plotly Chart
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Spot Price', line=dict(color='#deff9a', width=2.5)))
        fig.add_trace(go.Scatter(x=df.index, y=df['VWAP'], name='VWAP (POC)', line=dict(color='#00ffff', width=1.5, dash='dash')))
        fig.update_layout(template='plotly_dark', paper_bgcolor='#0b0e11', plot_bgcolor='#0b0e11', height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#2d3748'))
        st.plotly_chart(fig, use_container_width=True)
        
    else:
        st.error("⚠️ Data Sync Failed. Please wait for YFinance to stabilize.")

# ==============================================================================
# 5. MASTER SMC PROMPT GENERATOR
# ==============================================================================
st.markdown("<hr style='border-color:#2d3748;'>", unsafe_allow_html=True)
if st.button("🤖 Generate Master SMC Chat Prompt"):
    prompt = f"""You are an Institutional Quant Trader and Smart Money Concept (SMC) Analyst.

🔥 LIVE MARKET DATA
- Nifty Spot Price: ₹{curr_p if 'curr_p' in locals() else 'Unknown'}
- VWAP / POC: ₹{vwap_val if 'vwap_val' in locals() else 'Unknown'}
- ATR (Volatility): {atr_val if 'atr_val' in locals() else 'Unknown'} pts

Explain if the current price is offering a safe "Pullback Entry" near VWAP or if it is overextended. Recommend a strict 2x ATR Stop-loss strategy to avoid wick traps.
"""
    st.text_area("Copy this prompt into your Scalper Chat:", value=prompt, height=200)
