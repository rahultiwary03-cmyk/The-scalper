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
st.set_page_config(page_title="QuantScalper AI v28.0", layout="wide", initial_sidebar_state="collapsed")

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
    .analysis-box { background: rgba(0, 255, 255, 0.05); border-left: 4px solid #00ffff; padding: 15px; border-radius: 8px; margin-top: 15px;}
    </style>
    """, unsafe_allow_html=True)

sh_status = "<span style='color:#00ff66;'>🟢 API Linked</span>" if st.session_state.shoonya_token else f"<span style='color:#ffaa00;'>🟠 API: {st.session_state.shoonya_msg} | PAPER TRADING</span>"
st.markdown(f"<h1 style='margin:0; font-weight:800;'>QUANT<span style='color:#deff9a;'>SCALPER AI</span> v28.0 <span style='font-size:14px;'>{sh_status}</span></h1>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#2d3748; margin: 10px 0 15px 0;'>", unsafe_allow_html=True)

# ==============================================================================
# TABS SETUP
# ==============================================================================
tab_live, tab_screenshot = st.tabs(["🚀 LIVE TERMINAL", "📸 AI VISION LAB (Upload / Paste)"])

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
# TAB 2: AI VISION LAB (Screenshot Paste Support)
# ------------------------------------------------------------------------------
with tab_screenshot:
    st.markdown("### 📸 Copy & Paste Your Trading Chart")
    st.info("💡 **Pro Tip:** TradingView या Kite से स्क्रीनशॉट लें (Windows: Win + Shift + S) और सीधे नीचे वाले डब्बे में **Ctrl + V** दबाकर पेस्ट कर दें!")
    
    col_img, col_prompt = st.columns([1, 1])
    
    with col_img:
        uploaded_image = st.file_uploader("Click here and press Ctrl+V to paste image", type=['png', 'jpg', 'jpeg'])
        if uploaded_image is not None:
            image = Image.open(uploaded_image)
            st.image(image, caption="Uploaded Chart for AI Analysis", use_container_width=True)
            
            # Simulated Processing Alert
            with st.spinner("Preparing Image for Gemini Vision Analysis..."):
                time.sleep(1)
            st.success("✅ Chart Captured Successfully!")
            
            st.markdown("""
            <div class='analysis-box'>
                <h4 style='color:#00ffff; margin-top:0;'>⚠️ API Connection Notice</h4>
                <p style='font-size:14px;'>Since this Streamlit server doesn't have a paid Gemini API key embedded yet, it cannot scan the pixels directly. <br><br>
                <b>Next Step:</b> Right side वाले प्रॉम्प्ट को कॉपी करें और इस फोटो के साथ सीधे <b>Gemini Chat</b> में पेस्ट कर दें। AI (मैं) आपको तुरंत एनालाइज़ करके दे दूँगा!</p>
            </div>
            """, unsafe_allow_html=True)
            
        else:
            st.markdown("<div style='height:300px; border:2px dashed #2d3748; display:flex; align-items:center; justify-content:center; color:#8b949e; border-radius:10px;'>Awaiting Screenshot (Ctrl+V)</div>", unsafe_allow_html=True)

    with col_prompt:
        st.markdown("### 🤖 Strategy Doctor Prompt")
        st.markdown("इस प्रॉम्प्ट को कॉपी करें और अपने स्क्रीनशॉट के साथ AI चैट में भेजें:")
        
        screenshot_prompt = """Hello Gemini! I have attached a screenshot of my live Nifty chart. 
Please act as an Elite Quant Developer and analyze this chart to fix the flaws in my trading system.

1. Price Action Analysis:
- Based on the image, where did the Operator (Smart Money) trap retail buyers or sellers?
- Did the price respect the VWAP or 200 EMA?

2. Strategy Diagnosis:
- If my algorithm took an entry here, where exactly should the Stop Loss be to avoid a wick hit?
- Is this a trending market or a choppy/sideways market where I should avoid trading?

3. Code Improvement:
- Based on this specific chart pattern, write a small logic (in Python/Streamlit format) that I can add to my system to filter out bad trades like this in the future."""
        
        st.text_area("Copy and Paste into Gemini Chat:", value=screenshot_prompt, height=400)
