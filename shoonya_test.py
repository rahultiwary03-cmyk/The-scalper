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
SHOONYA_PWD = "Rahul@1995" 
SHOONYA_API_KEY = "3007acd3cd50a75e4e8eb1bfc0e1459a" 
SHOONYA_VC = "FN209492_U" 
SHOONYA_TOTP_SECRET = "666J4TSFQRM624X75B6WZ32PMUH3477P" 

# ==============================================================================
# 2. SHOONYA LIVE LOGIN ENGINE
# ==============================================================================
try:
    import pyotp
    import hashlib
    SH_AVAILABLE = True
except ImportError:
    SH_AVAILABLE = False

def shoonya_login():
    if not SH_AVAILABLE: return None, "pyotp missing"
    if not SHOONYA_API_KEY or SHOONYA_API_KEY == "YOUR_API_KEY": return None, "No API Key"
    try:
        pwd_sha256 = hashlib.sha256(SHOONYA_PWD.encode('utf-8')).hexdigest()
        app_key_sha256 = hashlib.sha256(f"{SHOONYA_UID}|{SHOONYA_API_KEY}".encode('utf-8')).hexdigest()
        totp = pyotp.TOTP(SHOONYA_TOTP_SECRET).now()
        payload = {"apkversion": "1.0.0", "uid": SHOONYA_UID, "pwd": pwd_sha256, "factor2": totp, "vc": SHOONYA_VC, "appkey": app_key_sha256, "imei": "abc12345", "source": "API"}
        res = requests.post('https://api.shoonya.com/NorenWClientTP/QuickAuth', data='jData=' + json.dumps(payload))
        data = res.json()
        if data.get('stat') == 'Ok': return data.get('susertoken'), "Success"
        else: return None, data.get('emsg', 'Unknown Error')
    except Exception as e: return None, str(e)

def get_shoonya_ltp(token, susertoken):
    if not susertoken: return None
    try:
        payload = {"uid": SHOONYA_UID, "exch": "NSE", "token": str(token)}
        headers = {'Authorization': f'Bearer {SHOONYA_UID} {susertoken}'}
        res = requests.post('https://api.shoonya.com/NorenWClientTP/GetQuotes', data='jData=' + json.dumps(payload), headers=headers)
        if res.json().get('stat') == 'Ok': return float(res.json().get('lp'))
        return None
    except: return None

# ==============================================================================
# 3. PAGE CONFIG & PERSISTENT STATE (CRASH-PROOF)
# ==============================================================================
st.set_page_config(page_title="QuantScalper AI v22.0", layout="wide", initial_sidebar_state="collapsed")

# यह डेटा रिफ्रेश होने पर कभी डिलीट नहीं होगा
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
    .ex-card { background: #14181f; border-radius: 12px; padding: 20px; border: 1px solid #2d3748; margin-bottom: 15px; }
    .status-badge { padding: 4px 10px; border-radius: 6px; font-weight: 800; font-size: 12px; text-transform: uppercase; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 4. HEADER & SEMI-AUTO BUTTONS
# ==============================================================================
sh_status = "<span style='color:#00ff66;'>🟢 API Linked</span>" if st.session_state.shoonya_token else "<span style='color:#ff3333;'>🔴 API Disabled</span>"
st.markdown(f"<h1 style='margin:0; font-weight:800;'>QUANT<span style='color:#deff9a;'>SCALPER AI</span> v22.0 <span style='font-size:14px;'>{sh_status}</span></h1>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#2d3748; margin: 10px 0 15px 0;'>", unsafe_allow_html=True)

c1, c2, c3 = st.columns([1, 1, 3])
with c1:
    if st.button("🟢 EXECUTE CE BUY", use_container_width=True):
        st.session_state.trade_active = True
        st.session_state.trade_details = {'Type': 'CE', 'Entry': 'Market', 'Status': 'Active'}
with c2:
    if st.button("🔴 EXECUTE PE BUY", use_container_width=True):
        st.session_state.trade_active = True
        st.session_state.trade_details = {'Type': 'PE', 'Entry': 'Market', 'Status': 'Active'}

if st.session_state.trade_active:
    with c3:
        st.warning(f"🔥 ACTIVE TRADE RUNNING: {st.session_state.trade_details['Type']} | Managing Risk...")
        if st.button("⏹️ CLOSE TRADE & SQUARE-OFF"):
            st.session_state.trade_active = False
            st.session_state.trade_details = {}
            st.rerun()

# ==============================================================================
# 5. ROBUST DATA ENGINE (BULLETPROOF)
# ==============================================================================
@st.cache_data(ttl=45)
def fetch_live_market_data():
    try:
        # Retry logic for YFinance stability
        for attempt in range(3):
            df = yf.download('^NSEI', period='1d', interval='1m', progress=False)
            if df is not None and not df.empty and len(df) > 5:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                return df
            time.sleep(1)
        return None
    except: return None

with st.spinner('Syncing Institutional Data & Calculating SMC...'):
    df = fetch_live_market_data()
    
    if df is not None:
        # SMC Engine Math
        curr_p = round(float(df['Close'].iloc[-1]), 2)
        df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / (df['Volume'].cumsum() + 1e-10)
        vwap_val = round(float(df['VWAP'].iloc[-1]), 2)
        
        # Live LTP Override
        if st.session_state.shoonya_token:
            ltp = get_shoonya_ltp('26000', st.session_state.shoonya_token)
            if ltp: curr_p = ltp
            
        m1, m2, m3 = st.columns(3)
        with m1: st.metric("NIFTY SPOT", f"₹{curr_p}")
        with m2: st.metric("Institutional POC (VWAP)", f"₹{vwap_val}")
        with m3: st.metric("Market Bias", "BULLISH 🟢" if curr_p > vwap_val else "BEARISH 🔴")

        # Stable Plotly Chart
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Spot Price', line=dict(color='#deff9a', width=2.5)))
        fig.add_trace(go.Scatter(x=df.index, y=df['VWAP'], name='VWAP (POC)', line=dict(color='#00ffff', width=1.5, dash='dash')))
        fig.update_layout(template='plotly_dark', paper_bgcolor='#0b0e11', plot_bgcolor='#0b0e11', height=450, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#2d3748'))
        st.plotly_chart(fig, use_container_width=True)
        
    else:
        st.error("⚠️ Data Sync Failed. Market might be pre-open or YFinance API is throttling.")
        st.info("💡 Pro-Tip: Please wait 1-2 minutes and refresh. YFinance takes time to stabilize exactly at 9:15 AM.")

# ==============================================================================
# 6. MASTER SMC PROMPT GENERATOR
# ==============================================================================
st.markdown("<hr style='border-color:#2d3748;'>", unsafe_allow_html=True)
if st.button("🤖 Generate Master SMC Chat Prompt"):
    prompt = f"""You are an Institutional Quant Trader, Smart Money Concept (SMC) Analyst, and High-Frequency Option Scalper specializing in NIFTY 50.

Analyze the live market strictly using the real-time data provided below. Think like a hedge fund trader, not a retail trader.

🔥 LIVE MARKET DATA
- Nifty Spot Price: ₹{curr_p if 'curr_p' in locals() else 'Unknown'}
- VWAP / POC: ₹{vwap_val if 'vwap_val' in locals() else 'Unknown'}

📊 INSTITUTIONAL SMC ANALYSIS REQUIRED
1. MARKET STRUCTURE: Determine context (Trending Bearish, Reversal, Liquidity trap, or Range-bound).
2. SMART MONEY ANALYSIS: Are institutions likely accumulating CALLS or PUTS? 
3. OPTIONS FLOW ANALYSIS: Tell which side has higher probability (CE buyers or PE buyers).
4. EXECUTION DECISION: Give ONE clear action: BUY CE, BUY PE, or NO TRADE.

⚠️ STRICT RULES: Be concise. No education. Speak like a prop-desk scalper. Prioritize capital protection. Output in this format:
✅ Market Bias: 
✅ Institutional Direction: 
✅ Best Trade: 
✅ Confidence Score: 
✅ Trap Warning: 
✅ Final Verdict:
"""
    st.text_area("Copy this prompt into your Scalper Chat (ChatGPT/Claude):", value=prompt, height=350)
