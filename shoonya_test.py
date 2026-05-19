import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import os
import datetime
import pytz
import requests
import json

# ==============================================================================
# 1. 🔑 SHOONYA API CREDENTIALS 
# ==============================================================================
SHOONYA_UID = "FN209492" 
SHOONYA_PWD = "Rahul@1995" 
SHOONYA_API_KEY = "3007acd3cd50a75e4e8eb1bfc0e1459a" 
SHOONYA_VC = "FN209492_U" 
SHOONYA_TOTP_SECRET = "666J4TSFQRM624X75B6WZ32PMUH3477P" 

# ==============================================================================
# 2. SHOONYA LIVE DATA ENGINE
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
        try: data = res.json()
        except ValueError: return None, f"HTTP {res.status_code}"
        if data.get('stat') == 'Ok': return data.get('susertoken'), "Success"
        else: return None, data.get('emsg', 'Unknown Error')
    except Exception as e: return None, str(e)

def get_shoonya_ltp(token, susertoken):
    if not susertoken: return None
    try:
        payload = {"uid": SHOONYA_UID, "exch": "NSE", "token": str(token)}
        headers = {'Authorization': f'Bearer {SHOONYA_UID} {susertoken}'}
        res = requests.post('https://api.shoonya.com/NorenWClientTP/GetQuotes', data='jData=' + json.dumps(payload), headers=headers)
        data = res.json()
        if data.get('stat') == 'Ok': return float(data.get('lp'))
        return None
    except: return None

def get_nse_pcr():
    try:
        headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=3)
        res = session.get("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY", headers=headers, timeout=3)
        data = res.json()
        tot_ce = data['filtered']['CE']['totOI']
        tot_pe = data['filtered']['PE']['totOI']
        return round(tot_pe / tot_ce, 2) if tot_ce > 0 else 1.0
    except:
        return None 

SH_TOKENS = {'^NSEI': '26000', '^NSEBANK': '26009', 'RELIANCE.NS': '2885', 'HDFCBANK.NS': '1333'}

# ==============================================================================
# 3. CORE CONFIGURATION & THEME (v18.2 Dynamic Theme Support)
# ==============================================================================
st.set_page_config(page_title="Scalper Pro AI v18.2", layout="wide", initial_sidebar_state="collapsed")

# 🚀 🚀 DYNAMIC THEME ENGINE 🚀 🚀
# Session state to store theme preference
if 'theme' not in st.session_state:
    st.session_state.theme = 'dark' # Default theme

# Dynamic colors based on theme state
if st.session_state.theme == 'dark':
    primary_color = "#deff9a" # Greenish yellow
    secondary_color = "#00ffff" # Cyan
    bg_color = "#0b0e11" # Black bg
    text_color = "#e3e9f0" # Light text
    card_bg = "#14181f" # Dark card bg
    border_color = "#2d3748"
    metric_label = "#8b949e"
    plot_paper = "#0b0e11"
    plot_bg = "#0b0e11"
else: # LIGHT THEME
    primary_color = "#2e7d32" # Dark Green
    secondary_color = "#0277bd" # Light Blue
    bg_color = "#f0f2f6" # Light Gray bg
    text_color = "#31333F" # Dark text
    card_bg = "#ffffff" # White card bg
    border_color = "#d1d5db"
    metric_label = "#555555"
    plot_paper = "#f0f2f6"
    plot_bg = "#ffffff"

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    html, body, [class*="css"]  {{ font-family: 'Inter', sans-serif; background-color: {bg_color}; color: {text_color}; }}
    .stApp {{ background-color: {bg_color}; }}
    #MainMenu {{visibility: hidden;}} footer {{visibility: hidden;}} header {{visibility: hidden;}}
    [data-testid="collapsedControl"] {{ display: none; }}
    
    /* Dynamic Metric Styles */
    div[data-testid="stMetricValue"] > div {{ color: {primary_color} !important; font-size: 28px !important; }}
    div[data-testid="stMetricLabel"] > label {{ color: {metric_label} !important; font-size: 13px !important; font-weight: 700 !important; letter-spacing: 0.5px; }}
    
    .stTabs [data-baseweb="tab-list"] {{ gap: 12px; background-color: {card_bg}; padding: 10px; border-radius: 12px; border: 1px solid {border_color}; }}
    .stTabs [data-baseweb="tab"] {{ background-color: transparent; border-radius: 8px; padding: 10px 20px; font-size: 14px; font-weight: 600; color: #a0aec0; border: none; transition: all 0.2s ease; }}
    .stTabs [aria-selected="true"] {{ background-color: {primary_color}; color: #0b0e11 !important; box-shadow: 0 4px 12px rgba(222, 255, 154, 0.3); }}
    
    .ex-card {{ background: {card_bg}; border-radius: 12px; padding: 20px; border: 1px solid {border_color}; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
    .inst-box {{ background: rgba(20, 24, 31, 0.05); padding: 12px; border-radius: 8px; border-left: 4px solid {secondary_color}; margin-bottom: 10px; border-top: 1px solid {border_color}; border-right: 1px solid {border_color}; border-bottom: 1px solid {border_color};}}
    .status-badge {{ padding: 4px 10px; border-radius: 6px; font-weight: 800; font-size: 12px; text-transform: uppercase; }}
    
    /* Bright Metric Text always Light for readability on both themes */
    .bright-metric {{ color: #deff9a !important; font-weight: bold;}}
    
    </style>
    """, unsafe_allow_html=True)
audio_code = """<audio id="alert-sound" autoplay><source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-500.wav" type="audio/wav"></audio>"""

if 'shoonya_token' not in st.session_state:
    token, msg = shoonya_login()
    st.session_state.shoonya_token = token
    st.session_state.shoonya_msg = msg

# ==============================================================================
# 4. TRADE HISTORY LOGGERS
# ==============================================================================
NIFTY_HISTORY_FILE = "nifty_trade_book.csv"
EXPECTED_COLUMNS = ["Time (IST)", "Asset", "Action", "Spot Entry", "Spot Exit", "Points", "Result"]

def save_trade(trade_data):
    filename = NIFTY_HISTORY_FILE
    df_new = pd.DataFrame([trade_data])
    if not os.path.exists(filename): df_new.to_csv(filename, index=False)
    else:
        try:
            existing = pd.read_csv(filename)
            if not all(col in existing.columns for col in EXPECTED_COLUMNS): df_new.to_csv(filename, index=False)
            else:
                is_duplicate = ((existing['Time (IST)'] == trade_data['Time (IST)']) & (existing['Asset'] == trade_data['Asset'])).any()
                if not is_duplicate: df_new.to_csv(filename, mode='a', header=False, index=False)
        except: df_new.to_csv(filename, index=False)

def load_history():
    filename = NIFTY_HISTORY_FILE
    if os.path.exists(filename):
        try:
            df = pd.read_csv(filename)
            if df.empty or not all(col in df.columns for col in EXPECTED_COLUMNS): return pd.DataFrame()
            return df.sort_index(ascending=False)
        except: return pd.DataFrame()
    return pd.DataFrame()

def style_results(val):
    if 'TARGET' in str(val) or 'PROFIT' in str(val): return 'background-color: rgba(0, 255, 102, 0.1); color: #00ff66; font-weight: bold;'
    if 'SL HIT' in str(val) or 'LOSS' in str(val) or 'SQUARE-OFF' in str(val): return 'background-color: rgba(255, 51, 51, 0.1); color: #ff3333; font-weight: bold;'
    return ''

# ==============================================================================
# 5. HYBRID QUANT ENGINE (Safe Series Handling from v18.1)
# ==============================================================================
def calculate_quant_engine(df, symbol, banknifty_df=None, daily_df=None):
    if st.session_state.shoonya_token and symbol in SH_TOKENS:
        live_ltp = get_shoonya_ltp(SH_TOKENS[symbol], st.session_state.shoonya_token)
        if live_ltp: df.at[df.index[-1], 'Close'] = live_ltp 

    pdh, pdl = 0, 0
    if daily_df is not None and not daily_df.empty and len(daily_df) > 1:
        pdh = float(daily_df['High'].squeeze().iloc[-2]) # Squeeze to safe float
        pdl = float(daily_df['Low'].squeeze().iloc[-2])
        
    df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean() 
    
    if 'Volume' in df.columns and df['Volume'].sum() > 0:
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        df['Baseline'] = (tp * df['Volume']).cumsum() / (df['Volume'].cumsum() + 1e-10) 
        df['VWAP_Variance'] = (((df['Close'] - df['Baseline'])**2) * df['Volume']).cumsum() / (df['Volume'].cumsum() + 1e-10)
        df['VWAP_Std'] = np.sqrt(df['VWAP_Variance'])
        df['VAH'] = df['Baseline'] + df['VWAP_Std'] 
        df['VAL'] = df['Baseline'] - df['VWAP_Std'] 
    else:
        df['Baseline'] = df['Close'].ewm(span=50, adjust=False).mean() 
        df['VAH'] = df['Baseline'] * 1.001
        df['VAL'] = df['Baseline'] * 0.999
    
    bn_bullish, bn_bearish = True, True
    if banknifty_df is not None and not banknifty_df.empty:
        bn_ema9 = banknifty_df['Close'].ewm(span=9, adjust=False).mean().iloc[-1]
        bn_ema21 = banknifty_df['Close'].ewm(span=21, adjust=False).mean().iloc[-1]
        bn_bullish = float(bn_ema9) > float(bn_ema21)
        bn_bearish = float(bn_ema9) < float(bn_ema21)

    high, low, close = df['High'].squeeze(), df['Low'].squeeze(), df['Close'].squeeze()
    plus_dm = high.diff(); minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0; minus_dm[minus_dm > 0] = 0
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr_smooth = tr.rolling(window=14).mean()
    df['ATR_14'] = atr_smooth 
    
    df['+DI'] = 100 * (plus_dm.rolling(window=14).mean() / (atr_smooth + 1e-10))
    df['-DI'] = 100 * (abs(minus_dm).rolling(window=14).mean() / (atr_smooth + 1e-10))
    df['ADX_14'] = ((abs(df['+DI'] - df['-DI']) / (df['+DI'] + df['-DI'] + 1e-10)) * 100).rolling(window=14).mean()

    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI_14'] = 100 - (100 / (1 + (gain / (loss + 1e-10))))

    df['AI_Score'], df['Signal'], df['Entry'], df['Target'], df['StopLoss'], df['Status'], df['Msg'] = 0, 'WAIT ⏳', 0.0, 0.0, 0.0, "", ""
    active_trade = None
    
    start_idx = 200 if len(df) > 200 else 30 
    for i in range(start_idx, len(df)):
        curr_c = round(float(df['Close'].iloc[i]), 2)
        curr_l = round(float(df['Low'].iloc[i]), 2)
        curr_h = round(float(df['High'].iloc[i]), 2)
        adx = float(df['ADX_14'].iloc[i])
        rsi = float(df['RSI_14'].iloc[i])
        baseline_val = float(df['Baseline'].iloc[i])
        atr = float(df['ATR_14'].iloc[i])
        
        candle_time = df.index[i]
        if candle_time.tz is None: candle_time = candle_time.tz_localize('UTC')
        ist_time = candle_time.tz_convert('Asia/Kolkata')
        timestamp = ist_time.strftime("%d-%b %I:%M %p")
        
        is_trade_allowed_time = (ist_time.hour == 9 and ist_time.minute >= 20) or (ist_time.hour > 9 and ist_time.hour < 15)
        is_eod = (ist_time.hour == 15 and ist_time.minute >= 15) or (ist_time.hour >= 16)
        
        is_bullish_sweep = pdl > 0 and curr_l < pdl and curr_c > pdl
        is_bearish_sweep = pdh > 0 and curr_h > pdh and curr_c < pdh
            
        score, trend_dir, msg = 0, 0, ""
        if is_trade_allowed_time and not is_eod and adx >= 22: 
            if df['EMA_9'].iloc[i] > df['EMA_21'].iloc[i] and curr_c > baseline_val and df['+DI'].iloc[i] > df['-DI'].iloc[i]:
                if bn_bullish: score, trend_dir, msg = 100, 1, "🚀 Perfect Long (BN Correlated)"
                else: msg = "⚠️ Long Blocked: BankNifty Divergence"
            elif df['EMA_9'].iloc[i] < df['EMA_21'].iloc[i] and curr_c < baseline_val and df['-DI'].iloc[i] > df['+DI'].iloc[i]:
                if bn_bearish: score, trend_dir, msg = 100, -1, "📉 Perfect Short (BN Correlated)"
                else: msg = "⚠️ Short Blocked: BankNifty Divergence"
            
            if is_bullish_sweep and rsi < 50: score, trend_dir, msg = 100, 1, "🔥 LIQUIDITY SWEEP (Long)"
            if is_bearish_sweep and rsi > 50: score, trend_dir, msg = 100, -1, "🔥 LIQUIDITY SWEEP (Short)"
                
        df.at[df.index[i], 'AI_Score'] = score
        df.at[df.index[i], 'Msg'] = msg
        
        if active_trade is not None:
            df.at[df.index[i], 'Signal'] = active_trade['Signal']
            df.at[df.index[i], 'Entry'] = active_trade['Entry']
            df.at[df.index[i], 'Target'] = active_trade['Target']
            df.at[df.index[i], 'StopLoss'] = active_trade['StopLoss']
            
            trade_closed, status_msg = False, ""
            if is_eod: status_msg, trade_closed = "⏱️ EOD SQUARE-OFF", True
            elif active_trade['Direction'] == 'LONG':
                if curr_c >= active_trade['Target']: status_msg, trade_closed = "🎯 TARGET HIT (+PROFIT)", True
                elif curr_c <= active_trade['StopLoss']: status_msg, trade_closed = "🛑 SL HIT (-LOSS)", True
            elif active_trade['Direction'] == 'SHORT':
                if curr_c <= active_trade['Target']: status_msg, trade_closed = "🎯 TARGET HIT (+PROFIT)", True
                elif curr_c >= active_trade['StopLoss']: status_msg, trade_closed = "🛑 SL HIT (-LOSS)", True
            
            if trade_closed:
                df.at[df.index[i], 'Status'] = status_msg
                trade_data = {"Time (IST)": timestamp, "Asset": "NIFTY 50", "Action": active_trade['Type'], "Spot Entry": active_trade['Entry'], "Spot Exit": curr_c, "Points": round(curr_c - active_trade['Entry'] if active_trade['Direction']=='LONG' else active_trade['Entry'] - curr_c, 1), "Result": status_msg}
                save_trade(trade_data)
                active_trade = None 
        else:
            if score == 100 and trend_dir != 0:
                atm_strike = int(round(curr_c / 50) * 50)
                sl_pts = max(18.0, round(atr * 1.5, 1)); tgt_pts = round(sl_pts * 2.0, 1) 
                
                if trend_dir == 1:
                    t_type, direction = f'{atm_strike} CE', 'LONG'
                    entry, tgt, sl = curr_c, curr_c + tgt_pts, curr_c - sl_pts
                else:
                    t_type, direction = f'{atm_strike} PE', 'SHORT'
                    entry, tgt, sl = curr_c, curr_c - tgt_pts, curr_c + sl_pts
                
                sig = f'🟢 BUY NIFTY {t_type}'
                active_trade = {'Type': t_type, 'Signal': sig, 'Entry': round(entry,1), 'Target': round(tgt,1), 'StopLoss': round(sl,1), 'Direction': direction}
                df.at[df.index[i], 'Signal'], df.at[df.index[i], 'Entry'], df.at[df.index[i], 'Target'], df.at[df.index[i], 'StopLoss'] = active_trade['Signal'], active_trade['Entry'], active_trade['Target'], active_trade['StopLoss']

    return df, active_trade

# ==============================================================================
# 6. UI LAYOUT (INSTITUTIONAL DASHBOARD + THEME SWITCHER)
# ==============================================================================
# 🚀 🚀 THEME SWITCHER IN THE HEADER 🚀 🚀
header_col1, header_col2, header_theme = st.columns([10, 10, 3])

with header_col1: 
    if st.session_state.shoonya_token: sh_status = f"<span style='color:{primary_color}; font-size:14px;'><i class='fa-solid fa-link'></i> Linked</span>"
    else: sh_status = f"<span style='color:#ff3333; font-size:14px;'>🔴 Disabled</span>"
    st.markdown(f"<h1 style='margin:0; font-weight:800; color:{text_color};'>QUANT<span style='color:{primary_color};'>SCALPER AI</span> v18.2 {sh_status}</h1>", unsafe_allow_html=True)
with header_col2:
    tz_ist = pytz.timezone('Asia/Kolkata'); now = datetime.datetime.now(tz_ist)
    market_status = "CLOSED" if now.hour >= 16 or now.hour < 9 or (now.hour==15 and now.minute>=30) else "LIVE"
    st.markdown(f"<div style='text-align:right; font-weight:700; color:#a0aec0; font-size:16px;'>📅 {now.strftime('%d %b')} | <span style='color:{'#ff3333' if market_status=='CLOSED' else primary_color}'>{now.strftime('%I:%M:%S %p')}</span></div>", unsafe_allow_html=True)

with header_theme:
    # Button to toggle theme
    btn_label = "🔆 Light" if st.session_state.theme == 'dark' else "🌙 Dark"
    if st.button(btn_label, key='theme_btn'):
        st.session_state.theme = 'light' if st.session_state.theme == 'dark' else 'dark'
        st.rerun() # Refresh to apply theme

st.markdown("<hr style='border-color:#2d3748; margin: 10px 0 15px 0;'>", unsafe_allow_html=True)

# 🚀 INSTITUTIONAL METRICS ROW
try:
    data = yf.download('^NSEI', period='1d', interval='1m', progress=False)
    bn_data = yf.download('^NSEBANK', period='1d', interval='1m', progress=False)
    daily_data = yf.download('^NSEI', period='5d', interval='1d', progress=False)
    pcr_val = get_nse_pcr() 
    
    for d in [data, bn_data, daily_data]:
        if not d.empty and isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
    
    if not data.empty:
        df, active_trade = calculate_quant_engine(data, '^NSEI', bn_data, daily_data)
        last = df.iloc[-1]; curr_p = round(float(df['Close'].iloc[-1]), 2); pts = round(curr_p - round(float(df['Open'].iloc[0]), 2), 2)
        adx, atr, vwap, vah, val = float(last['ADX_14']), float(last['ATR_14']), float(last['Baseline']), float(last['VAH']), float(last['VAL'])
        pdh = float(daily_data['High'].squeeze().iloc[-2]) if not daily_data.empty else 0
        pdl = float(daily_data['Low'].squeeze().iloc[-2]) if not daily_data.empty else 0
        bn_trend = "BULLISH 🟢" if (float(bn_data['Close'].ewm(span=9).mean().iloc[-1]) > float(bn_data['Close'].ewm(span=21).mean().iloc[-1])) else "BEARISH 🔴"
        ai_msg = str(last['Msg'])
        
        # Action Center with dynamic colors based on theme
        eod_color = "#ff3333" if st.session_state.theme == 'dark' else "#c62828"
        hold_color = "#ffaa00" if st.session_state.theme == 'dark' else "#ef6c00"
        execute_color = "#00ff66" if st.session_state.theme == 'dark' else "#1b5e20"

        if active_trade is not None: color_cmd, txt_cmd = hold_color, f"HOLD: {active_trade['Signal']} ACTIVE."
        elif "LIQUIDITY SWEEP" in ai_msg: color_cmd, txt_cmd = secondary_color, ai_msg
        elif "Blocked" in ai_msg: color_cmd, txt_cmd = hold_color, ai_msg
        elif adx < 22: color_cmd, txt_cmd = metric_label, "✋ WAIT: CHOP ZONE (ADX < 22)."
        elif last['AI_Score'] == 100: color_cmd, txt_cmd = execute_color, f"🚀 EXECUTE: {last['Signal']} NOW!"
        else: color_cmd, txt_cmd = metric_label, f"WAIT: Scanning Institutional Alignment..."
        
        st.markdown(f"<div style='background:{card_bg}; padding:12px; border-radius:10px; border-left:5px solid {color_cmd}; color:{text_color}; font-weight:700; margin-bottom:12px; border-top: 1px solid {border_color}; border-right: 1px solid {border_color}; border-bottom: 1px solid {border_color}; font-size:15px;'>{txt_cmd}</div>", unsafe_allow_html=True)

        m1, m2, m3, m4 = st.columns(4)
        with m1: st.metric("NIFTY SPOT", f"₹{curr_p:,}", f"{pts} pts")
        with m2: st.metric("BankNifty Alignment", bn_trend)
        with m3: st.metric("Options PCR", f"{pcr_val}" if pcr_val else "Fetch Error")
        with m4: st.metric("Liquidity Zone (VWAP)", f"₹{round(vwap,1)}", f"VAH:{round(vah,1)} | VAL:{round(val,1)}")

        # Dashboard body
        st.markdown("<br>", unsafe_allow_html=True)
        col_met1, col_met2 = st.columns([1, 2])
        
        with col_met1:
            st.markdown(f"""
            <div class='inst-box' style='color:{text_color}'>
                <div style='color:{metric_label}; font-size:11px; text-transform:uppercase;'>Market Depth Analytics</div>
                <div style='margin-top:8px;'><b>ADX Strength:</b> <span style='color:{execute_color};'>{round(adx,1)}</span></div>
                <div><b>Volatility (ATR):</b> <span style='color:{secondary_color};'>{round(atr,1)} pts</span></div>
                <div><b>Prev Day High (PDH):</b> {pdh}</div>
                <div><b>Prev Day Low (PDL):</b> {pdl}</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col_met2:
            if active_trade is not None and market_status == "LIVE":
                color_trade = execute_color if active_trade['Direction']=='LONG' else eod_color
                st.markdown(f"""
                <div class='ex-card'>
                    <div style='display:flex; justify-content:space-between;'>
                        <span class='status-badge' style='background:{card_bg}; border: 2px solid {color_trade}; color:{color_trade};'>{active_trade['Direction']} ACTIVE</span>
                        <span style='color:{secondary_color}; font-size: 12px;'><i class="fa-solid fa-shield"></i> Institutional Dynamic SL</span>
                    </div>
                    <h2 style='margin:10px 0; color:{text_color};'>SPOT ENTRY: ₹{active_trade['Entry']}</h2>
                    <div style='color:{execute_color}; font-weight:600; font-size:18px;'>TARGET: ₹{active_trade['Target']}</div>
                    <div style='color:{eod_color}; font-weight:600; font-size:18px;'>SL: ₹{active_trade['StopLoss']}</div>
                </div>
                """, unsafe_allow_html=True)

        # Chart with Theme support
        fig = go.Figure()
        # Liquidity Fill (Value Area)
        fig.add_trace(go.Scatter(x=df.index, y=df['VAH'], line=dict(width=0), showlegend=False))
        fig.add_trace(go.Scatter(x=df.index, y=df['VAL'], line=dict(width=0), fill='tonexty', fillcolor= f"rgba(0, 255, 255, {'0.05' if st.session_state.theme == 'dark' else '0.1'})", name='Value Area'))
        
        # Spot Price color depends on theme for visibility
        spot_color = '#deff9a' if st.session_state.theme == 'dark' else '#004d40'
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Spot Price', line=dict(color=spot_color, width=2.5)))
        fig.add_trace(go.Scatter(x=df.index, y=df['Baseline'], name='VWAP POC', line=dict(color=secondary_color, width=1.5, dash='dash')))
        
        # PDH / PDL Lines (Yellow is visible on both)
        if pdh > 0: fig.add_hline(y=pdh, line_dash="dot", line_color="#ef6c00", annotation_text="PDH", annotation_font_color=text_color)
        if pdl > 0: fig.add_hline(y=pdl, line_dash="dot", line_color="#ef6c00", annotation_text="PDL", annotation_font_color=text_color)
        
        # Dynamic theme updates for plot layout
        fig.update_layout(template='plotly_dark' if st.session_state.theme == 'dark' else 'plotly_white', paper_bgcolor=plot_paper, plot_bgcolor=plot_bg, height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(showgrid=False, tickfont_color=metric_label), yaxis=dict(gridcolor=border_color, tickfont_color=metric_label), legend_font_color=text_color)
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown(f"<h3 style='color:{primary_color};'>📖 TRADING LOG (IST)</h3>", unsafe_allow_html=True)
        n_hist = load_history()
        if not n_hist.empty: st.dataframe(n_hist[['Time (IST)','Action','Spot Entry','Spot Exit','Points','Result']].style.apply(lambda x: [style_results(val) if x.name == 'Result' else '' for val in x], axis=0), use_container_width=True, hide_index=True)

        # 🚀 🚀 SCALPER CHAT PROMPT SECTION 🚀 🚀
        st.markdown("<br><hr style='border-color:#2d3748;'>", unsafe_allow_html=True)
        st.markdown(f"<h3 style='color:{primary_color};'><i class='fa-solid fa-robot'></i> AI Scalper Analyst</h3>", unsafe_allow_html=True)
        
        if st.button("Generate Current Market Analysis Prompt"):
            # assembly of the advanced context prompt
            current_vwap_pos = "Above" if curr_p > vwap else "Below"
            current_va_pos = "Inside" if val < curr_p < vah else "Outside (Above VAH)" if curr_p > vah else "Outside (Below VAL)"
            
            pcr_status = "Very Bullish" if pcr_val and pcr_val > 1.2 else "Bullish" if pcr_val and pcr_val > 1.0 else "Bearish" if pcr_val and pcr_val < 1.0 else "Very Bearish" if pcr_val and pcr_val < 0.8 else "Unknown"
            
            liquidity_context = f"Price is {current_va_pos} the Institutional Value Area (VAH: {round(vah,1)}, VAL: {round(val,1)})."
            if pdh > 0 and pdl > 0:
                liquidity_context += f" Previous Day High: {pdh}, Previous Day Low: {pdl}."

            # THE FINAL MASTER CHAT PROMPT
            scalper_chat_prompt = f"""
Act as an Institutional Option Scalper and Quant Analyst. Analyze the current market context based Strictly on this data for Nifty 50:

**Market Snapshot:**
- Nifty Spot: ₹{curr_p} ({pts} pts today)
- Volatility (ATR 1m): {round(atr,1)} pts (Dynamic Risk)
- ADX Trend Strength: {round(adx,1)} ({'Strong Trend' if adx>=25 else 'Chop Zone'})

**Institutional Context:**
- Option Chain PCR: {pcr_val} ({pcr_status})
- BankNifty Alignment: {bn_trend}
- Price vs VWAP POC: {current_vwap_pos}

**Liquidity & Traps:**
- Value Area Status: {current_va_pos}
- PDH/PDL: {pdh} / {pdl}
- Current AI Signal: {ai_msg}

Given this context, tell me:
1. Is it safe to execute a scalp right now? Why or why not based on 'Smart Money' alignment?
2. If I had to take a trade within the next 5 minutes, would the probability favor buying { एटीएम_स्ट्राइक = एटीएम_स्ट्राइक if '에टीएम_스트라이크' in locals() else ATM_Strike } CALL (CE) or PUT (PE)? State the primary institutional reason (e.g., 'BankNifty Divergence is too risky' or 'Liquidity Sweep confirmed by PCR').
3. Based on the current ATR of {round(atr,1)}, what should be my maximum Spot Stop-Loss in points for this scalp to avoid being stopped out by noise?

Be extremely concise and professional.
"""
            st.text_area("Copy this prompt into your Scalper Chat:", value=scalper_chat_prompt, height=450)

except Exception as e: st.error(f"Error Nifty: {e}")

time.sleep(8); st.rerun()
