import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import datetime
import requests
import json
import threading
import websocket  

# ==============================================================================
# 1. 🔑 SHOONYA API CREDENTIALS 
# ==============================================================================
SHOONYA_UID = "FN209492" 
SHOONYA_PWD = "YOUR_PASSWORD" 
SHOONYA_API_KEY = "7cf713be1c14cb0020e7012d412c5f05" 
SHOONYA_VC = "FN209492_U" 
SHOONYA_TOTP_SECRET = "7S4S46UM2426XWQZ5726OO6QIXD6LYNT"

# ==============================================================================
# 2. SHOONYA LIVE LOGIN & WEBSOCKET ENGINE
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

def place_shoonya_order(susertoken, trading_symbol, qty, buy_sell='B'):
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

# --- WEBSOCKET ENGINE ---
def on_message(ws, message):
    data = json.loads(message)
    if 'lp' in data: st.session_state.live_ltp = float(data['lp'])

def on_error(ws, error): pass
def on_close(ws, close_status_code, close_msg): st.session_state.ws_status = "Disconnected"
def on_open(ws):
    st.session_state.ws_status = "Connected Live ⚡"
    auth_payload = {"t": "c", "uid": SHOONYA_UID, "actid": SHOONYA_UID, "source": "API", "susertoken": st.session_state.shoonya_token}
    ws.send(json.dumps(auth_payload))
    sub_payload = {"t": "t", "k": "NSE|26000"} 
    ws.send(json.dumps(sub_payload))

def start_shoonya_websocket():
    if not st.session_state.shoonya_token: return
    websocket.enableTrace(False)
    ws = websocket.WebSocketApp("wss://api.shoonya.com/NorenWSTP/", on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
    wst = threading.Thread(target=ws.run_forever)
    wst.daemon = True
    wst.start()

# ==============================================================================
# 3. PAGE CONFIG & PERSISTENT STATE 
# ==============================================================================
st.set_page_config(page_title="QuantScalper AI v35.3 [NSE 2026]", layout="wide", initial_sidebar_state="collapsed")

if 'live_ltp' not in st.session_state: st.session_state.live_ltp = 0.0
if 'ws_status' not in st.session_state: st.session_state.ws_status = "Initializing..."
if 'trade_history' not in st.session_state: st.session_state.trade_history = []
if 'trade_active' not in st.session_state: st.session_state.trade_active = False
if 'trade_details' not in st.session_state: st.session_state.trade_details = {}

if 'shoonya_token' not in st.session_state:
    token, msg = shoonya_login()
    st.session_state.shoonya_token = token
    st.session_state.shoonya_msg = msg
    if token: start_shoonya_websocket()

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
# 4. HEADER & ALGO SETTINGS
# ==============================================================================
total_trades = len(st.session_state.trade_history)
net_pnl = sum([t['PnL (Points)'] for t in st.session_state.trade_history]) if total_trades > 0 else 0
pnl_color = "#00ff66" if net_pnl >= 0 else "#ff3333"

col_h1, col_h2 = st.columns([2, 1])
with col_h1: 
    ws_badge = f"<span style='color:#00ffff; font-size:14px;'>📡 {st.session_state.ws_status}</span>"
    st.markdown(f"<h1 style='margin:0; font-weight:800;'>QUANT<span style='color:#deff9a;'>SCALPER AI</span> v35.3 {ws_badge}</h1>", unsafe_allow_html=True)
with col_h2: 
    st.markdown(f"<div style='text-align:right; font-size:18px; font-weight:bold;'>Trades: {total_trades} | Day PnL: <span style='color:{pnl_color};'>{net_pnl} pts</span></div>", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#2d3748; margin: 5px 0 15px 0;'>", unsafe_allow_html=True)

# ✅ UPDATED 2026 NSE LOT SIZES
def get_lot_size(index_name):
    if "NIFTY" in index_name and "BANK" not in index_name: return 65
    elif "BANKNIFTY" in index_name: return 30
    return 65

c_opt1, c_opt2, c_opt3, c_opt4 = st.columns(4)
with c_opt1: expiry_date = st.text_input("Nifty Expiry", value="28MAY26") 
with c_opt2: index_choice = st.selectbox("Index", ["NIFTY 50", "BANKNIFTY"])
with c_opt3: trade_qty = st.number_input(f"Qty (Lot Multiples of {get_lot_size(index_choice)})", min_value=get_lot_size(index_choice), step=get_lot_size(index_choice), value=get_lot_size(index_choice))
with c_opt4: live_mode = st.toggle("🔴 ENABLE LIVE TRADING", value=False)

# ==============================================================================
# 5. DATA FETCH & SIGNAL GENERATION
# ==============================================================================
@st.cache_data(ttl=30)
def fetch_macro_data():
    try: return yf.download('^NSEI', period='3d', interval='1m', progress=False)
    except: return None

with st.spinner('Syncing Macro Trend...'):
    df = fetch_macro_data()
    vwap_val = 23740.0; macro_trend = 23760.0; safe_sl_pts = 25.0
    yfinance_curr_p = 23750.0

    if df is not None and not df.empty:
        try:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            yfinance_curr_p = round(float(df['Close'].iloc[-1]), 2)
            df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
            macro_trend = round(float(df['EMA_200'].iloc[-1]), 2)
            
            last_day = df.index[-1].date()
            day_data = df[df.index.date == last_day].copy()
            if not day_data.empty and day_data['Volume'].sum() > 0:
                day_data['VWAP'] = (day_data['Close'] * day_data['Volume']).cumsum() / (day_data['Volume'].cumsum() + 1e-10)
                vwap_val = round(float(day_data['VWAP'].iloc[-1]), 2)
                df.loc[day_data.index, 'VWAP'] = day_data['VWAP']
            else: vwap_val = yfinance_curr_p; df['VWAP'] = df['Close'].ewm(span=20, adjust=False).mean()

            tr = pd.concat([df['High'] - df['Low'], (df['High'] - df['Close'].shift(1)).abs(), (df['Low'] - df['Close'].shift(1)).abs()], axis=1).max(axis=1)
            safe_sl_pts = max(20.0, round(float(tr.rolling(14).mean().iloc[-1]) * 2.5, 1))
        except:
            st.error("⚠️ Data Sync Issue (Weekend Mode). Wait for Monday market.")

    curr_p = st.session_state.live_ltp if st.session_state.live_ltp > 0 else yfinance_curr_p

    m1, m2, m3, m4 = st.columns(4)
    with m1: st.metric("LIVE SPOT (HFT)", f"₹{curr_p}")
    with m2: st.metric("Micro POC (VWAP)", f"₹{vwap_val}")
    with m3: st.metric("Macro Trend (200 EMA)", f"₹{macro_trend}")
    with m4: st.metric("Dynamic SL Buffer", f"{safe_sl_pts} pts")

    if curr_p > macro_trend and curr_p > vwap_val: bias, color, can_trade = "STRONG BULLISH", "#00ff66", True
    elif curr_p < macro_trend and curr_p < vwap_val: bias, color, can_trade = "STRONG BEARISH", "#ff3333", True
    else: bias, color, can_trade = "CHOPPY (WAIT)", "#ffaa00", False

    st.markdown(f"<div class='metric-box'><b>AI Master Bias:</b> <span style='color:{color}; font-size:18px;'>{bias}</span></div><br>", unsafe_allow_html=True)

    # ------------------------------------------------------------------------------
    # 6. EXECUTION & LIVE PNL MONITORING
    # ------------------------------------------------------------------------------
    index_factor = 100 if "BANK" in index_choice else 50
    atm_strike = int(round(curr_p / index_factor) * index_factor)
    ce_symbol = f"{index_choice[:5]}{expiry_date}C{atm_strike}" 
    pe_symbol = f"{index_choice[:5]}{expiry_date}P{atm_strike}"

    def calculate_trailing_sl(entry,current, pnl_points, trade_type, sl_buffer):
        if pnl_points >= 10: return entry 
        if trade_type == 'CE': return entry - sl_buffer
        else: return entry + sl_buffer

    c1, c2, c3 = st.columns([1, 1, 3])
    with c1:
        if st.button(f"🟢 BUY CE ({atm_strike})", disabled=not can_trade or st.session_state.trade_active, use_container_width=True):
            current_time = datetime.datetime.now().strftime("%H:%M:%S")
            if live_mode and st.session_state.shoonya_token:
                succ, msg = place_shoonya_order(st.session_state.shoonya_token, ce_symbol, trade_qty, 'B')
                if succ: 
                    st.session_state.trade_active = True
                    st.session_state.trade_details = {'Type':'CE', 'Sym':ce_symbol, 'Qty':trade_qty, 'Status':'LIVE', 'Entry':curr_p, 'Time':current_time}
                else: st.error(f"LIVE Order Failed: {msg}")
            else:
                st.session_state.trade_active = True
                st.session_state.trade_details = {'Type':'CE', 'Sym':ce_symbol, 'Qty':trade_qty, 'Status':'PAPER', 'Entry':curr_p, 'Time':current_time}
            st.rerun()

    with c2:
        if st.button(f"🔴 BUY PE ({atm_strike})", disabled=not can_trade or st.session_state.trade_active, use_container_width=True):
            current_time = datetime.datetime.now().strftime("%H:%M:%S")
            if live_mode and st.session_state.shoonya_token:
                succ, msg = place_shoonya_order(st.session_state.shoonya_token, pe_symbol, trade_qty, 'B')
                if succ: 
                    st.session_state.trade_active = True
                    st.session_state.trade_details = {'Type':'PE', 'Sym':pe_symbol, 'Qty':trade_qty, 'Status':'LIVE', 'Entry':curr_p, 'Time':current_time}
                else: st.error(f"LIVE Order Failed: {msg}")
            else:
                st.session_state.trade_active = True
                st.session_state.trade_details = {'Type':'PE', 'Sym':pe_symbol, 'Qty':trade_qty, 'Status':'PAPER', 'Entry':curr_p, 'Time':current_time}
            st.rerun()

    if st.session_state.trade_active:
        with c3:
            t = st.session_state.trade_details
            live_points = round(curr_p - t['Entry'], 2) if t['Type'] == 'CE' else round(t['Entry'] - curr_p, 2)
            trail_sl = calculate_trailing_sl(t['Entry'], curr_p, live_points, t['Type'], safe_sl_pts)
            pcol = "#00ff66" if live_points >= 0 else "#ff3333"
            status_color = "#00ffff" if t['Status'] == 'LIVE' else "#ffaa00"
            
            st.markdown(f"""
            <div class='live-pnl-box' style='border-left-color: {status_color};'>
                <div style='display:flex; justify-content:space-between;'>
                    <div><b style='color:{status_color};'>● {t['Status']}</b> {t['Type']} | {t['Sym']} <br> <span style='color:#8b949e;'>Entry Spot: ₹{t['Entry']} | Trail SL: ₹{trail_sl}</span></div>
                    <div style='text-align:right;'><span style='color:#8b949e;'>Live Spot PnL</span><br><b style='color:{pcol}; font-size:24px;'>{'+' if live_points>0 else ''}{live_points} pts</b></div>
                </div>
            </div>""", unsafe_allow_html=True)
            
            if st.button("⏹️ SQUARE-OFF POSITION", use_container_width=True):
                if t['Status'] == 'LIVE' and st.session_state.shoonya_token:
                    place_shoonya_order(st.session_state.shoonya_token, t['Sym'], t['Qty'], 'S')
                
                exit_time = datetime.datetime.now().strftime("%H:%M:%S")
                st.session_state.trade_history.append({
                    "Date": datetime.datetime.now().strftime("%Y-%m-%d"),
                    "Entry Time": t['Time'], "Exit Time": exit_time,
                    "Type": t['Type'], "Symbol": t['Sym'], 
                    "Entry Spot": t['Entry'], "Exit Spot": curr_p, 
                    "PnL (Points)": live_points, "Mode": t['Status']
                })
                st.session_state.trade_active = False; st.session_state.trade_details = {}
                st.rerun()

    # ------------------------------------------------------------------------------
    # 7. CHART & TRADE BOOK
    # ------------------------------------------------------------------------------
    if df is not None and not df.empty:
        try:
            plot_df = df.tail(180) 
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name='Market'))
            if 'VWAP' in plot_df.columns: fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['VWAP'], name='VWAP (POC)', line=dict(color='#00ffff', width=1.5, dash='dash')))
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['EMA_200'], name='200 EMA (Macro)', line=dict(color='#ffaa00', width=1.5)))
            
            if st.session_state.trade_active: 
                fig.add_hline(y=st.session_state.trade_details['Entry'], line_dash="dot", line_color="#00ff66", annotation_text="Entry")
                
            fig.update_layout(template='plotly_dark', paper_bgcolor='#0b0e11', plot_bgcolor='#0b0e11', height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#2d3748'))
            st.plotly_chart(fig, use_container_width=True)
        except: pass

st.markdown("<hr style='border-color:#2d3748;'>", unsafe_allow_html=True)
c_log1, c_log2 = st.columns([3, 1])
with c_log1: st.markdown("### 📓 DAILY TRADE BOOK")
with c_log2: 
    if st.button("🔄 Sync Live Market & UI"): st.rerun()

if len(st.session_state.trade_history) > 0:
    history_df = pd.DataFrame(st.session_state.trade_history)
    
    def style_pnl(val):
        color = '#00ff66' if val > 0 else '#ff3333' if val < 0 else '#8b949e'
        return f'color: {color}; font-weight: bold;'
        
    st.dataframe(history_df.style.applymap(style_pnl, subset=['PnL (Points)']), use_container_width=True, hide_index=True)
    
    if st.button("🗑️ Clear Trade Book"):
        st.session_state.trade_history = []
        st.session_state.daily_pnl = 0
        st.rerun()
else:
    st.info("No trades executed yet today.")
