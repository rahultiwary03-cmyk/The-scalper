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
# 2. ASSET CONFIGURATION & STATE INIT
# ==============================================================================
ASSET_MAP = {
    "NIFTY 50": {"ticker": "^NSEI", "lot": 65, "exch": "NFO", "ws_token": "NSE|26000"},
    "BANKNIFTY": {"ticker": "^NSEBANK", "lot": 30, "exch": "NFO", "ws_token": "NSE|26009"},
    "GOLD (Global)": {"ticker": "GC=F", "lot": 1, "exch": "MCX", "ws_token": None}, 
    "BITCOIN (Crypto)": {"ticker": "BTC-USD", "lot": 1, "exch": "CRYPTO", "ws_token": None} 
}

st.set_page_config(page_title="QuantScalper AI v41.2", layout="wide", initial_sidebar_state="collapsed")

if 'ws_ltp' not in st.session_state: st.session_state.ws_ltp = 0.0
if 'trade_history' not in st.session_state: st.session_state.trade_history = []
if 'trade_active' not in st.session_state: st.session_state.trade_active = False
if 'trade_details' not in st.session_state: st.session_state.trade_details = {}
if 'prev_asset' not in st.session_state: st.session_state.prev_asset = "NIFTY 50"
if 'theme' not in st.session_state: st.session_state.theme = "Dark"

# ==============================================================================
# 3. DYNAMIC THEME ENGINE (DARK / LIGHT)
# ==============================================================================
col_thm1, col_thm2 = st.columns([8, 1])
with col_thm2:
    if st.button("🌓 Toggle Theme"):
        st.session_state.theme = "Light" if st.session_state.theme == "Dark" else "Dark"

if st.session_state.theme == "Dark":
    bg_color, text_color, box_bg, border_col = "#0b0e11", "#e3e9f0", "rgba(20, 24, 31, 0.7)", "#2d3748"
    chart_template = "plotly_dark"
else:
    bg_color, text_color, box_bg, border_col = "#f4f6f9", "#1a202c", "#ffffff", "#cbd5e1"
    chart_template = "plotly_white"

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    html, body, [class*="css"]  {{ font-family: 'Inter', sans-serif; background-color: {bg_color}; color: {text_color}; transition: all 0.3s;}}
    .stApp {{ background-color: {bg_color}; }}
    .metric-box {{ background: {box_bg}; padding: 15px; border-radius: 10px; border: 1px solid {border_col}; box-shadow: 0 4px 6px rgba(0,0,0,0.1);}}
    .live-pnl-box {{ background: rgba(0, 255, 255, 0.1); border: 2px solid #00ffff; padding: 20px; border-radius: 10px; margin-top: 10px; }}
    .performance-bar {{ background: linear-gradient(90deg, #14181f 0%, #2d3748 100%); padding: 10px; border-radius: 8px; margin-bottom: 15px; color:#fff; display:flex; justify-content:space-around; align-items:center;}}
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 4. SMART PERFORMANCE DASHBOARD & AI SUGGESTIONS
# ==============================================================================
history = st.session_state.trade_history
total_trades = len(history)
wins = len([t for t in history if t['PnL'] > 0])
win_rate = round((wins / total_trades) * 100, 1) if total_trades > 0 else 0.0
net_pnl = sum([t['PnL'] for t in history]) if total_trades > 0 else 0

ai_suggestion = "🟢 System Ready. Awaiting High-Probability Setups."
if total_trades > 3:
    if win_rate < 40: ai_suggestion = "🔴 AI ALERT: Market is choppy. Reduce lot size by 50% or stop trading for today."
    elif win_rate >= 70: ai_suggestion = "🔥 AI ALERT: You are in sync with the market! Trail SL aggressively to capture big moves."

st.markdown(f"""
    <div class='performance-bar'>
        <div style='font-size:18px;'><b>WIN RATE:</b> <span style='color:{"#00ff66" if win_rate>=50 else "#ff3333"};'>{win_rate}%</span></div>
        <div style='font-size:18px;'><b>TOTAL TRADES:</b> {total_trades}</div>
        <div style='font-size:18px;'><b>DAY PnL:</b> <span style='color:{"#00ff66" if net_pnl>=0 else "#ff3333"}; font-size:22px; font-weight:900;'>{round(net_pnl,2)} pts</span></div>
    </div>
    <div style='text-align:center; margin-bottom:15px; font-weight:600; color:#ffaa00;'>🤖 AI Suggestion: {ai_suggestion}</div>
""", unsafe_allow_html=True)

# ==============================================================================
# 5. UI CONTROLS (OMNI-ASSET)
# ==============================================================================
c_opt1, c_opt2, c_opt3, c_opt4 = st.columns(4)
with c_opt1: selected_asset = st.selectbox("🌍 Select Market Asset", list(ASSET_MAP.keys()))
asset_data = ASSET_MAP[selected_asset]
is_crypto = asset_data['exch'] == 'CRYPTO'

with c_opt2: expiry_date = st.text_input("Options Expiry", value="28MAY26" if not is_crypto else "N/A", disabled=is_crypto) 
with c_opt3: trade_qty = st.number_input(f"Qty (Auto-Lot)", min_value=asset_data['lot'], step=asset_data['lot'], value=asset_data['lot'])
with c_opt4: 
    live_mode = st.toggle("🔴 ENABLE LIVE TRADING", value=False, disabled=is_crypto)
    auto_refresh = st.toggle("🔄 Auto-Tick Engine", value=False)

# ==============================================================================
# 6. UNIVERSAL DATA ENGINE (MTF & SMC)
# ==============================================================================
@st.cache_data(ttl=60)
def fetch_omni_data(ticker):
    try:
        df_1m = yf.download(ticker, period='3d', interval='1m', progress=False)
        df_1h = yf.download(ticker, period='1mo', interval='1h', progress=False)
        df_1d = yf.download(ticker, period='3mo', interval='1d', progress=False)
        if isinstance(df_1m.columns, pd.MultiIndex): 
            df_1m.columns = df_1m.columns.get_level_values(0)
            df_1h.columns = df_1h.columns.get_level_values(0)
            df_1d.columns = df_1d.columns.get_level_values(0)
        return df_1m, df_1h, df_1d
    except: 
        return None, None, None

df_1m, df_1h, df_1d = fetch_omni_data(asset_data['ticker'])

curr_p = st.session_state.ws_ltp if st.session_state.ws_ltp > 0 else (round(float(df_1m['Close'].iloc[-1]), 2) if df_1m is not None else 0.0)
fvg_list = []
safe_sl_pts = 20.0; vwap_val = curr_p; ema_1m = curr_p; pdh = curr_p; pdl = curr_p
vol_anomaly = False

current_hour = datetime.datetime.now().time()
in_kill_zone = (datetime.time(9, 15) <= current_hour <= datetime.time(10, 30)) or (datetime.time(13, 30) <= current_hour <= datetime.time(15, 0))

if df_1m is not None and not df_1m.empty:
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

    if df_1m['Close'].iloc[-1] > df_1m['Open'].iloc[-1] and df_1m['Volume'].iloc[-1] < df_1m['Volume'].iloc[-2]:
        vol_anomaly = True

    if len(df_1m) > 20:
        for i in range(len(df_1m)-20, len(df_1m)-2):
            if df_1m['Low'].iloc[i+2] > df_1m['High'].iloc[i]: 
                fvg_bot = df_1m['High'].iloc[i]; fvg_top = df_1m['Low'].iloc[i+2]
                if df_1m['Low'].iloc[i+3:].min() > fvg_bot: fvg_list.append({"type":"BULLISH", "top":fvg_top, "bot":fvg_bot})
            elif df_1m['High'].iloc[i+2] < df_1m['Low'].iloc[i]: 
                fvg_top = df_1m['Low'].iloc[i]; fvg_bot = df_1m['High'].iloc[i+2]
                if df_1m['High'].iloc[i+3:].max() < fvg_top: fvg_list.append({"type":"BEARISH", "top":fvg_top, "bot":fvg_bot})

if df_1d is not None and not df_1d.empty:
    pdh = round(float(df_1d['High'].iloc[-2]), 2)
    pdl = round(float(df_1d['Low'].iloc[-2]), 2)

# ==============================================================================
# 7. MTF CONFLUENCE & AI RATIONALE
# ==============================================================================
bias_1d = "🟩 Bullish" if df_1d is not None and curr_p > df_1d['Close'].ewm(span=20).mean().iloc[-1] else "🟥 Bearish"
bias_1h = "🟩 Bullish" if df_1h is not None and curr_p > df_1h['Close'].ewm(span=50).mean().iloc[-1] else "🟥 Bearish"
bias_1m = "🟩 Bullish" if curr_p > vwap_val else "🟥 Bearish"

st.markdown(f"""<div style='text-align:center; padding:10px; background:{box_bg}; border-radius:5px; border:1px solid {border_col}; margin-bottom:15px;'>
    <b>MTF CONFLUENCE:</b> 1D [{bias_1d}] &nbsp;|&nbsp; 1H [{bias_1h}] &nbsp;|&nbsp; 1m [{bias_1m}]
</div>""", unsafe_allow_html=True)

rationale = []
can_ce, can_pe = False, False

if not in_kill_zone: rationale.append("⚠️ <b>Time Filter:</b> Outside Kill Zone. Institutions are resting. Low volume expected.")
if vol_anomaly: rationale.append("🚨 <b>Volume Anomaly:</b> Price is moving but volume is dropping. FAKE MOVE suspected by Operators.")

if curr_p > ema_1m and curr_p > vwap_val and not vol_anomaly:
    bias, color, can_ce = "STRONG LONG (Bullish Structure)", "#00ff66", True
    rationale.append("🎯 <b>Execution:</b> Trend is aligned. Execute LONG.")
elif curr_p < ema_1m and curr_p < vwap_val and not vol_anomaly:
    bias, color, can_pe = "STRONG SHORT (Bearish Structure)", "#ff3333", True
    rationale.append("🎯 <b>Execution:</b> Trend is aligned. Execute SHORT.")
else:
    bias, color = "LIQUIDITY CHOP (WAIT)", "#ffaa00"
    rationale.append("🛑 <b>Execution:</b> Trapping zone. Stay Out.")

col_log, col_exec = st.columns([1, 1])
with col_log:
    st.markdown(f"<div class='metric-box'><h3 style='color:#00ffff; margin-top:0;'>🧠 SMC AI Logic</h3>{'<br>'.join(rationale)}</div>", unsafe_allow_html=True)
    
with col_exec:
    st.markdown(f"<div class='metric-box' style='text-align:center;'><b>MASTER BIAS</b><br><span style='color:{color}; font-size:22px; font-weight:800;'>{bias}</span></div><br>", unsafe_allow_html=True)
    
    trade_sym = asset_data['ticker'] if is_crypto else f"{selected_asset[:5]}{expiry_date}C{int(round(curr_p/50)*50)}"
    trade_sym_pe = asset_data['ticker'] if is_crypto else f"{selected_asset[:5]}{expiry_date}P{int(round(curr_p/50)*50)}"

    btn1, btn2 = st.columns(2)
    with btn1:
        if st.button("🟢 EXECUTE LONG", disabled=not can_ce or st.session_state.trade_active, use_container_width=True):
            st.session_state.trade_active = True
            st.session_state.trade_details = {'Type':'LONG', 'Sym':trade_sym, 'Qty':trade_qty, 'Status':'LIVE' if live_mode else 'PAPER', 'Entry':curr_p, 'Time':datetime.datetime.now().strftime("%H:%M:%S")}
            st.rerun()
    with btn2:
        if st.button("🔴 EXECUTE SHORT", disabled=not can_pe or st.session_state.trade_active, use_container_width=True):
            st.session_state.trade_active = True
            st.session_state.trade_details = {'Type':'SHORT', 'Sym':trade_sym_pe, 'Qty':trade_qty, 'Status':'LIVE' if live_mode else 'PAPER', 'Entry':curr_p, 'Time':datetime.datetime.now().strftime("%H:%M:%S")}
            st.rerun()

# ==============================================================================
# 8. ACTIVE TRADE & LIVE COMMENTARY
# ==============================================================================
if st.session_state.trade_active:
    t = st.session_state.trade_details
    live_points = round(curr_p - t['Entry'], 2) if t['Type'] == 'LONG' else round(t['Entry'] - curr_p, 2)
    
    if live_points >= safe_sl_pts: trail_sl, comm = t['Entry'], "🔥 Risk Free! Trailing SL moved to Cost."
    elif live_points > 0: trail_sl, comm = t['Entry'] - safe_sl_pts if t['Type'] == 'LONG' else t['Entry'] + safe_sl_pts, "📈 Trade is in profit. Hold strong."
    else: trail_sl, comm = t['Entry'] - safe_sl_pts if t['Type'] == 'LONG' else t['Entry'] + safe_sl_pts, "📉 Drawdown active. Maintain discipline, respect SL."

    pcol = "#00ff66" if live_points >= 0 else "#ff3333"
    st.markdown(f"""
    <div class='live-pnl-box'>
        <div style='display:flex; justify-content:space-between; align-items:center;'>
            <div><b>● {t['Status']} {t['Type']}</b> | {t['Sym']} <br> 
            <span style='color:#8b949e;'>Entry: {t['Entry']} | Trail SL: {round(trail_sl,2)}</span><br>
            <span style='color:#ffaa00; font-style:italic;'>🤖 AI Comm: {comm}</span>
            </div>
            <div style='text-align:right;'><span style='color:#8b949e;'>Live Spot PnL</span><br><b style='color:{pcol}; font-size:36px;'>{'+' if live_points>0 else ''}{live_points}</b></div>
        </div>
    </div>""", unsafe_allow_html=True)
    
    if st.button("🛑 SQUARE-OFF TRADE", use_container_width=True):
        st.session_state.trade_history.append({"Date": datetime.datetime.now().strftime("%Y-%m-%d"), "Asset": selected_asset, "Type": t['Type'], "Entry": t['Entry'], "Exit": curr_p, "PnL": live_points, "Mode": t['Status']})
        st.session_state.trade_active = False; st.session_state.trade_details = {}
        st.rerun()

# ==============================================================================
# 9. 1 BIG VISUAL CHART (NO TABS)
# ==============================================================================
st.markdown("### 📊 SMC Master Chart")
if df_1m is not None and not df_1m.empty:
    plot_df = df_1m.tail(150) 
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name='Market'))
    if 'VWAP' in plot_df.columns: fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['VWAP'], name='VWAP', line=dict(color='#00ffff', width=1.5, dash='dash')))
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['EMA_200'], name='200 EMA', line=dict(color='#ffaa00', width=1.5)))
    
    for fvg in fvg_list:
        c = "rgba(255, 51, 51, 0.2)" if fvg['type'] == "BEARISH" else "rgba(0, 255, 102, 0.2)"
        fig.add_hrect(y0=fvg['bot'], y1=fvg['top'], fillcolor=c, opacity=0.4, line_width=0, annotation_text=f"{fvg['type']} FVG")
    
    fig.add_hline(y=pdh, line_dash="dot", line_color="#ff3333", annotation_text="PDH Liquidity")
    fig.add_hline(y=pdl, line_dash="dot", line_color="#00ff66", annotation_text="PDL Liquidity")
    if st.session_state.trade_active: fig.add_hline(y=st.session_state.trade_details['Entry'], line_dash="solid", line_color="#00ffff", annotation_text="ENTRY")
    
    fig.update_layout(template=chart_template, height=550, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(showgrid=False), yaxis=dict(gridcolor=border_col))
    st.plotly_chart(fig, use_container_width=True)

# ==============================================================================
# 10. TRADE BOOK
# ==============================================================================
st.markdown("<hr style='border-color:#2d3748;'>", unsafe_allow_html=True)
if len(st.session_state.trade_history) > 0:
    history_df = pd.DataFrame(st.session_state.trade_history)
    def style_pnl(val): return f"color: {'#00ff66' if val > 0 else '#ff3333' if val < 0 else text_color}; font-weight: bold;"
    st.dataframe(history_df.style.map(style_pnl, subset=['PnL']), use_container_width=True, hide_index=True)
else:
    st.info("No trades executed yet. Data will be saved in app memory.")

if auto_refresh: 
    time.sleep(2)
    st.rerun()

