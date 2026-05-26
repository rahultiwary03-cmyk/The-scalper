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
SHOONYA_PWD = "Rahul@1995" 
SHOONYA_API_KEY = "7cf713be1c14cb0020e7012d412c5f05" 
SHOONYA_VC = "FN209492_U" 
SHOONYA_TOTP_SECRET = "7S4S46UM2426XWQZ5726OO6QIXD6LYNT" 

# ==============================================================================
# 2. ASSET CONFIGURATION & TIMEZONE FIX
# ==============================================================================
import os
os.environ['TZ'] = 'Asia/Kolkata' # Force IST Timezone
try: time.tzset()
except: pass # For Windows compatibility

def get_ist_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)

ASSET_MAP = {
    "NIFTY 50": {"ticker": "^NSEI", "lot": 25, "exch": "NFO", "ws_token": "NSE|26000", "tg_pts": 50}, # Target logic
    "BANKNIFTY": {"ticker": "^NSEBANK", "lot": 15, "exch": "NFO", "ws_token": "NSE|26009", "tg_pts": 100},
    "GOLD (Global)": {"ticker": "GC=F", "lot": 1, "exch": "MCX", "ws_token": None, "tg_pts": 10}, 
    "BITCOIN (Crypto)": {"ticker": "BTC-USD", "lot": 1, "exch": "CRYPTO", "ws_token": None, "tg_pts": 500} 
}

SWING_STOCKS = ["RELIANCE.NS", "TATAMOTORS.NS", "SBIN.NS", "HAL.NS", "HDFC.NS", "INFY.NS", "TCS.NS", "ICICIBANK.NS", "ZOMATO.NS", "BHEL.NS", "M&M.NS", "SUNPHARMA.NS"]

st.set_page_config(page_title="QuantScalper AI v44.0", layout="wide", initial_sidebar_state="collapsed")

if 'ws_ltp' not in st.session_state: st.session_state.ws_ltp = 0.0
if 'ws_status' not in st.session_state: st.session_state.ws_status = "Waiting for API..."
if 'trade_history' not in st.session_state: st.session_state.trade_history = []
if 'trade_active' not in st.session_state: st.session_state.trade_active = False
if 'trade_details' not in st.session_state: st.session_state.trade_details = {}
if 'prev_asset' not in st.session_state: st.session_state.prev_asset = "NIFTY 50"

# ==============================================================================
# 3. SHOONYA CONNECTION ENGINE
# ==============================================================================
def shoonya_login():
    if not SHOONYA_API_KEY or SHOONYA_API_KEY == "YOUR_API_KEY": return None, "No API Key Provided"
    try:
        import pyotp, hashlib
        pwd_sha256 = hashlib.sha256(SHOONYA_PWD.encode('utf-8')).hexdigest()
        app_key_sha256 = hashlib.sha256(f"{SHOONYA_UID}|{SHOONYA_API_KEY}".encode('utf-8')).hexdigest()
        totp = pyotp.TOTP(SHOONYA_TOTP_SECRET).now()
        payload = {"apkversion": "1.0.0", "uid": SHOONYA_UID, "pwd": pwd_sha256, "factor2": totp, "vc": SHOONYA_VC, "appkey": app_key_sha256, "imei": "abc12345", "source": "API"}
        res = requests.post('https://api.shoonya.com/NorenWClientTP/QuickAuth', data='jData=' + json.dumps(payload), timeout=5)
        try: data = res.json()
        except: return None, "API Offline"
        if data.get('stat') == 'Ok': return data.get('susertoken'), "Success"
        return None, data.get('emsg', 'Login Failed')
    except: return None, "Broker API Offline"

def on_message(ws, message):
    data = json.loads(message)
    if 'lp' in data: st.session_state.ws_ltp = float(data['lp'])
def on_error(ws, error): pass
def on_close(ws, close_status_code, close_msg): st.session_state.ws_status = "🔴 Disconnected"
def on_open(ws):
    st.session_state.ws_status = "🟢 Connected to Shoonya Live"
    ws.send(json.dumps({"t": "c", "uid": SHOONYA_UID, "actid": SHOONYA_UID, "source": "API", "susertoken": st.session_state.shoonya_token}))

def start_shoonya_websocket():
    if not st.session_state.shoonya_token: 
        st.session_state.ws_status = "🔴 API Login Failed / Keys Missing"
        return
    websocket.enableTrace(False)
    ws = websocket.WebSocketApp("wss://api.shoonya.com/NorenWSTP/", on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
    st.session_state.ws_app = ws
    wst = threading.Thread(target=ws.run_forever)
    wst.daemon = True
    wst.start()

if 'shoonya_token' not in st.session_state:
    token, msg = shoonya_login()
    st.session_state.shoonya_token = token
    start_shoonya_websocket()

# ==============================================================================
# 4. CUSTOM STYLING (MASSIVE FONTS)
# ==============================================================================
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; background-color: #0b0e11 !important; color: #e3e9f0 !important; }
    .stApp { background-color: #0b0e11 !important; }
    .metric-box { background: #151a22; padding: 15px; border-radius: 10px; border: 1px solid #2d3748; color: #e3e9f0; box-shadow: 0 4px 6px rgba(0,0,0,0.3);}
    .live-pnl-box { background: rgba(0, 255, 255, 0.05); border: 2px solid #00ffff; padding: 25px; border-radius: 15px; margin-top: 10px; color: white; box-shadow: 0px 0px 20px rgba(0,255,255,0.1);}
    .performance-bar { background: linear-gradient(90deg, #151a22 0%, #1e2532 100%); padding: 15px; border-radius: 8px; margin-bottom: 15px; color:#fff; display:flex; justify-content:space-around; align-items:center; border: 1px solid #2d3748;}
    .live-price-text { font-size: 55px; font-weight: 900; color: #00ffff; text-align: center; margin: 5px 0; text-shadow: 0px 0px 15px rgba(0,255,255,0.3); }
    .massive-target { font-size: 38px; font-weight: 900; color: #00ff66; text-shadow: 0px 0px 10px rgba(0,255,102,0.4); }
    .massive-entry { font-size: 32px; font-weight: 800; color: #00ffff; }
    .massive-sl { font-size: 32px; font-weight: 800; color: #ff3333; }
    .stSelectbox > div > div, .stNumberInput > div > div, .stTextInput > div > div { background-color: #1a202c !important; color: white !important; border: 1px solid #2d3748 !important; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 5. HEADER & PERFORMANCE DASHBOARD
# ==============================================================================
history = st.session_state.trade_history
total_trades = len(history)
wins = len([t for t in history if t['PnL'] > 0])
win_rate = round((wins / total_trades) * 100, 1) if total_trades > 0 else 0.0
net_pnl = sum([t['PnL'] for t in history]) if total_trades > 0 else 0

st.markdown(f"""
    <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom: 10px;'>
        <h1 style='margin:0; font-weight: 900; color:#e3e9f0;'>QUANT<span style='color:#deff9a;'>SCALPER AI</span> v44.0</h1>
        <div style='background:#1a202c; padding:8px 15px; border-radius:20px; font-weight:bold; color: #e3e9f0; border: 1px solid #2d3748;'>📡 API Status: {st.session_state.ws_status}</div>
    </div>
    <div class='performance-bar'>
        <div style='font-size:20px;'><b>WIN RATE:</b> <span style='color:{"#00ff66" if win_rate>=50 else "#ff3333"};'>{win_rate}%</span></div>
        <div style='font-size:20px;'><b>TOTAL TRADES:</b> {total_trades}</div>
        <div style='font-size:20px;'><b>DAY NET PnL:</b> <span style='color:{"#00ff66" if net_pnl>=0 else "#ff3333"}; font-size:26px; font-weight:900;'>{round(net_pnl,2)}</span></div>
    </div>
""", unsafe_allow_html=True)

# ==============================================================================
# 6. UI CONTROLS 
# ==============================================================================
c_opt1, c_opt2, c_opt3, c_opt4 = st.columns(4)
with c_opt1: selected_asset = st.selectbox("🌍 Select Market Asset", list(ASSET_MAP.keys()))
asset_data = ASSET_MAP[selected_asset]
is_crypto = asset_data['exch'] == 'CRYPTO'

if selected_asset != st.session_state.prev_asset:
    st.session_state.prev_asset = selected_asset
    st.session_state.ws_ltp = 0.0 
    if asset_data['ws_token'] and 'ws_app' in st.session_state and st.session_state.shoonya_token:
        try: st.session_state.ws_app.send(json.dumps({"t": "t", "k": asset_data['ws_token']}))
        except: pass

with c_opt2: expiry_date = st.text_input("Options Expiry", value="28MAY26" if not is_crypto else "N/A", disabled=is_crypto) 
with c_opt3: trade_qty = st.number_input(f"Qty (Auto-Lot)", min_value=asset_data['lot'], step=asset_data['lot'], value=asset_data['lot'])
with c_opt4: 
    live_mode = st.toggle("🔴 LIVE TRADING", value=False, disabled=is_crypto)
    auto_refresh = st.toggle("🔄 Auto-Tick Engine", value=False)

# ==============================================================================
# 7. UNIVERSAL DATA ENGINE (MTF & SMC)
# ==============================================================================
@st.cache_data(ttl=30)
def fetch_omni_data(ticker):
    try:
        df_1m = yf.download(ticker, period='3d', interval='1m', progress=False)
        df_1h = yf.download(ticker, period='1mo', interval='1h', progress=False)
        df_1d = yf.download(ticker, period='3mo', interval='1d', progress=False)
        
        for df in [df_1m, df_1h, df_1d]:
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                if df.index.tz is not None: df.index = df.index.tz_localize(None)
                
        return df_1m, df_1h, df_1d
    except: return None, None, None

df_1m, df_1h, df_1d = fetch_omni_data(asset_data['ticker'])

yf_curr_p = round(float(df_1m['Close'].iloc[-1]), 2) if df_1m is not None and not df_1m.empty else 0.0
curr_p = st.session_state.ws_ltp if (st.session_state.ws_ltp > 0 and asset_data['ws_token']) else yf_curr_p

fvg_list = []
safe_sl_pts = 20.0; vwap_val = curr_p; ema_1m = curr_p; pdh = curr_p; pdl = curr_p
vol_anomaly = False

current_hour = get_ist_now().time()
in_kill_zone = (datetime.time(9, 15) <= current_hour <= datetime.time(10, 30)) or (datetime.time(13, 30) <= current_hour <= datetime.time(15, 0))

if df_1m is not None and not df_1m.empty:
    try:
        tr = pd.concat([df_1m['High'] - df_1m['Low'], (df_1m['High'] - df_1m['Close'].shift(1)).abs(), (df_1m['Low'] - df_1m['Close'].shift(1)).abs()], axis=1).max(axis=1)
        safe_sl_pts = round(float(tr.rolling(14).mean().iloc[-1]) * 2.5, 2)
        df_1m['EMA_200'] = df_1m['Close'].ewm(span=200, adjust=False).mean()
        ema_1m = round(float(df_1m['EMA_200'].iloc[-1]), 2)
        
        last_day = df_1m.index[-1].date()
        day_data = df_1m[df_1m.index.date == last_day].copy()
        if day_data['Volume'].sum() > 0:
            day_data['VWAP'] = (day_data['Close'] * day_data['Volume']).cumsum() / (day_data['Volume'].cumsum() + 1e-10)
            vwap_val = round(float(day_data['VWAP'].iloc[-1]), 2)
            df_1m.loc[day_data.index, 'VWAP'] = day_data['VWAP']

        if df_1m['Close'].iloc[-1] > df_1m['Open'].iloc[-1] and df_1m['Volume'].iloc[-1] < df_1m['Volume'].iloc[-2]: vol_anomaly = True

        if len(df_1m) > 20:
            for i in range(len(df_1m)-20, len(df_1m)-2):
                if df_1m['Low'].iloc[i+2] > df_1m['High'].iloc[i]: 
                    fvg_bot = df_1m['High'].iloc[i]; fvg_top = df_1m['Low'].iloc[i+2]
                    if df_1m['Low'].iloc[i+3:].min() > fvg_bot: fvg_list.append({"type":"BULLISH", "top":fvg_top, "bot":fvg_bot})
                elif df_1m['High'].iloc[i+2] < df_1m['Low'].iloc[i]: 
                    fvg_top = df_1m['Low'].iloc[i]; fvg_bot = df_1m['High'].iloc[i+2]
                    if df_1m['High'].iloc[i+3:].max() < fvg_top: fvg_list.append({"type":"BEARISH", "top":fvg_top, "bot":fvg_bot})
    except: pass

if df_1d is not None and not df_1d.empty:
    try:
        pdh = round(float(df_1d['High'].iloc[-2]), 2)
        pdl = round(float(df_1d['Low'].iloc[-2]), 2)
    except: pass

# ==============================================================================
# 8. BIG LIVE PRICE & AI RATIONALE
# ==============================================================================
st.markdown(f"<div class='metric-box'><div style='text-align:center; color:#8b949e; font-weight:bold; font-size:18px;'>LIVE SPOT ({selected_asset})</div><div class='live-price-text'>₹ {curr_p}</div></div><br>", unsafe_allow_html=True)

bias_1d = "🟩 Bullish" if df_1d is not None and curr_p > df_1d['Close'].ewm(span=20).mean().iloc[-1] else "🟥 Bearish"
bias_1h = "🟩 Bullish" if df_1h is not None and curr_p > df_1h['Close'].ewm(span=50).mean().iloc[-1] else "🟥 Bearish"
bias_1m = "🟩 Bullish" if curr_p > vwap_val else "🟥 Bearish"

st.markdown(f"<div style='text-align:center; padding:10px; background:#1e2532; color:#e3e9f0; border-radius:5px; border:1px solid #2d3748; margin-bottom:15px; font-size:18px;'><b>MTF CONFLUENCE:</b> 1D [{bias_1d}] &nbsp;|&nbsp; 1H [{bias_1h}] &nbsp;|&nbsp; 1m [{bias_1m}]</div>", unsafe_allow_html=True)

rationale = []
can_ce, can_pe = False, False

if not in_kill_zone: rationale.append("⚠️ <b>Time Filter:</b> Outside Kill Zone. Volume might be low.")
if vol_anomaly: rationale.append("🚨 <b>Volume Anomaly:</b> Price is moving but volume is dropping. Operator Fake Move.")

if curr_p > ema_1m and curr_p > vwap_val and not vol_anomaly: bias, color, can_ce = "STRONG LONG (Bullish)", "#00ff66", True; rationale.append("🎯 <b>Execution:</b> Trend is aligned. Execute LONG.")
elif curr_p < ema_1m and curr_p < vwap_val and not vol_anomaly: bias, color, can_pe = "STRONG SHORT (Bearish)", "#ff3333", True; rationale.append("🎯 <b>Execution:</b> Trend is aligned. Execute SHORT.")
else: bias, color = "LIQUIDITY CHOP (WAIT)", "#ffaa00"; rationale.append("🛑 <b>Execution:</b> Trapping zone. Stay Out.")

col_log, col_exec = st.columns([1, 1])
with col_log: st.markdown(f"<div class='metric-box'><h3 style='color:#00ffff; margin-top:0;'>🧠 SMC AI Logic</h3>{'<br>'.join(rationale)}</div>", unsafe_allow_html=True)
with col_exec:
    st.markdown(f"<div class='metric-box' style='text-align:center;'><b>MASTER BIAS</b><br><span style='color:{color}; font-size:28px; font-weight:900;'>{bias}</span></div><br>", unsafe_allow_html=True)
    
    trade_sym = asset_data['ticker'] if is_crypto else f"{selected_asset[:5]}{expiry_date}C{int(round(curr_p/50)*50)}"
    trade_sym_pe = asset_data['ticker'] if is_crypto else f"{selected_asset[:5]}{expiry_date}P{int(round(curr_p/50)*50)}"

    btn1, btn2 = st.columns(2)
    with btn1:
        if st.button("🟢 EXECUTE LONG", disabled=not can_ce or st.session_state.trade_active, use_container_width=True):
            tg_price = curr_p + asset_data['tg_pts']
            st.session_state.trade_active = True
            st.session_state.trade_details = {'Type':'LONG', 'Sym':trade_sym, 'Qty':trade_qty, 'Status':'LIVE' if live_mode else 'PAPER', 'Entry':curr_p, 'Target': tg_price, 'Time':get_ist_now().strftime("%H:%M:%S")}
            st.rerun()
    with btn2:
        if st.button("🔴 EXECUTE SHORT", disabled=not can_pe or st.session_state.trade_active, use_container_width=True):
            tg_price = curr_p - asset_data['tg_pts']
            st.session_state.trade_active = True
            st.session_state.trade_details = {'Type':'SHORT', 'Sym':trade_sym_pe, 'Qty':trade_qty, 'Status':'LIVE' if live_mode else 'PAPER', 'Entry':curr_p, 'Target': tg_price, 'Time':get_ist_now().strftime("%H:%M:%S")}
            st.rerun()

# ==============================================================================
# 9. ACTIVE TRADE PANEL (MASSIVE TARGET/ENTRY)
# ==============================================================================
if st.session_state.trade_active:
    t = st.session_state.trade_details
    live_points = round(curr_p - t['Entry'], 2) if t['Type'] == 'LONG' else round(t['Entry'] - curr_p, 2)
    trail_sl = t['Entry'] if live_points >= safe_sl_pts else (t['Entry'] - safe_sl_pts if t['Type'] == 'LONG' else t['Entry'] + safe_sl_pts)

    pcol = "#00ff66" if live_points >= 0 else "#ff3333"
    st.markdown(f"""
    <div class='live-pnl-box'>
        <div style='display:flex; justify-content:space-between; align-items:center;'>
            <div style='width: 60%;'>
                <h2 style='margin:0; color:#e3e9f0;'>{t['Status']} {t['Type']} | {t['Sym']}</h2>
                <hr style='border-color:#2d3748; margin: 10px 0;'>
                <div style='display:flex; justify-content:space-between;'>
                    <div><span style='color:#8b949e; font-size:18px;'>ENTRY SPOT</span><br><span class='massive-entry'>₹ {t['Entry']}</span></div>
                    <div><span style='color:#8b949e; font-size:18px;'>TARGET</span><br><span class='massive-target'>₹ {t['Target']}</span></div>
                    <div><span style='color:#8b949e; font-size:18px;'>TRAIL SL</span><br><span class='massive-sl'>₹ {round(trail_sl,2)}</span></div>
                </div>
            </div>
            <div style='text-align:right; width: 35%;'>
                <span style='color:#8b949e; font-size:20px;'>LIVE PnL (Points)</span><br>
                <b style='color:{pcol}; font-size:65px; font-weight:900;'>{'+' if live_points>0 else ''}{live_points}</b>
            </div>
        </div>
    </div>""", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🛑 SQUARE-OFF TRADE", use_container_width=True):
        st.session_state.trade_history.append({"Date": get_ist_now().strftime("%Y-%m-%d"), "Time": get_ist_now().strftime("%H:%M:%S"), "Asset": selected_asset, "Type": t['Type'], "Entry Spot": t['Entry'], "Exit Spot": curr_p, "PnL": live_points, "Mode": t['Status']})
        st.session_state.trade_active = False; st.session_state.trade_details = {}
        st.rerun()

# ==============================================================================
# 10. VISUAL CHART (Y-AXIS FIX)
# ==============================================================================
st.markdown("### 📊 SMC Master Chart")
if df_1m is not None and not df_1m.empty:
    try:
        plot_df = df_1m.tail(150).copy()
        plot_df['Time_Str'] = plot_df.index.strftime('%H:%M | %d-%b')
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=plot_df['Time_Str'], open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name='Market'))
        if 'VWAP' in plot_df.columns: fig.add_trace(go.Scatter(x=plot_df['Time_Str'], y=plot_df['VWAP'], name='VWAP', line=dict(color='#00ffff', width=1.5, dash='dash')))
        fig.add_trace(go.Scatter(x=plot_df['Time_Str'], y=plot_df['EMA_200'], name='200 EMA', line=dict(color='#ffaa00', width=1.5)))
        for fvg in fvg_list:
            c = "rgba(255, 51, 51, 0.2)" if fvg['type'] == "BEARISH" else "rgba(0, 255, 102, 0.2)"
            fig.add_hrect(y0=fvg['bot'], y1=fvg['top'], fillcolor=c, opacity=0.4, line_width=0)
        fig.add_hline(y=pdh, line_dash="dot", line_color="#ff3333", annotation_text="PDH")
        fig.add_hline(y=pdl, line_dash="dot", line_color="#00ff66", annotation_text="PDL")
        if st.session_state.trade_active: fig.add_hline(y=st.session_state.trade_details['Entry'], line_dash="solid", line_color="#00ffff", annotation_text="ENTRY")
        
        y_min = plot_df['Low'].min()
        y_max = plot_df['High'].max()
        y_buffer = (y_max - y_min) * 0.4 if (y_max - y_min) > 0 else y_min * 0.001
        
        fig.update_layout(template="plotly_dark", height=550, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(showgrid=False, type='category', categoryorder='category ascending', nticks=10), yaxis=dict(gridcolor="#2d3748", range=[y_min - y_buffer, y_max + y_buffer]), paper_bgcolor="#0b0e11", plot_bgcolor="#0b0e11")
        st.plotly_chart(fig, use_container_width=True, theme=None)
    except: pass

# ==============================================================================
# 11. 🚀 10% SWING STOCK FINDER (NEW)
# ==============================================================================
st.markdown("<hr style='border-color:#2d3748;'>", unsafe_allow_html=True)
with st.expander("🚀 SCALPER 10% SWING FINDER (Next 2-3 Days Momentum)"):
    st.markdown("### Operator Breakout Scanner")
    if st.button("🔍 Scan Top High-Beta Stocks", use_container_width=True):
        with st.spinner("Scanning Market for Institutional Buying..."):
            found_stocks = []
            for sym in SWING_STOCKS:
                try:
                    sdf = yf.download(sym, period="1mo", interval="1d", progress=False)
                    if not sdf.empty and len(sdf) > 5:
                        if isinstance(sdf.columns, pd.MultiIndex): sdf.columns = sdf.columns.get_level_values(0)
                        curr_c = float(sdf['Close'].iloc[-1])
                        prev_c = float(sdf['Close'].iloc[-2])
                        avg_vol = sdf['Volume'].tail(10).mean()
                        curr_vol = float(sdf['Volume'].iloc[-1])
                        
                        # Logic: Price Up + Volume > 1.5x Avg (Operator Entry)
                        if curr_c > prev_c and curr_vol > (avg_vol * 1.5):
                            target = round(curr_c * 1.10, 2) # 10% Target
                            sl = round(curr_c * 0.95, 2)     # 5% SL
                            found_stocks.append({"Stock": sym.replace(".NS", ""), "Entry Price": round(curr_c, 2), "Target (10%)": f"₹ {target}", "Stop Loss": f"₹ {sl}", "Status": "🔥 BREAKOUT"})
                except: pass
            
            if found_stocks:
                scan_df = pd.DataFrame(found_stocks)
                def highlight_target(val): return 'color: #00ff66; font-weight: 900;'
                def highlight_sl(val): return 'color: #ff3333; font-weight: 800;'
                def highlight_entry(val): return 'color: #00ffff; font-weight: 800;'
                
                st.dataframe(scan_df.style.map(highlight_target, subset=['Target (10%)']).map(highlight_sl, subset=['Stop Loss']).map(highlight_entry, subset=['Entry Price']), use_container_width=True, hide_index=True)
            else:
                st.info("No 10% momentum setups found today. Market is resting.")

# ==============================================================================
# 12. TRADE BOOK 
# ==============================================================================
st.markdown("<hr style='border-color:#2d3748;'>", unsafe_allow_html=True)
if len(st.session_state.trade_history) > 0:
    st.markdown("### 📓 SECURE TRADE BOOK")
    history_df = pd.DataFrame(st.session_state.trade_history)
    def style_pnl(val): return f"color: {'#00ff66' if val > 0 else '#ff3333' if val < 0 else '#ffffff'}; font-weight: bold;"
    def style_entry(val): return "color: #00ffff; font-weight: bold;" 
    def style_exit(val): return "color: #ffaa00; font-weight: bold;"  
    st.dataframe(history_df.style.map(style_pnl, subset=['PnL']).map(style_entry, subset=['Entry Spot']).map(style_exit, subset=['Exit Spot']), use_container_width=True, hide_index=True)

if auto_refresh: time.sleep(2); st.rerun()
