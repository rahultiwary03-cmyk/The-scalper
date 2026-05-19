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
SHOONYA_PWD = "YOUR_PASSWORD" 
SHOONYA_API_KEY = "YOUR_API_KEY" 
SHOONYA_VC = "FN209492_U" 
SHOONYA_TOTP_SECRET = "YOUR_TOTP_SECRET" 

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

# 🚀 INSTITUTIONAL FEATURE 1: NSE PCR FETCHER (Safe Mode)
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
# 3. CORE CONFIGURATION & THEME
# ==============================================================================
st.set_page_config(page_title="Scalper Pro AI v18.1", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    html, body, [class*="css"]  { font-family: 'Inter', sans-serif; background-color: #0b0e11; color: #e3e9f0; }
    .stApp { background-color: #0b0e11; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    [data-testid="collapsedControl"] { display: none; }
    
    div[data-testid="stMetricValue"] > div { color: #deff9a !important; font-size: 28px !important; }
    div[data-testid="stMetricLabel"] > label { color: #8b949e !important; font-size: 13px !important; font-weight: 700 !important; letter-spacing: 0.5px; }
    
    .stTabs [data-baseweb="tab-list"] { gap: 12px; background-color: #14181f; padding: 10px; border-radius: 12px; border: 1px solid #2d3748; }
    .stTabs [data-baseweb="tab"] { background-color: transparent; border-radius: 8px; padding: 10px 20px; font-size: 14px; font-weight: 600; color: #a0aec0; border: none; transition: all 0.2s ease; }
    .stTabs [aria-selected="true"] { background-color: #deff9a; color: #0b0e11 !important; box-shadow: 0 4px 12px rgba(222, 255, 154, 0.3); }
    .ex-card { background: #14181f; border-radius: 12px; padding: 20px; border: 1px solid #2d3748; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    .inst-box { background: rgba(20, 24, 31, 0.8); padding: 12px; border-radius: 8px; border-left: 4px solid #00ffff; margin-bottom: 10px;}
    .status-badge { padding: 4px 10px; border-radius: 6px; font-weight: 800; font-size: 12px; text-transform: uppercase; }
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
STOCK_HISTORY_FILE = "stock_trade_book.csv"
EXPECTED_COLUMNS = ["Time (IST)", "Asset", "Action", "Spot Entry", "Spot Exit", "Points", "Result"]

def save_trade(trade_data, is_nifty=False):
    filename = NIFTY_HISTORY_FILE if is_nifty else STOCK_HISTORY_FILE
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

def load_history(is_nifty=False):
    filename = NIFTY_HISTORY_FILE if is_nifty else STOCK_HISTORY_FILE
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
# 5. THE HEDGE FUND QUANT ENGINE
# ==============================================================================
def calculate_quant_engine(df, symbol, banknifty_df=None, daily_df=None):
    if st.session_state.shoonya_token and symbol in SH_TOKENS:
        live_ltp = get_shoonya_ltp(SH_TOKENS[symbol], st.session_state.shoonya_token)
        if live_ltp: df.at[df.index[-1], 'Close'] = live_ltp 

    # 🚀 YFINANCE MULTI-INDEX SAFE FLATTENER FOR PDH/PDL
    pdh, pdl = 0, 0
    if daily_df is not None and not daily_df.empty and len(daily_df) > 1:
        pdh = float(daily_df['High'].squeeze().iloc[-2])
        pdl = float(daily_df['Low'].squeeze().iloc[-2])
        
    df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean() 
    df['EMA_105'] = df['Close'].ewm(span=105, adjust=False).mean()
    
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
    is_nifty = "NSEI" in symbol
    
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
                if bn_bullish:
                    score = 100 if rsi >= 55 else 70
                    trend_dir = 1
                    msg = "🚀 Perfect Long (BN Correlated)"
                else: msg = "⚠️ Long Blocked: BankNifty Divergence"
            elif df['EMA_9'].iloc[i] < df['EMA_21'].iloc[i] and curr_c < baseline_val and df['-DI'].iloc[i] > df['+DI'].iloc[i]:
                if bn_bearish:
                    score = 100 if rsi <= 45 else 70
                    trend_dir = -1
                    msg = "📉 Perfect Short (BN Correlated)"
                else: msg = "⚠️ Short Blocked: BankNifty Divergence"
            
            if is_bullish_sweep and rsi < 50: score, trend_dir, msg = 100, 1, "🔥 LIQUIDITY SWEEP: Retailers Trapped (Long)"
            if is_bearish_sweep and rsi > 50: score, trend_dir, msg = 100, -1, "🔥 LIQUIDITY SWEEP: Retailers Trapped (Short)"
                
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
                trade_data = {"Time (IST)": timestamp, "Asset": "NIFTY 50" if is_nifty else symbol.replace(".NS", ""), "Action": active_trade['Type'], "Spot Entry": active_trade['Entry'], "Spot Exit": curr_c, "Points": round(curr_c - active_trade['Entry'] if active_trade['Direction']=='LONG' else active_trade['Entry'] - curr_c, 1), "Result": status_msg}
                save_trade(trade_data, is_nifty=is_nifty)
                active_trade = None 
        else:
            if score == 100 and trend_dir != 0:
                atm_strike = int(round(curr_c / 50) * 50)
                base_sl = max(18.0, round(atr * 1.5, 1)) 
                sl_pts = base_sl if is_nifty else round(curr_c * 0.003, 1)
                tgt_pts = round(sl_pts * 2.0, 1) 
                
                if trend_dir == 1:
                    t_type, direction = f'{atm_strike} CE' if is_nifty else 'BUY', 'LONG'
                    entry, tgt, sl = curr_c, curr_c + tgt_pts, curr_c - sl_pts
                else:
                    t_type, direction = f'{atm_strike} PE' if is_nifty else 'SELL', 'SHORT'
                    entry, tgt, sl = curr_c, curr_c - tgt_pts, curr_c + sl_pts
                
                sig = f'🟢 BUY NIFTY {t_type}' if is_nifty else f'🟢 BUY {symbol.replace(".NS","")}'
                active_trade = {'Type': t_type, 'Signal': sig, 'Entry': round(entry,1), 'Target': round(tgt,1), 'StopLoss': round(sl,1), 'Direction': direction}
                df.at[df.index[i], 'Signal'], df.at[df.index[i], 'Entry'], df.at[df.index[i], 'Target'], df.at[df.index[i], 'StopLoss'] = active_trade['Signal'], active_trade['Entry'], active_trade['Target'], active_trade['StopLoss']

    return df, active_trade

# ==============================================================================
# 6. UI LAYOUT
# ==============================================================================
col_h1, col_h2 = st.columns([2, 1])
with col_h1: 
    if st.session_state.shoonya_token: sh_status = "<span style='color:#00ff66; font-size:14px;'><i class='fa-solid fa-link'></i> Shoonya API Linked</span>"
    else: sh_status = f"<span style='color:#ff3333; font-size:14px;'>🔴 Shoonya API: {st.session_state.get('shoonya_msg', 'Disabled')}</span>"
    st.markdown(f"<h1 style='margin:0; font-weight:800; color:#e3e9f0;'>QUANT<span style='color:#deff9a;'>SCALPER AI</span> v18.1 <br>{sh_status}</h1>", unsafe_allow_html=True)
with col_h2:
    tz_ist = pytz.timezone('Asia/Kolkata'); now = datetime.datetime.now(tz_ist)
    market_status = "CLOSED" if now.hour >= 16 or now.hour < 9 or (now.hour==15 and now.minute>=30) else "LIVE"
    st.markdown(f"<div style='text-align:right; font-weight:700; color:#a0aec0; font-size:16px;'>📅 {now.strftime('%A, %d %b')} | <span style='color:{'#ff3333' if market_status=='CLOSED' else '#00ff66'}'>{now.strftime('%I:%M:%S %p')} IST ({market_status})</span></div>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#2d3748; margin: 10px 0 20px 0;'>", unsafe_allow_html=True)

tab1, tab2, tab3, tab4, tab5 = st.tabs(["⚡ NIFTY HEDGE FUND", "📡 STOCK INT.", "🚀 SWING RADAR", "📈 P&L ANALYTICS", "👨‍💻 CREATOR"])

# ------------------------------------------------------------------------------
# TAB 1: NIFTY OPTIONS (PRO DASHBOARD)
# ------------------------------------------------------------------------------
with tab1:
    try:
        data = yf.download('^NSEI', period='1d', interval='1m', progress=False)
        bn_data = yf.download('^NSEBANK', period='1d', interval='1m', progress=False)
        daily_data = yf.download('^NSEI', period='5d', interval='1d', progress=False)
        pcr_val = get_nse_pcr() 
        
        # 🚀 YFINANCE MULTI-INDEX BUG FIX
        for d in [data, bn_data, daily_data]:
            if not d.empty and isinstance(d.columns, pd.MultiIndex):
                d.columns = d.columns.get_level_values(0)
        
        if not data.empty:
            df, active_trade = calculate_quant_engine(data, '^NSEI', bn_data, daily_data)
            last = df.iloc[-1]; prev = df.iloc[-2]; curr_p = round(float(df['Close'].iloc[-1]), 2); pts = round(curr_p - round(float(df['Open'].iloc[0]), 2), 2)
            adx, atr, vwap, vah, val = float(last['ADX_14']), float(last['ATR_14']), float(last['Baseline']), float(last['VAH']), float(last['VAL'])
            pdh = float(daily_data['High'].squeeze().iloc[-2]) if not daily_data.empty else 0
            pdl = float(daily_data['Low'].squeeze().iloc[-2]) if not daily_data.empty else 0
            
            bn_trend = "BULLISH 🟢" if (float(bn_data['Close'].ewm(span=9).mean().iloc[-1]) > float(bn_data['Close'].ewm(span=21).mean().iloc[-1])) else "BEARISH 🔴"
            
            is_eod_ui = now.hour >= 15 and now.minute >= 15
            ai_msg = str(last['Msg'])
            
            if is_eod_ui: color_cmd, txt_cmd = "#ff3333", "⏱️ EOD Square-Off: Trading Hours Over."
            elif active_trade is not None: color_cmd, txt_cmd = "#ffaa00", f"HOLD : {active_trade['Signal']} ACTIVE."
            elif "LIQUIDITY SWEEP" in ai_msg: color_cmd, txt_cmd = "#00ffff", ai_msg
            elif "Blocked" in ai_msg: color_cmd, txt_cmd = "#ffaa00", ai_msg
            elif adx < 22: color_cmd, txt_cmd = "#a0aec0", "✋ WAIT: CHOP ZONE (ADX < 22). No Trading."
            elif last['AI_Score'] == 100: color_cmd, txt_cmd = "#00ff66", f"🚀 EXECUTE: {last['Signal']} NOW!"
            else: color_cmd, txt_cmd = "#a0aec0", f"WAIT: Scanning Institutional Alignment..."
            
            st.markdown(f"<div style='background:#14181f; padding:15px; border-radius:10px; border-left:5px solid {color_cmd}; color:{color_cmd}; font-weight:700; margin-bottom:15px; font-size:16px;'>{txt_cmd}</div>", unsafe_allow_html=True)

            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            with col_m1: st.metric("NIFTY SPOT", f"₹{curr_p:,}", f"{pts} pts")
            with col_m2: st.metric("BankNifty Alignment", bn_trend)
            with col_m3: st.metric("Options PCR", f"{pcr_val}" if pcr_val else "Fetch Error", "Bullish > 1.0" if pcr_val and pcr_val > 1.0 else "Bearish < 1.0" if pcr_val else "")
            with col_m4: st.metric("Liquidity Zone (VWAP)", f"₹{round(vwap,1)}", f"VAH: {round(vah,1)} | VAL: {round(val,1)}")

            col_met1, col_met2 = st.columns([1, 2])
            with col_met1:
                st.markdown(f"""
                <div class='inst-box'>
                    <div style='color:#a0aec0; font-size:11px; text-transform:uppercase;'>Market Depth Analytics</div>
                    <div style='margin-top:8px;'><b>ADX Strength:</b> <span style='color:{'#00ff66' if adx>=22 else '#ff3333'};'>{round(adx,1)}</span></div>
                    <div><b>Volatility (ATR):</b> <span style='color:#00ffff;'>{round(atr,1)} pts</span></div>
                    <div><b>Prev Day High (PDH):</b> {pdh}</div>
                    <div><b>Prev Day Low (PDL):</b> {pdl}</div>
                </div>
                """, unsafe_allow_html=True)
            
            with col_met2:
                if active_trade is not None and not is_eod_ui:
                    color = "#00ff66" if active_trade['Direction']=='LONG' else "#ff3333"
                    rrr = round((active_trade['Target'] - active_trade['Entry']) / (active_trade['Entry'] - active_trade['StopLoss']),1)
                    if play_sound:= (last['AI_Score']==100 and prev['AI_Score']<100): st.markdown(audio_code, unsafe_allow_html=True)
                    st.markdown(f"""
                    <div class='ex-card'>
                        <div style='display:flex; justify-content:space-between;'>
                            <span class='status-badge' style='background:{'rgba(0,255,102,0.1)' if color=='#00ff66' else 'rgba(255,51,51,0.1)'}; color:{color};'>{active_trade['Direction']} ACTIVE</span>
                            <span style='color:#00ffff; font-size: 12px;'><i class="fa-solid fa-shield"></i> Institutional Dynamic SL</span>
                        </div>
                        <h2 style='margin:10px 0; color:#e3e9f0;'>SPOT ENTRY: ₹{active_trade['Entry']}</h2>
                        <div style='color:#00ff66; font-weight:600; font-size:18px;'>TARGET: ₹{active_trade['Target']}</div>
                        <div style='color:#ff3333; font-weight:600; font-size:18px;'>SL: ₹{active_trade['StopLoss']}</div>
                    </div>
                    """, unsafe_allow_html=True)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df.index, y=df['VAH'], line=dict(width=0), showlegend=False))
            fig.add_trace(go.Scatter(x=df.index, y=df['VAL'], line=dict(width=0), fill='tonexty', fillcolor='rgba(0, 255, 255, 0.05)', name='Value Area'))
            fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Spot Price', line=dict(color='#deff9a', width=2)))
            fig.add_trace(go.Scatter(x=df.index, y=df['Baseline'], name='VWAP POC', line=dict(color='#00ffff', width=1.5, dash='dash')))
            if pdh > 0: fig.add_hline(y=pdh, line_dash="dot", line_color="#ffaa00", annotation_text="PDH")
            if pdl > 0: fig.add_hline(y=pdl, line_dash="dot", line_color="#ffaa00", annotation_text="PDL")
            fig.update_layout(template='plotly_dark', paper_bgcolor='#0b0e11', plot_bgcolor='#0b0e11', height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#2d3748'))
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("<h3 style='color:#deff9a;'>📖 NIFTY OPTIONS LOG (IST)</h3>", unsafe_allow_html=True)
            n_hist = load_history(is_nifty=True)
            if not n_hist.empty: st.dataframe(n_hist[['Time (IST)','Action','Spot Entry','Spot Exit','Points','Result']].style.apply(lambda x: [style_results(val) if x.name == 'Result' else '' for val in x], axis=0), use_container_width=True, hide_index=True)
    except Exception as e: st.error(f"Error Nifty: {e}")

# ------------------------------------------------------------------------------
# TAB 2 & 3
# ------------------------------------------------------------------------------
with tab2: st.write("Intraday Stocks: Tracking disabled in v18 focus mode to save bandwidth for Nifty Option Chain.")
with tab3: st.write("Swing Radar: Move to dedicated file for daily scans.")

# ------------------------------------------------------------------------------
# TAB 4: P&L ANALYTICS
# ------------------------------------------------------------------------------
with tab4:
    st.markdown("<h2 style='color:#deff9a; font-weight:800;'>📊 YOUR TRADING PERFORMANCE AUDIT</h2><hr style='border-color:#2d3748;'>", unsafe_allow_html=True)
    df_n = load_history(is_nifty=True)
    def clean_and_calc(df):
        if df.empty: return df
        if 'Points' in df.columns: df['Points'] = pd.to_numeric(df['Points'], errors='coerce')
        else: df['Points'] = 0.0 
        return df
    all_trades = clean_and_calc(df_n)
    if not all_trades.empty and 'Result' in all_trades.columns:
        total_trades = len(all_trades); wins = len(all_trades[all_trades['Result'].str.contains('TARGET HIT|PROFIT', na=False)])
        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
        total_points = all_trades['Points'].sum() if 'Points' in all_trades.columns else 0
        c_an1, c_an2, c_an3, c_an4 = st.columns(4)
        with c_an1: st.metric("Total Trades Executed", total_trades)
        with c_an2: st.metric("Winning Trades ✅", wins)
        with c_an3: st.metric("Total Win Rate %", f"{round(win_rate, 1)}%")
        with c_an4: st.metric("Total Spot Points P&L", f"{round(total_points, 1)} pts")
    else: st.info("डैशबोर्ड को एक्टिवेट करने के लिए पहले कम से कम एक ट्रेड क्लोज करें।")

with tab5:
    st.markdown(f"<div style='text-align:center;'><h1>[अपना नाम]</h1>Hedge Fund Quant Developer</div>", unsafe_allow_html=True)

time.sleep(8); st.rerun()
