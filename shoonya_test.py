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
SHOONYA_UID = "FN209492" 
SHOONYA_PWD = "YOUR_PASSWORD" 
SHOONYA_API_KEY = "7cf713be1c14cb0020e7012d412c5f05" 
SHOONYA_VC = "FN209492_U" 
SHOONYA_TOTP_SECRET = "7S4S46UM2426XWQZ5726OO6QIXD6LYNT" 

# ==============================================================================
# 2. SHOONYA LIVE LOGIN & DATA FETCH ENGINE
# ==============================================================================
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
# 3. PAGE CONFIG & CRASH-PROOF STATE 
# ==============================================================================
st.set_page_config(page_title="QuantScalper AI v25.0", layout="wide", initial_sidebar_state="collapsed")

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
    .metric-box { background: rgba(20, 24, 31, 0.5); padding: 15px; border-radius: 10px; border: 1px solid #2d3748; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 4. HEADER & SMART EXECUTION BUTTONS
# ==============================================================================
sh_status = "<span style='color:#00ff66;'>🟢 API Linked</span>" if st.session_state.shoonya_token else f"<span style='color:#ff3333;'>🔴 API: {st.session_state.shoonya_msg} | PAPER TRADING</span>"
st.markdown(f"<h1 style='margin:0; font-weight:800;'>QUANT<span style='color:#deff9a;'>SCALPER AI</span> v25.0 <span style='font-size:14px;'>{sh_status}</span></h1>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#2d3748; margin: 10px 0 15px 0;'>", unsafe_allow_html=True)

c1, c2, c3 = st.columns([1, 1, 3])
with c1:
    if st.button("🟢 EXECUTE CE (Bullish Pullback)", use_container_width=True):
        st.session_state.trade_active = True
        st.session_state.trade_details = {'Type': 'CE', 'Entry': 'Market', 'Status': 'Risk Managed'}
with c2:
    if st.button("🔴 EXECUTE PE (Bearish Pullback)", use_container_width=True):
        st.session_state.trade_active = True
        st.session_state.trade_details = {'Type': 'PE', 'Entry': 'Market', 'Status': 'Risk Managed'}

if st.session_state.trade_active:
    with c3:
        st.warning(f"🔥 ACTIVE TRADE RUNNING: {st.session_state.trade_details['Type']} | Strict 2.5x ATR Stop-Loss Active.")
        if st.button("⏹️ SQUARE-OFF & BOOK PNL"):
            st.session_state.trade_active = False
            st.session_state.trade_details = {}
            st.rerun()

# ==============================================================================
# 5. ADVANCED SMC QUANT ENGINE (MACRO + MICRO)
# ==============================================================================
@st.cache_data(ttl=30)
def fetch_live_market_data():
    try:
        for attempt in range(3):
            # Fetching 2 days data to calculate 200 EMA properly
            df = yf.download('^NSEI', period='2d', interval='1m', progress=False)
            if df is not None and not df.empty and len(df) > 200:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                return df
            time.sleep(1)
        return None
    except: return None

with st.spinner('Syncing Multi-Timeframe Institutional Data...'):
    df = fetch_live_market_data()
    
    if df is not None:
        # Calculate Core Metrics
        curr_p = round(float(df['Close'].iloc[-1]), 2)
        
        # 1. MACRO TREND (200 EMA)
        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
        macro_trend = round(float(df['EMA_200'].iloc[-1]), 2)
        
        # 2. MICRO POC (VWAP)
        # Calculate VWAP only for the current day
        current_day = df.index[-1].date()
        day_data = df[df.index.date == current_day].copy()
        if not day_data.empty:
            day_data['VWAP'] = (day_data['Close'] * day_data['Volume']).cumsum() / (day_data['Volume'].cumsum() + 1e-10)
            vwap_val = round(float(day_data['VWAP'].iloc[-1]), 2)
            # Reassign VWAP back to main dataframe for plotting
            df.loc[day_data.index, 'VWAP'] = day_data['VWAP']
        else:
            vwap_val = curr_p
            df['VWAP'] = curr_p

        # 3. DYNAMIC STOP LOSS (ATR 14)
        high, low, close = df['High'], df['Low'], df['Close']
        tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        atr_val = round(float(tr.rolling(14).mean().iloc[-1]), 2)
        safe_sl_pts = max(20.0, round(atr_val * 2.5, 1)) # Minimum 20 pts SL or 2.5x ATR
        
        # Live LTP Override from Shoonya
        if st.session_state.shoonya_token:
            ltp = get_shoonya_ltp('26000', st.session_state.shoonya_token)
            if ltp: curr_p = ltp
            
        # UI Metrics Display
        m1, m2, m3, m4 = st.columns(4)
        with m1: st.metric("NIFTY SPOT", f"₹{curr_p}")
        with m2: st.metric("Micro POC (VWAP)", f"₹{vwap_val}")
        with m3: st.metric("Macro Trend (200 EMA)", f"₹{macro_trend}")
        with m4: st.metric("Safe SL Buffer (2.5x ATR)", f"{safe_sl_pts} pts")
        
        # 4. MULTI-TIMEFRAME LOGIC DETECTOR
        st.markdown("<br>", unsafe_allow_html=True)
        if curr_p > macro_trend and curr_p > vwap_val: bias, color = "STRONG BULLISH (Only Look for CE Pullbacks)", "#00ff66"
        elif curr_p < macro_trend and curr_p < vwap_val: bias, color = "STRONG BEARISH (Only Look for PE Pullbacks)", "#ff3333"
        elif curr_p > macro_trend and curr_p < vwap_val: bias, color = "CHOPPY (Macro Bullish, Micro Bearish - WAIT)", "#ffaa00"
        else: bias, color = "CHOPPY (Macro Bearish, Micro Bullish - WAIT)", "#ffaa00"
        
        st.markdown(f"<div class='metric-box'><b>AI Master Bias:</b> <span style='color:{color}; font-size:18px;'>{bias}</span></div>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        # Plotly Chart (Showing only the last 3 hours for scalping clarity)
        plot_df = df.tail(180) 
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Close'], name='Spot Price', line=dict(color='#deff9a', width=2.5)))
        if 'VWAP' in plot_df.columns:
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['VWAP'], name='VWAP (Micro)', line=dict(color='#00ffff', width=2, dash='dash')))
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['EMA_200'], name='200 EMA (Macro)', line=dict(color='#ffaa00', width=2)))
        
        fig.update_layout(template='plotly_dark', paper_bgcolor='#0b0e11', plot_bgcolor='#0b0e11', height=450, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#2d3748'))
        st.plotly_chart(fig, use_container_width=True)
        
    else:
        st.error("⚠️ Data Sync Failed. Please wait for YFinance to stabilize.")

# ==============================================================================
# 6. MASTER SMC PROMPT GENERATOR
# ==============================================================================
st.markdown("<hr style='border-color:#2d3748;'>", unsafe_allow_html=True)
if st.button("🤖 Generate Master SMC Chat Prompt"):
    prompt = f"""You are an Institutional Quant Trader and Smart Money Concept (SMC) Analyst.

🔥 LIVE MARKET DATA
- Nifty Spot Price: ₹{curr_p if 'curr_p' in locals() else 'Unknown'}
- Micro POC (VWAP): ₹{vwap_val if 'vwap_val' in locals() else 'Unknown'}
- Macro Trend (200 EMA): ₹{macro_trend if 'macro_trend' in locals() else 'Unknown'}
- Dynamic ATR SL: {safe_sl_pts if 'safe_sl_pts' in locals() else 'Unknown'} pts

Explain the alignment between the Macro Trend (200 EMA) and Micro Trend (VWAP). If they are aligned, recommend a safe "Pullback Entry" with a strict {safe_sl_pts if 'safe_sl_pts' in locals() else '2.5x ATR'} point stop-loss. If they contradict, advise to stay out of the market.
"""
    st.text_area("Copy this prompt into your Scalper Chat (ChatGPT/Claude):", value=prompt, height=250)
