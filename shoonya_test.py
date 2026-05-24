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
# 2. ASSET CONFIGURATION (UNIVERSAL ENGINE)
# ==============================================================================
ASSET_MAP = {
    "NIFTY 50": {"ticker": "^NSEI", "lot": 65, "exch": "NFO", "ws_token": "NSE|26000"},
    "BANKNIFTY": {"ticker": "^NSEBANK", "lot": 30, "exch": "NFO", "ws_token": "NSE|26009"},
    "GOLD (Global)": {"ticker": "GC=F", "lot": 1, "exch": "MCX", "ws_token": None}, # Gold uses yfinance live
    "BITCOIN (Crypto)": {"ticker": "BTC-USD", "lot": 1, "exch": "CRYPTO", "ws_token": None} # Crypto uses yfinance live
}

# ==============================================================================
# 3. SHOONYA WEBSOCKET & EXECUTION ENGINE
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
        except: return None, "API Weekend Mode"
        if data.get('stat') == 'Ok': return data.get('susertoken'), "Success"
        return None, data.get('emsg', 'Login Failed')
    except: return None, "Broker API Offline"

def place_shoonya_order(susertoken, trading_symbol, qty, exch, buy_sell='B'):
    if exch == "CRYPTO": return False, "Crypto natively not supported by Shoonya API. Paper Trade Only."
    if not susertoken: return False, "API Not Connected"
    try:
        payload = {"uid": SHOONYA_UID, "actid": SHOONYA_UID, "exch": exch, "tsym": trading_symbol, "qty": str(qty), "prc": "0", "prd": "M", "trantype": buy_sell, "prctyp": "MKT", "ret": "DAY"}
        headers = {'Authorization': f'Bearer {SHOONYA_UID} {susertoken}'}
        res = requests.post('https://api.shoonya.com/NorenWClientTP/PlaceOrder', data='jData=' + json.dumps(payload), headers=headers)
        data = res.json()
        if data.get('stat') == 'Ok': return True, data.get('norenordno')
        else: return False, data.get('emsg', 'Order Rejected')
    except Exception as e: return False, str(e)

def on_message(ws, message):
    data = json.loads(message)
    if 'lp' in data: st.session_state.ws_ltp = float(data['lp'])
def on_error(ws, error): pass
def on_close(ws, close_status_code, close_msg): st.session_state.ws_status = "Disconnected"
def on_open(ws):
    st.session_state.ws_status = "Connected Live ⚡"
    ws.send(json.dumps({"t": "c", "uid": SHOONYA_UID, "actid": SHOONYA_UID, "source": "API", "susertoken": st.session_state.shoonya_token}))

def start_shoonya_websocket():
    if not st.session_state.shoonya_token: return
    websocket.enableTrace(False)
    ws = websocket.WebSocketApp("wss://api.shoonya.com/NorenWSTP/", on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
    st.session_state.ws_app = ws
    wst = threading.Thread(target=ws.run_forever)
    wst.daemon = True
    wst.start()

# ==============================================================================
# 4. PAGE CONFIG & STATE 
# ==============================================================================
st.set_page_config(page_title="QuantScalper AI v39.0 [OMNI-ASSET]", layout="wide", initial_sidebar_state="collapsed")

if 'ws_ltp' not in st.session_state: st.session_state.ws_ltp = 0.0
if 'ws_status' not in st.session_state: st.session_state.ws_status = "Initializing..."
if 'trade_history' not in st.session_state: st.session_state.trade_history = []
if 'trade_active' not in st.session_state: st.session_state.trade_active = False
if 'trade_details' not in st.session_state: st.session_state.trade_details = {}
if 'prev_asset' not in st.session_state: st.session_state.prev_asset = "NIFTY 50"

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
    .metric-box { background: rgba(20, 24, 31, 0.5); padding: 15px; border-radius: 10px; border: 1px solid #2d3748; }
    .logic-box { background: #14181f; border-left: 5px solid #ffaa00; padding: 15px; border-radius: 8px; margin-bottom: 10px; font-size: 14px;}
    .live-pnl-box { background: rgba(0, 255, 255, 0.05); border: 1px solid #00ffff; padding: 15px; border-radius: 8px; margin-top: 10px; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 5. UI HEADER & OMNI-ASSET SETTINGS
# ==============================================================================
total_trades = len(st.session_state.trade_history)
net_pnl = sum([t['PnL (Points)'] for t in st.session_state.trade_history]) if total_trades > 0 else 0

col_h1, col_h2 = st.columns([2, 1])
with col_h1: st.markdown(f"<h1 style='margin:0; font-weight:800;'>QUANT<span style='color:#deff9a;'>SCALPER AI</span> v39.0 🌍</h1>", unsafe_allow_html=True)
with col_h2: st.markdown(f"<div style='text-align:right; font-size:18px; font-weight:bold;'>Trades: {total_trades} | Day Net: <span style='color:{'#00ff66' if net_pnl >= 0 else '#ff3333'};'>{round(net_pnl,2)}</span></div>", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#2d3748; margin: 5px 0 15px 0;'>", unsafe_allow_html=True)

c_opt1, c_opt2, c_opt3, c_opt4 = st.columns(4)
with c_opt1: selected_asset = st.selectbox("🌍 Select Market Asset", list(ASSET_MAP.keys()))

# Asset Switch Logic for WebSocket Subscription
if selected_asset != st.session_state.prev_asset:
    st.session_state.prev_asset = selected_asset
    st.session_state.ws_ltp = 0.0 # Reset Live Price
    if ASSET_MAP[selected_asset]['ws_token'] and 'ws_app' in st.session_state and st.session_state.shoonya_token:
        try: st.session_state.ws_app.send(json.dumps({"t": "t", "k": ASSET_MAP[selected_asset]['ws_token']}))
        except: pass

asset_data = ASSET_MAP[selected_asset]
is_crypto = asset_data['exch'] == 'CRYPTO'

with c_opt2: expiry_date = st.text_input("Options Expiry (Nifty/BankNifty Only)", value="28MAY26" if not is_crypto else "N/A", disabled=is_crypto) 
with c_opt3: trade_qty = st.number_input(f"Qty (Auto-Lot)", min_value=asset_data['lot'], step=asset_data['lot'], value=asset_data['lot'])
with c_opt4: 
    if is_crypto:
        st.warning("Crypto: Paper Trading Auto-Enforced")
        live_mode = False
    else:
        live_mode = st.toggle("🔴 ENABLE LIVE TRADING", value=False)

# ==============================================================================
# 6. UNIVERSAL DATA ENGINE (SMC, FVG, TRAPS)
# ==============================================================================
@st.cache_data(ttl=60)
def fetch_omni_data(ticker):
    try:
        df_1m = yf.download(ticker, period='3d', interval='1m', progress=False)
        df_1d = yf.download(ticker, period='1mo', interval='1d', progress=False)
        if isinstance(df_1m.columns, pd.MultiIndex): 
            df_1m.columns = df_1m.columns.get_level_values(0)
            df_1d.columns = df_1d.columns.get_level_values(0)
        return df_1m, df_1d
    except: return None, None

with st.spinner(f'Syncing {selected_asset} SMC HFT Engine...'):
    df_1m, df_1d = fetch_omni_data(asset_data['ticker'])
    
    # Dynamic Variables
    curr_p = 0.0; vwap_val = 0.0; ema_1m = 0.0; ema_1d = 0.0
    pdh = 0.0; pdl = 0.0; fvg_top = 0; fvg_bot = 0; fvg_type = None; safe_sl_pts = 0.0

    if df_1m is not None and not df_1m.empty:
        try:
            # 1. Price Resolution
            yf_lp = round(float(df_1m['Close'].iloc[-1]), 2)
            # Use Shoonya WS for Indian Indices, Yfinance for Crypto/Gold
            curr_p = st.session_state.ws_ltp if (st.session_state.ws_ltp > 0 and asset_data['ws_token']) else yf_lp
            
            # 2. Dynamic SL based on Asset Volatility (ATR * 2.5)
            tr = pd.concat([df_1m['High'] - df_1m['Low'], (df_1m['High'] - df_1m['Close'].shift(1)).abs(), (df_1m['Low'] - df_1m['Close'].shift(1)).abs()], axis=1).max(axis=1)
            atr = float(tr.rolling(14).mean().iloc[-1])
            safe_sl_pts = round(atr * 2.5, 2)

            # 3. Micro Trends (1m)
            df_1m['EMA_200'] = df_1m['Close'].ewm(span=200, adjust=False).mean()
            ema_1m = round(float(df_1m['EMA_200'].iloc[-1]), 2)
            
            last_day = df_1m.index[-1].date()
            day_data = df_1m[df_1m.index.date == last_day].copy()
            if day_data['Volume'].sum() > 0:
                day_data['VWAP'] = (day_data['Close'] * day_data['Volume']).cumsum() / (day_data['Volume'].cumsum() + 1e-10)
                vwap_val = round(float(day_data['VWAP'].iloc[-1]), 2)
                df_1m.loc[day_data.index, 'VWAP'] = day_data['VWAP']
            else: vwap_val = curr_p

            # 4. FVG Detection
            if len(df_1m) > 20:
                for i in range(len(df_1m)-10, len(df_1m)-2):
                    if df_1m['Low'].iloc[i+2] > df_1m['High'].iloc[i]: 
                        fvg_bot = df_1m['High'].iloc[i]; fvg_top = df_1m['Low'].iloc[i+2]; fvg_type = "BULLISH"
                    elif df_1m['High'].iloc[i+2] < df_1m['Low'].iloc[i]: 
                        fvg_top = df_1m['Low'].iloc[i]; fvg_bot = df_1m['High'].iloc[i+2]; fvg_type = "BEARISH"

            # 5. Macro Trends (1D)
            if df_1d is not None and len(df_1d) > 2:
                df_1d['EMA_20'] = df_1d['Close'].ewm(span=20, adjust=False).mean()
                ema_1d = round(float(df_1d['EMA_20'].iloc[-1]), 2)
                pdh = round(float(df_1d['High'].iloc[-2]), 2)
                pdl = round(float(df_1d['Low'].iloc[-2]), 2)
                
        except Exception as e: st.error(f"Engine Syncing... {e}")

    # ==========================================================================
    # 7. AI RATIONALE & MASTER BIAS
    # ==========================================================================
    rationale = []
    can_ce = False; can_pe = False
    
    # Universal Logic Rationale
    if curr_p > ema_1d: rationale.append("✅ <b>1D Macro:</b> Institution Flow is Bullish.")
    else: rationale.append("❌ <b>1D Macro:</b> Institution Flow is Bearish.")

    trap_zone_buffer = atr * 3 # Dynamic Trap Zone Buffer based on asset
    if curr_p < pdl + trap_zone_buffer and curr_p > pdl - trap_zone_buffer: rationale.append("🔥 <b>Trap Alert:</b> Price near Previous Day Low. Watch for Fake Breakdown (W-Trap) to Go LONG.")
    elif curr_p > pdh - trap_zone_buffer and curr_p < pdh + trap_zone_buffer: rationale.append("🔥 <b>Trap Alert:</b> Price near Previous Day High. Watch for Fake Breakout (M-Trap) to Go SHORT.")

    if fvg_type == "BEARISH" and curr_p > ema_1m: rationale.append("🚨 <b>Bearish FVG:</b> Unmitigated Institutional Sell zone above. Ready for Rejection.")
    
    # Master Decision
    if curr_p > ema_1m and curr_p > vwap_val:
        bias, color, can_ce = "STRONG LONG (Bullish Flow)", "#00ff66", True
        rationale.append("🎯 <b>Execution:</b> Market structure is strongly bullish. Look for Pullbacks to execute LONG (CE/Buy).")
    elif curr_p < ema_1m and curr_p < vwap_val:
        bias, color, can_pe = "STRONG SHORT (Bearish Flow)", "#ff3333", True
        rationale.append("🎯 <b>Execution:</b> Market structure is strongly bearish. Execute SHORT (PE/Sell) on pullbacks.")
    else:
        bias, color = "LIQUIDITY CHOP (WAIT)", "#ffaa00"
        rationale.append("🛑 <b>Execution:</b> SMC Trap Zone. Smart money is confusing retailers. Stay Out.")

    # Execution Panel
    col_log, col_exec = st.columns([1, 1])
    with col_log:
        st.markdown(f"<div class='logic-box'><h3 style='color:#00ffff; margin-top:0;'>🧠 SMC AI Logic ({selected_asset})</h3>{'<br>'.join(rationale)}</div>", unsafe_allow_html=True)
        
    with col_exec:
        st.markdown(f"<div class='metric-box' style='text-align:center;'><b>MASTER BIAS</b><br><span style='color:{color}; font-size:22px; font-weight:800;'>{bias}</span><br><span style='font-size:12px;color:#8b949e;'>Dynamic SL: {safe_sl_pts} | Spot: {curr_p}</span></div><br>", unsafe_allow_html=True)
        
        btn_buy_lbl = "🟢 BUY LONG (CE)" if asset_data['exch'] == 'NFO' else "🟢 BUY (LONG)"
        btn_sell_lbl = "🔴 BUY SHORT (PE)" if asset_data['exch'] == 'NFO' else "🔴 SELL (SHORT)"
        
        # Format Symbol for API
        if asset_data['exch'] == 'NFO':
            atm_strike = int(round(curr_p / 50) * 50) if "NIFTY" in selected_asset and "BANK" not in selected_asset else int(round(curr_p / 100) * 100)
            trade_sym_ce = f"{selected_asset[:5]}{expiry_date}C{atm_strike}"
            trade_sym_pe = f"{selected_asset[:5]}{expiry_date}P{atm_strike}"
        else:
            trade_sym_ce = asset_data['ticker']
            trade_sym_pe = asset_data['ticker']

        btn1, btn2 = st.columns(2)
        with btn1:
            if st.button(btn_buy_lbl, disabled=not can_ce or st.session_state.trade_active, use_container_width=True):
                if live_mode and st.session_state.shoonya_token:
                    succ, msg = place_shoonya_order(st.session_state.shoonya_token, trade_sym_ce, trade_qty, asset_data['exch'], 'B')
                    if succ: st.session_state.trade_active = True; st.session_state.trade_details = {'Type':'LONG', 'Sym':trade_sym_ce, 'Qty':trade_qty, 'Status':'LIVE', 'Entry':curr_p, 'Time':datetime.datetime.now().strftime("%H:%M:%S")}
                else:
                    st.session_state.trade_active = True; st.session_state.trade_details = {'Type':'LONG', 'Sym':trade_sym_ce, 'Qty':trade_qty, 'Status':'PAPER', 'Entry':curr_p, 'Time':datetime.datetime.now().strftime("%H:%M:%S")}
                st.rerun()
        with btn2:
            if st.button(btn_sell_lbl, disabled=not can_pe or st.session_state.trade_active, use_container_width=True):
                if live_mode and st.session_state.shoonya_token:
                    succ, msg = place_shoonya_order(st.session_state.shoonya_token, trade_sym_pe, trade_qty, asset_data['exch'], 'S' if asset_data['exch']!='NFO' else 'B') # For NFO we buy PE, for others we Short sell
                    if succ: st.session_state.trade_active = True; st.session_state.trade_details = {'Type':'SHORT', 'Sym':trade_sym_pe, 'Qty':trade_qty, 'Status':'LIVE', 'Entry':curr_p, 'Time':datetime.datetime.now().strftime("%H:%M:%S")}
                else:
                    st.session_state.trade_active = True; st.session_state.trade_details = {'Type':'SHORT', 'Sym':trade_sym_pe, 'Qty':trade_qty, 'Status':'PAPER', 'Entry':curr_p, 'Time':datetime.datetime.now().strftime("%H:%M:%S")}
                st.rerun()

    # Active Trade Panel
    if st.session_state.trade_active:
        t = st.session_state.trade_details
        live_points = round(curr_p - t['Entry'], 2) if t['Type'] == 'LONG' else round(t['Entry'] - curr_p, 2)
        
        # Dynamic Risk-Free Trailing (Trails to cost after moving 1x SL buffer)
        if live_points >= safe_sl_pts * 0.5: trail_sl = t['Entry'] 
        else: trail_sl = t['Entry'] - safe_sl_pts if t['Type'] == 'LONG' else t['Entry'] + safe_sl_pts

        pcol = "#00ff66" if live_points >= 0 else "#ff3333"
        st.markdown(f"""
        <div class='live-pnl-box'>
            <div style='display:flex; justify-content:space-between; align-items:center;'>
                <div><b>● {t['Status']} {t['Type']}</b> | {t['Sym']} <br> <span style='color:#8b949e;'>Entry: {t['Entry']} | Trail SL: {round(trail_sl,2)}</span></div>
                <div style='text-align:right;'><span style='color:#8b949e;'>Live Spot PnL</span><br><b style='color:{pcol}; font-size:28px;'>{'+' if live_points>0 else ''}{live_points}</b></div>
            </div>
        </div>""", unsafe_allow_html=True)
        
        if st.button("🛑 FORCE SQUARE-OFF", use_container_width=True):
            if t['Status'] == 'LIVE' and st.session_state.shoonya_token: 
                place_shoonya_order(st.session_state.shoonya_token, t['Sym'], t['Qty'], asset_data['exch'], 'S' if t['Type']=='LONG' else 'B')
            
            st.session_state.trade_history.append({"Date": datetime.datetime.now().strftime("%Y-%m-%d"), "Asset": selected_asset, "Type": t['Type'], "Entry Spot": t['Entry'], "Exit Spot": curr_p, "PnL (Points)": live_points, "Mode": t['Status']})
            st.session_state.trade_active = False; st.session_state.trade_details = {}
            st.rerun()

    # ==============================================================================
    # 8. VISUAL CHARTS (OMNI-TABS)
    # ==============================================================================
    st.markdown("### 📊 SMC Liquidity Charts")
    tab1, tab2 = st.tabs(["🎯 1-Minute (Sniper & FVG)", "🌍 1-Day (Macro Liquidity)"])
    
    with tab1:
        if df_1m is not None and not df_1m.empty:
            try:
                plot_df = df_1m.tail(150) 
                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name='Market'))
                if 'VWAP' in plot_df.columns: fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['VWAP'], name='VWAP', line=dict(color='#00ffff', width=1.5, dash='dash')))
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['EMA_200'], name='200 EMA', line=dict(color='#ffaa00', width=1.5)))
                
                if fvg_type is not None:
                    color = "rgba(255, 51, 51, 0.2)" if fvg_type == "BEARISH" else "rgba(0, 255, 102, 0.2)"
                    fig.add_hrect(y0=fvg_bot, y1=fvg_top, fillcolor=color, opacity=0.3, line_width=0, annotation_text=f"{fvg_type} FVG")
                
                if st.session_state.trade_active: fig.add_hline(y=st.session_state.trade_details['Entry'], line_dash="dot", line_color="#00ff66", annotation_text="Your Entry")
                fig.update_layout(template='plotly_dark', paper_bgcolor='#0b0e11', plot_bgcolor='#0b0e11', height=450, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#2d3748'))
                st.plotly_chart(fig, use_container_width=True)
            except: pass
            
    with tab2:
        if df_1d is not None and not df_1d.empty:
            try:
                plot_1d = df_1d.tail(60) 
                fig_1d = go.Figure(data=[go.Candlestick(x=plot_1d.index, open=plot_1d['Open'], high=plot_1d['High'], low=plot_1d['Low'], close=plot_1d['Close'], name='1D')])
                fig_1d.add_hline(y=pdh, line_dash="solid", line_color="#ff3333", annotation_text="PDH (Sell-Side Liquidity)")
                fig_1d.add_hline(y=pdl, line_dash="solid", line_color="#00ff66", annotation_text="PDL (Buy-Side Liquidity)")
                fig_1d.update_layout(template='plotly_dark', paper_bgcolor='#0b0e11', plot_bgcolor='#0b0e11', height=450, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(showgrid=False))
                st.plotly_chart(fig_1d, use_container_width=True)
            except: pass

st.markdown("<hr style='border-color:#2d3748;'>", unsafe_allow_html=True)
c_log1, c_log2, c_log3 = st.columns([2, 1, 1])
with c_log1: st.markdown("### 📓 OMNI-ASSET TRADE BOOK")
with c_log2: 
    if st.button("🔄 Sync Market", use_container_width=True): st.rerun()

if len(st.session_state.trade_history) > 0:
    history_df = pd.DataFrame(st.session_state.trade_history)
    csv = history_df.to_csv(index=False).encode('utf-8')
    with c_log3: st.download_button(label="📥 Export Trade Data (CSV)", data=csv, file_name=f"Quant_Trades_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv", mime="text/csv", use_container_width=True)
    def style_pnl(val): return f"color: {'#00ff66' if val > 0 else '#ff3333' if val < 0 else '#8b949e'}; font-weight: bold;"
    st.dataframe(history_df.style.map(style_pnl, subset=['PnL (Points)']), use_container_width=True, hide_index=True)
else:
    st.info("No trades executed yet today. Switch assets from the top dropdown to scan different markets.")
