import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import datetime
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
# 2. SHOONYA LIVE LOGIN & ORDER EXECUTION ENGINE
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
        if res.status_code == 200 and res.json().get('stat') == 'Ok': return float(res.json().get('lp'))
        return None
    except: return None

# 🚀 THE ALGO ORDER FUNCTION
def place_shoonya_order(susertoken, trading_symbol, qty=25, buy_sell='B'):
    if not susertoken: return False, "API Not Connected"
    try:
        payload = {
            "uid": SHOONYA_UID, "actid": SHOONYA_UID, "exch": "NFO", 
            "tsym": trading_symbol, "qty": str(qty), "prc": "0", 
            "prd": "M", # 'M' = NRML/Margin (Use 'I' for MIS Intraday)
            "trantype": buy_sell, "prctyp": "MKT", "ret": "DAY"
        }
        headers = {'Authorization': f'Bearer {SHOONYA_UID} {susertoken}'}
        res = requests.post('https://api.shoonya.com/NorenWClientTP/PlaceOrder', data='jData=' + json.dumps(payload), headers=headers)
        data = res.json()
        if data.get('stat') == 'Ok': return True, data.get('norenordno')
        else: return False, data.get('emsg', 'Order Rejected')
    except Exception as e: return False, str(e)

# ==============================================================================
# 3. PAGE CONFIG & CRASH-PROOF STATE 
# ==============================================================================
st.set_page_config(page_title="QuantScalper AI v29.0 [ALGO]", layout="wide", initial_sidebar_state="collapsed")

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
# 4. ALGO CONTROL PANEL (HEADER)
# ==============================================================================
sh_status = "<span style='color:#00ff66;'>🟢 API Linked</span>" if st.session_state.shoonya_token else f"<span style='color:#ffaa00;'>🟠 API: {st.session_state.shoonya_msg}</span>"
st.markdown(f"<h1 style='margin:0; font-weight:800;'>QUANT<span style='color:#deff9a;'>SCALPER AI</span> v29.0 <span style='font-size:14px;'>{sh_status}</span></h1>", unsafe_allow_html=True)

st.markdown("""<div style='background:#1a1a1a; padding:10px; border-radius:8px; border:1px solid #ffaa00; margin-bottom:15px;'>
<b>⚙️ ALGO SETTINGS (REQUIRED):</b> Ensure Expiry format is exactly like Shoonya (e.g., 30MAY24).
</div>""", unsafe_allow_html=True)

c_opt1, c_opt2, c_opt3 = st.columns(3)
with c_opt1: expiry_date = st.text_input("Current Nifty Expiry", value="30MAY24")
with c_opt2: trade_qty = st.number_input("Quantity (1 Lot = 25)", min_value=25, step=25, value=25)
with c_opt3: live_mode = st.toggle("🔴 ENABLE LIVE TRADING (Real Money)", value=False)

st.markdown("<hr style='border-color:#2d3748; margin: 5px 0 15px 0;'>", unsafe_allow_html=True)

# ==============================================================================
# 5. DATA FETCH & SIGNAL GENERATION
# ==============================================================================
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

with st.spinner('Syncing HFT Algorithms...'):
    df = fetch_live_market_data()
    curr_p = 23750 # Fallback
    
    if df is not None:
        curr_p = round(float(df['Close'].iloc[-1]), 2)
        if st.session_state.shoonya_token:
            ltp = get_shoonya_ltp('26000', st.session_state.shoonya_token)
            if ltp: curr_p = ltp

        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
        macro_trend = round(float(df['EMA_200'].iloc[-1]), 2)
        
        last_trading_day = df.index[-1].date()
        day_data = df[df.index.date == last_trading_day].copy()
        if not day_data.empty and day_data['Volume'].sum() > 0:
            day_data['VWAP'] = (day_data['Close'] * day_data['Volume']).cumsum() / (day_data['Volume'].cumsum() + 1e-10)
            vwap_val = round(float(day_data['VWAP'].iloc[-1]), 2)
            df.loc[day_data.index, 'VWAP'] = day_data['VWAP']
        else: vwap_val = curr_p; df['VWAP'] = df['Close'].ewm(span=20, adjust=False).mean()

        tr = pd.concat([df['High'] - df['Low'], (df['High'] - df['Close'].shift(1)).abs(), (df['Low'] - df['Close'].shift(1)).abs()], axis=1).max(axis=1)
        atr_val = round(float(tr.rolling(14).mean().iloc[-1]), 2)
        safe_sl_pts = max(20.0, round(atr_val * 2.5, 1))
        
        m1, m2, m3, m4 = st.columns(4)
        with m1: st.metric("NIFTY SPOT", f"₹{curr_p}")
        with m2: st.metric("Micro POC (VWAP)", f"₹{vwap_val}")
        with m3: st.metric("Macro Trend (200 EMA)", f"₹{macro_trend}")
        with m4: st.metric("Dynamic SL Buffer", f"{safe_sl_pts} pts")
        
        # Automatic ATM Strike Calculation
        atm_strike = int(round(curr_p / 50) * 50)
        ce_symbol = f"NIFTY{expiry_date}C{atm_strike}"
        pe_symbol = f"NIFTY{expiry_date}P{atm_strike}"

        # ------------------------------------------------------------------------------
        # 6. AUTO-EXECUTION BUTTONS (THE ALGO TRIGGERS)
        # ------------------------------------------------------------------------------
        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1, 3])
        
        with c1:
            if st.button(f"🟢 BUY CE (Strike: {atm_strike})", use_container_width=True):
                if live_mode and st.session_state.shoonya_token:
                    success, msg = place_shoonya_order(st.session_state.shoonya_token, ce_symbol, trade_qty, 'B')
                    if success: 
                        st.success(f"LIVE ORDER PLACED! Order ID: {msg}")
                        st.session_state.trade_active = True
                        st.session_state.trade_details = {'Type': 'CE', 'Symbol': ce_symbol, 'Qty': trade_qty, 'Status': 'LIVE'}
                    else: st.error(f"Order Failed: {msg}")
                else:
                    st.toast("PAPER TRADE: Simulated CE Buy.")
                    st.session_state.trade_active = True
                    st.session_state.trade_details = {'Type': 'CE', 'Symbol': ce_symbol, 'Qty': trade_qty, 'Status': 'PAPER'}

        with c2:
            if st.button(f"🔴 BUY PE (Strike: {atm_strike})", use_container_width=True):
                if live_mode and st.session_state.shoonya_token:
                    success, msg = place_shoonya_order(st.session_state.shoonya_token, pe_symbol, trade_qty, 'B')
                    if success: 
                        st.success(f"LIVE ORDER PLACED! Order ID: {msg}")
                        st.session_state.trade_active = True
                        st.session_state.trade_details = {'Type': 'PE', 'Symbol': pe_symbol, 'Qty': trade_qty, 'Status': 'LIVE'}
                    else: st.error(f"Order Failed: {msg}")
                else:
                    st.toast("PAPER TRADE: Simulated PE Buy.")
                    st.session_state.trade_active = True
                    st.session_state.trade_details = {'Type': 'PE', 'Symbol': pe_symbol, 'Qty': trade_qty, 'Status': 'PAPER'}

        if st.session_state.trade_active:
            with c3:
                trade = st.session_state.trade_details
                status_color = "#00ff66" if trade['Status'] == 'LIVE' else "#ffaa00"
                st.markdown(f"<div style='border:1px solid {status_color}; padding:10px; border-radius:8px;'><b>🔥 ACTIVE {trade['Status']} TRADE:</b> {trade['Symbol']} | Qty: {trade['Qty']}</div>", unsafe_allow_html=True)
                
                if st.button("⏹️ SQUARE-OFF POSITION"):
                    if trade['Status'] == 'LIVE' and st.session_state.shoonya_token:
                        success, msg = place_shoonya_order(st.session_state.shoonya_token, trade['Symbol'], trade['Qty'], 'S')
                        if success: st.success("Position Closed Successfully!")
                        else: st.error(f"Square-off Failed: {msg} (Close manually on Broker App!)")
                    st.session_state.trade_active = False
                    st.session_state.trade_details = {}
                    st.rerun()

        # Plotly Chart
        plot_df = df.tail(180) 
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Close'], name='Spot Price', line=dict(color='#deff9a', width=2.5)))
        if 'VWAP' in plot_df.columns: fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['VWAP'], name='VWAP (Micro)', line=dict(color='#00ffff', width=2, dash='dash')))
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['EMA_200'], name='200 EMA (Macro)', line=dict(color='#ffaa00', width=2)))
        fig.update_layout(template='plotly_dark', paper_bgcolor='#0b0e11', plot_bgcolor='#0b0e11', height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#2d3748'))
        st.plotly_chart(fig, use_container_width=True)
        
    else:
        st.error("⚠️ Data Sync Failed.")

st.markdown("<hr style='border-color:#2d3748;'>", unsafe_allow_html=True)
st.markdown("### 📸 AI Chart Analyzer (Paste Screenshot Here)")
uploaded_image = st.file_uploader("Click here and press Ctrl+V to paste your chart image", type=['png', 'jpg', 'jpeg'])
if uploaded_image is not None:
    st.image(Image.open(uploaded_image), use_container_width=True)
    st.info("Screenshot Accepted. Copy the prompt from v28.0 and send it to Gemini for analysis!")
