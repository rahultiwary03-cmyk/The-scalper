import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import datetime
import requests
import json

# ==============================================================================
# 1. 🔑 SHOONYA API CREDENTIALS 
# ==============================================================================
SHOONYA_UID = "FN209492" 
SHOONYA_PWD = "YOUR_PASSWORD" 
SHOONYA_API_KEY = "7cf713be1c14cb0020e7012d412c5f05" 
SHOONYA_VC = "FN209492_U" 
SHOONYA_TOTP_SECRET = "7S4S46UM2426XWQZ5726OO6QIXD6LYNT" 

# ==============================================================================
# 2. SHOONYA LIVE LOGIN & ORDER EXECUTION
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

def place_shoonya_order(susertoken, trading_symbol, qty=25, buy_sell='B'):
    if not susertoken: return False, "API Not Connected"
    try:
        payload = {
            "uid": SHOONYA_UID, "actid": SHOONYA_UID, "exch": "NFO", 
            "tsym": trading_symbol, "qty": str(qty), "prc": "0", 
            "prd": "M", 
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
st.set_page_config(page_title="QuantScalper AI v31.0", layout="wide", initial_sidebar_state="collapsed")

# 🚀 NEW: Trade History Logger added to Session State
if 'trade_history' not in st.session_state: st.session_state.trade_history = []
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
    .live-pnl-box { background: #14181f; border-left: 5px solid #00ffff; padding: 15px; border-radius: 8px; margin-top: 10px; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 4. ALGO CONTROL PANEL
# ==============================================================================
sh_status = "<span style='color:#00ff66;'>🟢 API Linked</span>" if st.session_state.shoonya_token else f"<span style='color:#ffaa00;'>🟠 PAPER TRADING MODE</span>"

# Calculate Total PnL for the Day
total_trades_today = len(st.session_state.trade_history)
net_pnl_today = sum([trade['PnL (Points)'] for trade in st.session_state.trade_history]) if total_trades_today > 0 else 0
pnl_color = "#00ff66" if net_pnl_today >= 0 else "#ff3333"

col_h1, col_h2 = st.columns([2, 1])
with col_h1: st.markdown(f"<h1 style='margin:0; font-weight:800;'>QUANT<span style='color:#deff9a;'>SCALPER AI</span> v31.0 <span style='font-size:14px;'>{sh_status}</span></h1>", unsafe_allow_html=True)
with col_h2: st.markdown(f"<div style='text-align:right; font-size:18px; font-weight:bold;'>Total Trades: {total_trades_today} | Day PnL: <span style='color:{pnl_color};'>{net_pnl_today} pts</span></div>", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#2d3748; margin: 5px 0 15px 0;'>", unsafe_allow_html=True)

c_opt1, c_opt2, c_opt3 = st.columns(3)
with c_opt1: expiry_date = st.text_input("Current Nifty Expiry", value="30MAY24")
with c_opt2: trade_qty = st.number_input("Quantity (1 Lot = 25)", min_value=25, step=25, value=25)
with c_opt3: live_mode = st.toggle("🔴 ENABLE LIVE TRADING (Real Money)", value=False)

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
    curr_p = 23750 
    
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
        
        atm_strike = int(round(curr_p / 50) * 50)
        ce_symbol = f"NIFTY{expiry_date}C{atm_strike}"
        pe_symbol = f"NIFTY{expiry_date}P{atm_strike}"

        st.markdown("<br>", unsafe_allow_html=True)
        if curr_p > macro_trend and curr_p > vwap_val: bias, color = "STRONG BULLISH (Trend Aligned)", "#00ff66"
        elif curr_p < macro_trend and curr_p < vwap_val: bias, color = "STRONG BEARISH (Trend Aligned)", "#ff3333"
        else: bias, color = "CHOPPY (Macro & Micro Contradiction - WAIT)", "#ffaa00"
        
        st.markdown(f"<div class='metric-box'><b>AI Master Bias:</b> <span style='color:{color}; font-size:18px;'>{bias}</span></div><br>", unsafe_allow_html=True)

        # ------------------------------------------------------------------------------
        # 6. AUTO-EXECUTION BUTTONS & LIVE PNL MONITORING
        # ------------------------------------------------------------------------------
        c1, c2, c3 = st.columns([1, 1, 3])
        
        with c1:
            if st.button(f"🟢 BUY CE (Strike: {atm_strike})", use_container_width=True) and not st.session_state.trade_active:
                current_time = datetime.datetime.now().strftime("%H:%M:%S")
                if live_mode and st.session_state.shoonya_token:
                    success, msg = place_shoonya_order(st.session_state.shoonya_token, ce_symbol, trade_qty, 'B')
                    if success: 
                        st.session_state.trade_active = True
                        st.session_state.trade_details = {'Type': 'CE', 'Symbol': ce_symbol, 'Qty': trade_qty, 'Status': 'LIVE', 'Entry_Price': curr_p, 'Time': current_time}
                else:
                    st.session_state.trade_active = True
                    st.session_state.trade_details = {'Type': 'CE', 'Symbol': ce_symbol, 'Qty': trade_qty, 'Status': 'PAPER', 'Entry_Price': curr_p, 'Time': current_time}
                st.rerun()

        with c2:
            if st.button(f"🔴 BUY PE (Strike: {atm_strike})", use_container_width=True) and not st.session_state.trade_active:
                current_time = datetime.datetime.now().strftime("%H:%M:%S")
                if live_mode and st.session_state.shoonya_token:
                    success, msg = place_shoonya_order(st.session_state.shoonya_token, pe_symbol, trade_qty, 'B')
                    if success: 
                        st.session_state.trade_active = True
                        st.session_state.trade_details = {'Type': 'PE', 'Symbol': pe_symbol, 'Qty': trade_qty, 'Status': 'LIVE', 'Entry_Price': curr_p, 'Time': current_time}
                else:
                    st.session_state.trade_active = True
                    st.session_state.trade_details = {'Type': 'PE', 'Symbol': pe_symbol, 'Qty': trade_qty, 'Status': 'PAPER', 'Entry_Price': curr_p, 'Time': current_time}
                st.rerun()

        if st.session_state.trade_active:
            with c3:
                trade = st.session_state.trade_details
                
                # 🚀 LIVE PNL CALCULATION
                if trade['Type'] == 'CE': live_points = round(curr_p - trade['Entry_Price'], 2)
                else: live_points = round(trade['Entry_Price'] - curr_p, 2)
                
                pnl_color_live = "#00ff66" if live_points >= 0 else "#ff3333"
                status_color = "#00ff66" if trade['Status'] == 'LIVE' else "#ffaa00"
                
                st.markdown(f"""
                <div class='live-pnl-box' style='border-left-color: {status_color};'>
                    <div style='display:flex; justify-content:space-between; align-items:center;'>
                        <div>
                            <span style='color:{status_color}; font-weight:bold; font-size:12px;'>● {trade['Status']} TRADE</span><br>
                            <span style='font-size:18px; font-weight:bold;'>{trade['Symbol']}</span><br>
                            <span style='color:#8b949e;'>Entry Spot: ₹{trade['Entry_Price']} | Qty: {trade['Qty']}</span>
                        </div>
                        <div style='text-align:right;'>
                            <span style='color:#8b949e; font-size:12px;'>Live Spot PnL</span><br>
                            <span style='color:{pnl_color_live}; font-size:24px; font-weight:bold;'>{'+' if live_points>0 else ''}{live_points} pts</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button("⏹️ SQUARE-OFF & SAVE LOG", use_container_width=True):
                    exit_time = datetime.datetime.now().strftime("%H:%M:%S")
                    if trade['Status'] == 'LIVE' and st.session_state.shoonya_token:
                        place_shoonya_order(st.session_state.shoonya_token, trade['Symbol'], trade['Qty'], 'S')
                    
                    # Save to Trade History
                    log_entry = {
                        "Date": datetime.datetime.now().strftime("%Y-%m-%d"),
                        "Entry Time": trade['Time'],
                        "Exit Time": exit_time,
                        "Type": trade['Type'],
                        "Strike": trade['Symbol'],
                        "Entry Spot": trade['Entry_Price'],
                        "Exit Spot": curr_p,
                        "PnL (Points)": live_points,
                        "Mode": trade['Status']
                    }
                    st.session_state.trade_history.append(log_entry)
                    st.session_state.trade_active = False
                    st.session_state.trade_details = {}
                    st.rerun()

        # Plotly Chart
        plot_df = df.tail(180) 
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Close'], name='Spot Price', line=dict(color='#deff9a', width=2.5)))
        if 'VWAP' in plot_df.columns: fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['VWAP'], name='VWAP (Micro)', line=dict(color='#00ffff', width=2, dash='dash')))
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['EMA_200'], name='200 EMA (Macro)', line=dict(color='#ffaa00', width=2)))
        
        # Draw Entry Line if trade is active
        if st.session_state.trade_active:
            fig.add_hline(y=st.session_state.trade_details['Entry_Price'], line_dash="dot", line_color="#00ff66", annotation_text="Your Entry", annotation_font_color="#00ff66")
            
        fig.update_layout(template='plotly_dark', paper_bgcolor='#0b0e11', plot_bgcolor='#0b0e11', height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#2d3748'))
        st.plotly_chart(fig, use_container_width=True)
        
    else:
        st.error("⚠️ Data Sync Failed.")

# ==============================================================================
# 7. TRADE BOOK & JOURNAL (THE LOGS)
# ==============================================================================
st.markdown("<hr style='border-color:#2d3748;'>", unsafe_allow_html=True)
st.markdown("### 📓 TRADE BOOK & LIVE LOGS")

if len(st.session_state.trade_history) > 0:
    # Convert history to DataFrame for clean table display
    history_df = pd.DataFrame(st.session_state.trade_history)
    
    # Custom styling function for PnL column
    def color_pnl(val):
        color = '#00ff66' if val > 0 else '#ff3333' if val < 0 else '#8b949e'
        return f'color: {color}; font-weight: bold;'
    
    styled_df = history_df.style.applymap(color_pnl, subset=['PnL (Points)'])
    st.dataframe(styled_df, use_container_width=True, hide_index=True)
    
    # Option to clear logs
    if st.button("🗑️ Clear Trade Book"):
        st.session_state.trade_history = []
        st.rerun()
else:
    st.info("आज अभी तक कोई ट्रेड नहीं लिया गया है। (No trades executed today).")
