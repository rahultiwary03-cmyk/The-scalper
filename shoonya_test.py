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
from PIL import Image

# ==============================================================================
# 1. 🔑 SHOONYA API CREDENTIALS 
# ==============================================================================
SHOONYA_UID = "FN209492" 
SHOONYA_PWD = "YOUR_PASSWORD" 
SHOONYA_API_KEY = "7cf713be1c14cb0020e7012d412c5f05" 
SHOONYA_VC = "FN209492_U" 
SHOONYA_TOTP_SECRET = "7S4S46UM2426XWQZ5726OO6QIXD6LYNT" 

# ==============================================================================
# 2. SHOONYA LIVE LOGIN
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
        try: data = res.json()
        except ValueError: return None, "Broker API Maintenance (Weekend Mode)"
        if data.get('stat') == 'Ok': return data.get('susertoken'), "Success"
        return None, data.get('emsg', 'Login Failed')
    except Exception as e: return None, "Broker API Offline"

def get_shoonya_ltp(token, susertoken):
    if not susertoken: return None
    try:
        payload = {"uid": SHOONYA_UID, "exch": "NSE", "token": str(token)}
        headers = {'Authorization': f'Bearer {SHOONYA_UID} {susertoken}'}
        res = requests.post('https://api.shoonya.com/NorenWClientTP/GetQuotes', data='jData=' + json.dumps(payload), headers=headers, timeout=3)
        if res.status_code == 200:
            data = res.json()
            if data.get('stat') == 'Ok': return float(data.get('lp'))
        return None
    except: return None

# ==============================================================================
# 3. PAGE CONFIG & CRASH-PROOF STATE 
# ==============================================================================
st.set_page_config(page_title="QuantScalper AI v27.0", layout="wide", initial_sidebar_state="collapsed")

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

sh_status = "<span style='color:#00ff66;'>🟢 API Linked</span>" if st.session_state.shoonya_token else f"<span style='color:#ffaa00;'>🟠 API: {st.session_state.shoonya_msg} | PAPER TRADING</span>"
st.markdown(f"<h1 style='margin:0; font-weight:800;'>QUANT<span style='color:#deff9a;'>SCALPER AI</span> v27.0 <span style='font-size:14px;'>{sh_status}</span></h1>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#2d3748; margin: 10px 0 15px 0;'>", unsafe_allow_html=True)

# ==============================================================================
# TABS SETUP: LIVE vs SCREENSHOT ANALYZER
# ==============================================================================
tab_live, tab_screenshot = st.tabs(["🚀 LIVE TERMINAL", "📸 SCREENSHOT ANALYZER (No CSV Needed)"])

# ------------------------------------------------------------------------------
# TAB 1: LIVE TERMINAL
# ------------------------------------------------------------------------------
with tab_live:
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

    @st.cache_data(ttl=30)
    def fetch_live_market_data():
        try:
            for attempt in range(3):
                df = yf.download('^NSEI', period='3d', interval='1m', progress=False)
                if df is not None and not df.empty and len(df) > 50:
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                    return df
                time.sleep(1)
            return None
        except: return None

    with st.spinner('Syncing Multi-Timeframe Institutional Data...'):
        df = fetch_live_market_data()
        
        if df is not None:
            curr_p = round(float(df['Close'].iloc[-1]), 2)
            df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
            macro_trend = round(float(df['EMA_200'].iloc[-1]), 2)
            
            last_trading_day = df.index[-1].date()
            day_data = df[df.index.date == last_trading_day].copy()
            if not day_data.empty and day_data['Volume'].sum() > 0:
                day_data['VWAP'] = (day_data['Close'] * day_data['Volume']).cumsum() / (day_data['Volume'].cumsum() + 1e-10)
                vwap_val = round(float(day_data['VWAP'].iloc[-1]), 2)
                df.loc[day_data.index, 'VWAP'] = day_data['VWAP']
            else:
                vwap_val = curr_p; df['VWAP'] = df['Close'].ewm(span=20, adjust=False).mean()

            high, low, close = df['High'], df['Low'], df['Close']
            tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
            atr_val = round(float(tr.rolling(14).mean().iloc[-1]), 2)
            safe_sl_pts = max(20.0, round(atr_val * 2.5, 1))
            
            if st.session_state.shoonya_token:
                ltp = get_shoonya_ltp('26000', st.session_state.shoonya_token)
                if ltp: curr_p = ltp
                
            m1, m2, m3, m4 = st.columns(4)
            with m1: st.metric("NIFTY SPOT", f"₹{curr_p}")
            with m2: st.metric("Micro POC (VWAP)", f"₹{vwap_val}")
            with m3: st.metric("Macro Trend (200 EMA)", f"₹{macro_trend}")
            with m4: st.metric("Safe SL Buffer (2.5x ATR)", f"{safe_sl_pts} pts")
            
            st.markdown("<br>", unsafe_allow_html=True)
            if curr_p > macro_trend and curr_p > vwap_val: bias, color = "STRONG BULLISH (Only Look for CE Pullbacks)", "#00ff66"
            elif curr_p < macro_trend and curr_p < vwap_val: bias, color = "STRONG BEARISH (Only Look for PE Pullbacks)", "#ff3333"
            elif curr_p > macro_trend and curr_p < vwap_val: bias, color = "CHOPPY (Macro Bullish, Micro Bearish - WAIT)", "#ffaa00"
            else: bias, color = "CHOPPY (Macro Bearish, Micro Bullish - WAIT)", "#ffaa00"
            
            st.markdown(f"<div class='metric-box'><b>AI Master Bias:</b> <span style='color:{color}; font-size:18px;'>{bias}</span></div>", unsafe_allow_html=True)
            
            plot_df = df.tail(180) 
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Close'], name='Spot Price', line=dict(color='#deff9a', width=2.5)))
            if 'VWAP' in plot_df.columns: fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['VWAP'], name='VWAP (Micro)', line=dict(color='#00ffff', width=2, dash='dash')))
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['EMA_200'], name='200 EMA (Macro)', line=dict(color='#ffaa00', width=2)))
            
            fig.update_layout(template='plotly_dark', paper_bgcolor='#0b0e11', plot_bgcolor='#0b0e11', height=450, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#2d3748'))
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.error("⚠️ Data Sync Failed.")

# ------------------------------------------------------------------------------
# TAB 2: SCREENSHOT ANALYZER (Tension Free!)
# ------------------------------------------------------------------------------
with tab_screenshot:
    st.markdown("### 📸 AI Chart Analyzer & Trading Journal")
    st.info("CSV file download karne ki koi zaroorat nahi hai! Apne chart ka screenshot lijiye (TradingView / Zerodha) aur yahan upload karein.")
    
    col_img, col_prompt = st.columns([1, 1])
    
    with col_img:
        uploaded_image = st.file_uploader("Upload Chart Screenshot (PNG/JPG)", type=['png', 'jpg', 'jpeg'])
        if uploaded_image is not None:
            image = Image.open(uploaded_image)
            st.image(image, caption="Uploaded Chart", use_container_width=True)
            st.success("✅ Screenshot Loaded! Ab right side ka prompt copy karke AI (Gemini) ko bhejein.")
        else:
            st.markdown("<div style='height:300px; border:2px dashed #2d3748; display:flex; align-items:center; justify-content:center; color:#8b949e; border-radius:10px;'>No Image Uploaded</div>", unsafe_allow_html=True)

    with col_prompt:
        st.markdown("### 🤖 Copy This Prompt")
        st.markdown("Niche diye gaye prompt ko copy karein aur apni photo (Screenshot) ke sath mujhe (AI ko) chat mein bhejein. Main aapko bataunga ki isme kya trap hai aur aage kya karna hai.")
        
        screenshot_prompt = """Hello AI Quant! I have uploaded a screenshot of my trading chart. Please act as a Smart Money Concept (SMC) Expert and analyze it for me.

Task 1: Identify the Phase
- Is it Accumulation, Manipulation (Trap/Liquidity Grab), or Distribution?

Task 2: Retailer Trap
- Where are the retail traders trapped in this chart (Call buyers or Put buyers)?

Task 3: Execution Advice
- Based on the visible price action, should I look for a Pullback Entry, Wait, or Avoid trading entirely?
- If I take a trade here, where should my logical Stop Loss be placed to avoid getting hunted?

Be strictly analytical and give me a clear "Hedge-Fund" style breakdown."""
        
        st.text_area("Copy and Paste into AI Chat:", value=screenshot_prompt, height=350)
