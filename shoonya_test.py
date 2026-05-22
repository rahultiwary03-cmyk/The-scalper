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
import concurrent.futures  # 🚀 MULTITHREADING ENGINE ADDED

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
# 3. CORE CONFIGURATION & THEME 
# ==============================================================================
st.set_page_config(page_title="Scalper Pro AI v18.8", layout="wide", initial_sidebar_state="collapsed")

if 'theme' not in st.session_state:
    st.session_state.theme = 'dark' 

if st.session_state.theme == 'dark':
    primary_color = "#deff9a"; secondary_color = "#00ffff"; bg_color = "#0b0e11"; text_color = "#e3e9f0"; card_bg = "#14181f"; border_color = "#2d3748"; metric_label = "#8b949e"; plot_paper = "#0b0e11"; plot_bg = "#0b0e11"
else: 
    primary_color = "#2e7d32"; secondary_color = "#0277bd"; bg_color = "#f0f2f6"; text_color = "#31333F"; card_bg = "#ffffff"; border_color = "#d1d5db"; metric_label = "#555555"; plot_paper = "#f0f2f6"; plot_bg = "#ffffff"

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    html, body, [class*="css"]  {{ font-family: 'Inter', sans-serif; background-color: {bg_color}; color: {text_color}; }}
    .stApp {{ background-color: {bg_color}; }}
    #MainMenu {{visibility: hidden;}} footer {{visibility: hidden;}} header {{visibility: hidden;}}
    [data-testid="collapsedControl"] {{ display: none; }}
    div[data-testid="stMetricValue"] > div {{ color: {primary_color} !important; font-size: 28px !important; }}
    div[data-testid="stMetricLabel"] > label {{ color: {metric_label} !important; font-size: 13px !important; font-weight: 700 !important; letter-spacing: 0.5px; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 12px; background-color: {card_bg}; padding: 10px; border-radius: 12px; border: 1px solid {border_color}; }}
    .stTabs [data-baseweb="tab"] {{ background-color: transparent; border-radius: 8px; padding: 10px 20px; font-size: 14px; font-weight: 600; color: #a0aec0; border: none; transition: all 0.2s ease; }}
    .stTabs [aria-selected="true"] {{ background-color: {primary_color}; color: #0b0e11 !important; box-shadow: 0 4px 12px rgba(222, 255, 154, 0.3); }}
    .ex-card {{ background: {card_bg}; border-radius: 12px; padding: 20px; border: 1px solid {border_color}; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
    .inst-box {{ background: rgba(20, 24, 31, 0.05); padding: 12px; border-radius: 8px; border-left: 4px solid {secondary_color}; margin-bottom: 10px; border-top: 1px solid {border_color}; border-right: 1px solid {border_color}; border-bottom: 1px solid {border_color};}}
    .status-badge {{ padding: 4px 10px; border-radius: 6px; font-weight: 800; font-size: 12px; text-transform: uppercase; }}
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
            df = pd.read_csv(filename); return df.sort_index(ascending=False) if not df.empty else pd.DataFrame()
        except: return pd.DataFrame()
    return pd.DataFrame()

def style_results(val):
    if 'TARGET' in str(val) or 'PROFIT' in str(val): return 'background-color: rgba(0, 255, 102, 0.1); color: #00ff66; font-weight: bold;'
    if 'SL HIT' in str(val) or 'LOSS' in str(val) or 'SQUARE-OFF' in str(val): return 'background-color: rgba(255, 51, 51, 0.1); color: #ff3333; font-weight: bold;'
    return ''

def safe_series(d, col):
    s = d[col]
    if isinstance(s, pd.DataFrame): return s.iloc[:, 0]
    return s

# 🚀 SMART CACHING: Daily data only fetched once every 30 minutes
@st.cache_data(ttl=1800)
def fetch_daily_data_cached():
    return yf.download('^NSEI', period='5d', interval='1d', progress=False)

# ==============================================================================
# 5. THE ANTI-REPAINT SMC ENGINE
# ==============================================================================
def calculate_quant_engine(df, symbol, banknifty_df=None, daily_df=None):
    if st.session_state.shoonya_token and symbol in SH_TOKENS:
        live_ltp = get_shoonya_ltp(SH_TOKENS[symbol], st.session_state.shoonya_token)
        if live_ltp: df.at[df.index[-1], 'Close'] = live_ltp 

    pdh, pdl = 0, 0
    if daily_df is not None and len(daily_df) > 1:
        try:
            pdh = float(safe_series(daily_df, 'High').iloc[-2])
            pdl = float(safe_series(daily_df, 'Low').iloc[-2])
        except: pass
        
    if 'Volume' in df.columns and df['Volume'].sum() > 0:
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        df['Baseline'] = (tp * df['Volume']).cumsum() / (df['Volume'].cumsum() + 1e-10) 
        df['VWAP_Variance'] = (((df['Close'] - df['Baseline'])**2) * df['Volume']).cumsum() / (df['Volume'].cumsum() + 1e-10)
        df['VWAP_Std'] = np.sqrt(df['VWAP_Variance'])
        df['VAH'] = df['Baseline'] + df['VWAP_Std'] 
        df['VAL'] = df['Baseline'] - df['VWAP_Std'] 
    else:
        df['Baseline'] = df['Close'].ewm(span=50, adjust=False).mean() 
        df['VAH'] = df['Baseline'] * 1.001; df['VAL'] = df['Baseline'] * 0.999
    
    bn_bearish, bn_bullish = False, False
    if banknifty_df is not None and not banknifty_df.empty:
        bn_ltp = float(safe_series(banknifty_df, 'Close').iloc[-1])
        bn_baseline = float(banknifty_df['Close'].ewm(span=50, adjust=False).mean().iloc[-1])
        bn_bearish = bn_ltp < bn_baseline
        bn_bullish = bn_ltp > bn_baseline

    high, low, close = safe_series(df, 'High'), safe_series(df, 'Low'), safe_series(df, 'Close')
    
    plus_dm = high.diff(); minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0; minus_dm[minus_dm > 0] = 0
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr_smooth = tr.rolling(window=14).mean(); df['ATR_14'] = atr_smooth 
    df['+DI'] = 100 * (plus_dm.rolling(window=14).mean() / (atr_smooth + 1e-10))
    df['-DI'] = 100 * (abs(minus_dm).rolling(window=14).mean() / (atr_smooth + 1e-10))
    df['ADX_14'] = ((abs(df['+DI'] - df['-DI']) / (df['+DI'] + df['-DI'] + 1e-10)) * 100).rolling(window=14).mean()

    df['AI_Score'], df['Signal'], df['Entry'], df['Target'], df['StopLoss'], df['Status'], df['Msg'] = 0, 'WAIT ⏳', 0.0, 0.0, 0.0, "", "WAIT: Scanning SMC Setup..."
    active_trade = None
    
    start_idx = 30 
    for i in range(start_idx, len(df)):
        prev_c = float(df['Close'].iloc[i-1]); prev_h = float(df['High'].iloc[i-1]); prev_l = float(df['Low'].iloc[i-1])
        prev_baseline = float(df['Baseline'].iloc[i-1]); prev_adx = float(df['ADX_14'].iloc[i-1]); prev_atr = float(df['ATR_14'].iloc[i-1])

        curr_h = float(df['High'].iloc[i]); curr_l = float(df['Low'].iloc[i]); curr_o = float(df['Open'].iloc[i]); curr_c = float(df['Close'].iloc[i])
        
        ist_time = df.index[i].tz_convert('Asia/Kolkata')
        is_trade_window = (ist_time.hour == 9 and ist_time.minute >= 20) or (ist_time.hour > 9 and ist_time.hour < 15)
        is_eod = (ist_time.hour == 15 and ist_time.minute >= 15)
        
        score, trend_dir, msg, entry_price = 0, 0, "✋ WAIT: Setup not aligned.", 0.0
        
        if is_trade_window and not is_eod and prev_adx >= 22:
            if prev_c < prev_baseline and bn_bearish:
                if curr_l < prev_l: 
                    score, trend_dir, entry_price, msg = 100, -1, min(prev_l, curr_o), "📉 EXECUTE PE: Breakdown Locked."
                else: msg = "⚠️ SMC Aligned (Below VWAP), Waiting for Low Breakdown (PE)."
            elif prev_c > prev_baseline and bn_bullish:
                if curr_h > prev_h: 
                    score, trend_dir, entry_price, msg = 100, 1, max(prev_h, curr_o), "🚀 EXECUTE CE: Breakout Locked."
                else: msg = "⚠️ SMC Aligned (Above VWAP), Waiting for High Breakout (CE)."
        
        if is_eod: msg = "⏱️ EOD: Trading window closed."
        df.at[df.index[i], 'Msg'] = msg; df.at[df.index[i], 'AI_Score'] = score
        
        if active_trade is not None:
            trade_closed, status_msg, exit_price = False, "", 0.0
            if is_eod: status_msg, trade_closed, exit_price = "⏱️ EOD SQUARE-OFF", True, curr_c
            elif active_trade['Direction'] == 'LONG':
                if curr_h >= active_trade['Target']: status_msg, trade_closed, exit_price = "🎯 TARGET HIT (+PROFIT)", True, active_trade['Target']
                elif curr_l <= active_trade['StopLoss']: status_msg, trade_closed, exit_price = "🛑 SL HIT (-LOSS)", True, active_trade['StopLoss']
            elif active_trade['Direction'] == 'SHORT':
                if curr_l <= active_trade['Target']: status_msg, trade_closed, exit_price = "🎯 TARGET HIT (+PROFIT)", True, active_trade['Target']
                elif curr_h >= active_trade['StopLoss']: status_msg, trade_closed, exit_price = "🛑 SL HIT (-LOSS)", True, active_trade['StopLoss']
            
            if trade_closed:
                trade_pts = round(exit_price - active_trade['Entry'] if active_trade['Direction']=='LONG' else active_trade['Entry'] - exit_price, 1)
                trade_data = {"Time (IST)": ist_time.strftime("%d-%b %I:%M %p"), "Asset": "NIFTY 50", "Action": active_trade['Type'], "Spot Entry": active_trade['Entry'], "Spot Exit": exit_price, "Points": trade_pts, "Result": status_msg}
                save_trade(trade_data); active_trade = None 
        else:
            if score == 100 and trend_dir != 0 and is_trade_window:
                atm_strike = int(round(entry_price / 50) * 50)
                sl_pts = max(18.0, round(prev_atr * 1.5, 1)); tgt_pts = round(sl_pts * 2.0, 1)
                if trend_dir == 1: tgt, sl, direction, t_type = entry_price + tgt_pts, entry_price - sl_pts, 'LONG', f'{atm_strike} CE'
                else: tgt, sl, direction, t_type = entry_price - tgt_pts, entry_price + sl_pts, 'SHORT', f'{atm_strike} PE'
                active_trade = {'Type': t_type, 'Signal': f'🟢 BUY NIFTY {t_type}', 'Entry': round(entry_price,1), 'Target': round(tgt,1), 'StopLoss': round(sl,1), 'Direction': direction}
                df.at[df.index[i], 'Signal'] = active_trade['Signal']
    return df, active_trade

# ==============================================================================
# 6. UI LAYOUT 
# ==============================================================================
header_col1, header_col2, header_theme = st.columns([10, 10, 3])
with header_col1: 
    if st.session_state.shoonya_token: sh_status = f"<span style='color:{primary_color}; font-size:14px;'><i class='fa-solid fa-link'></i> Shoonya API Linked</span>"
    else: sh_status = f"<span style='color:#ff3333; font-size:14px;'>🔴 Shoonya API: {st.session_state.get('shoonya_msg', 'Disabled')}</span>"
    st.markdown(f"<h1 style='margin:0; font-weight:800; color:{text_color};'>QUANT<span style='color:{primary_color};'>SCALPER AI</span> v18.8 <span style='font-size:12px; color:#00ffff;'>⚡TURBO</span> <br>{sh_status}</h1>", unsafe_allow_html=True)
with header_col2:
    tz_ist = pytz.timezone('Asia/Kolkata'); now = datetime.datetime.now(tz_ist)
    market_status = "CLOSED" if now.hour >= 16 or now.hour < 9 or (now.hour==15 and now.minute>=30) else "LIVE"
    st.markdown(f"<div style='text-align:right; font-weight:700; color:#a0aec0; font-size:16px;'>📅 {now.strftime('%d %b')} | <span style='color:{'#ff3333' if market_status=='CLOSED' else primary_color}'>{now.strftime('%I:%M:%S %p')} IST</span></div>", unsafe_allow_html=True)
with header_theme:
    btn_label = "🔆 Light" if st.session_state.theme == 'dark' else "🌙 Dark"
    if st.button(btn_label, key='theme_btn'): st.session_state.theme = 'light' if st.session_state.theme == 'dark' else 'dark'; st.rerun() 
st.markdown("<hr style='border-color:#2d3748; margin: 10px 0 15px 0;'>", unsafe_allow_html=True)

try:
    # 🚀 TURBO MULTITHREADING FETCH
    def fetch_nifty(): return yf.download('^NSEI', period='1d', interval='1m', progress=False)
    def fetch_bn(): return yf.download('^NSEBANK', period='1d', interval='1m', progress=False)
    
    daily_data = fetch_daily_data_cached() # Hits cache, 0 latency
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        f_nifty = executor.submit(fetch_nifty)
        f_bn = executor.submit(fetch_bn)
        f_pcr = executor.submit(get_nse_pcr)
        
        data = f_nifty.result()
        bn_data = f_bn.result()
        pcr_val = f_pcr.result()
    
    for d in [data, bn_data, daily_data]:
        if not d.empty:
            if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
            d.index = d.index.tz_convert('Asia/Kolkata') if d.index.tz is not None else d.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
    
    if not data.empty:
        df, active_trade = calculate_quant_engine(data, '^NSEI', bn_data, daily_data)
        last = df.iloc[-1]; curr_p = round(float(df['Close'].iloc[-1]), 2); pts = round(curr_p - round(float(df['Open'].iloc[0]), 2), 2)
        
        adx = float(last['ADX_14']) if pd.notna(last['ADX_14']) else 0.0; atr = float(last['ATR_14']) if pd.notna(last['ATR_14']) else 0.0
        vwap = float(last['Baseline']) if pd.notna(last['Baseline']) else curr_p;vah = float(last['VAH']) if pd.notna(last['VAH']) else curr_p;val = float(last['VAL']) if pd.notna(last['VAL']) else curr_p
        pdh = float(safe_series(daily_data, 'High').iloc[-2]) if not daily_data.empty and len(daily_data) > 1 else 0.0;pdl = float(safe_series(daily_data, 'Low').iloc[-2]) if not daily_data.empty and len(daily_data) > 1 else 0.0
        ai_msg = str(last['Msg']); atm_strike = int(round(curr_p / 50) * 50)
        
        bn_trend = "BULLISH 🟢" if (float(bn_data['Close'].ewm(span=50).mean().iloc[-1]) < float(safe_series(bn_data, 'Close').iloc[-1])) else "BEARISH 🔴"
        eod_color = "#ff3333" if st.session_state.theme == 'dark' else "#c62828";hold_color = "#ffaa00" if st.session_state.theme == 'dark' else "#ef6c00";execute_color = "#00ff66" if st.session_state.theme == 'dark' else "#1b5e20"

        if active_trade is not None: color_cmd, txt_cmd = hold_color, f"HOLD: {active_trade['Signal']} ACTIVE."
        elif last['AI_Score'] == 100: color_cmd, txt_cmd = execute_color, f"🚀 EXECUTE: {last['Signal']} NOW!"
        elif market_status == "CLOSED": color_cmd, txt_cmd = metric_label, "MARKET CLOSED: AI Standby Mode."
        else: color_cmd, txt_cmd = metric_label, ai_msg
        
        st.markdown(f"<div style='background:{card_bg}; padding:12px; border-radius:10px; border-left:5px solid {color_cmd}; color:{text_color}; font-weight:700; margin-bottom:12px; border-top: 1px solid {border_color}; border-right: 1px solid {border_color}; border-bottom: 1px solid {border_color}; font-size:15px;'>{txt_cmd}</div>", unsafe_allow_html=True)

        m1, m2, m3, m4 = st.columns(4)
        with m1: st.metric("NIFTY SPOT", f"₹{curr_p:,}", f"{pts} pts")
        with m2: st.metric("BankNifty Alignment", bn_trend)
        with m3: st.metric("Options PCR", f"{pcr_val}" if pcr_val else "Error")
        with m4: st.metric("Institution Zone (POC)", f"₹{round(vwap,1)}")

        st.markdown("<br>", unsafe_allow_html=True); col_met1, col_met2 = st.columns([1, 2])
        
        with col_met1:
            st.markdown(f"""
            <div class='inst-box' style='color:{text_color};'>
                <div style='color:{metric_label}; font-size:11px; text-transform:uppercase;'>Institutional Depth Analytics</div>
                <div style='margin-top:8px;'><b>Trend Power (ADX):</b> <span style='color:{execute_color};'>{round(adx,1)}</span></div>
                <div><b>Dynamic Risk (ATR):</b> <span style='color:#00ffff;'>{round(atr,1)} pts</span></div>
                <div><b>Value Area High (VAH):</b> {round(vah,1)}</div>
                <div><b>Value Area Low (VAL):</b> {round(val,1)}</div>
                <div><b>Prev Day Low (PDL):</b> {pdl}</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col_met2:
            if active_trade is not None and market_status == "LIVE":
                color_trade = execute_color if active_trade['Direction']=='LONG' else eod_color
                st.markdown(f"""
                <div class='ex-card' style='border: 2px solid {color_trade};'>
                    <div style='display:flex; justify-content:space-between;'>
                        <span class='status-badge' style='background:{bg_color}; border: 1px solid {color_trade}; color:{color_trade};'>{active_trade['Direction']} ACTIVE</span>
                        <span style='color:#00ffff; font-size: 12px;'><i class="fa-solid fa-shield"></i> ATR Dynamic SL</span>
                    </div>
                    <h2 style='margin:10px 0; color:{text_color};'>SPOT ENTRY: ₹{active_trade['Entry']}</h2>
                    <div style='color:{execute_color}; font-weight:700; font-size:20px;'>TARGET: ₹{active_trade['Target']} (1:2 RR)</div>
                    <div style='color:{eod_color}; font-weight:700; font-size:20px;'>STOP-LOSS: ₹{active_trade['StopLoss']}</div>
                </div>
                """, unsafe_allow_html=True)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df['VAH'], line=dict(width=0), showlegend=False))
        fig.add_trace(go.Scatter(x=df.index, y=df['VAL'], line=dict(width=0), fill='tonexty', fillcolor= f"rgba(0, 255, 255, {'0.05' if st.session_state.theme == 'dark' else '0.1'})", name='Institutional Value Area'))
        spot_color = '#deff9a' if st.session_state.theme == 'dark' else '#004d40'
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Spot Price', line=dict(color=spot_color, width=2.5)))
        fig.add_trace(go.Scatter(x=df.index, y=df['Baseline'], name='POC (VWAP)', line=dict(color=secondary_color, width=1.5, dash='dash')))
        if pdh > 0: fig.add_hline(y=pdh, line_dash="dot", line_color="#ef6c00", annotation_text="Prev Day High", annotation_font_color=text_color)
        if pdl > 0: fig.add_hline(y=pdl, line_dash="dot", line_color="#ef6c00", annotation_text="Prev Day Low", annotation_font_color=text_color)
        fig.update_layout(template='plotly_dark' if st.session_state.theme == 'dark' else 'plotly_white', paper_bgcolor=plot_paper, plot_bgcolor=plot_bg, height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(showgrid=False, tickfont_color=metric_label), yaxis=dict(gridcolor=border_color, tickfont_color=metric_label), legend_font_color=text_color)
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("<hr style='border-color:#2d3748;'>", unsafe_allow_html=True); tab_l1, tab_l2 = st.tabs(["📖 TRADING LOG (IST)", "👨‍💻 SMC PRO PROMPT GENERATOR"])
        
        with tab_l1:
            n_hist = load_history()
            if not n_hist.empty: 
                needed = n_hist[['Time (IST)','Asset','Action','Spot Entry','Spot Exit','Points','Result']]
                st.dataframe(needed.style.apply(lambda x: [style_results(val) if x.name == 'Result' else '' for val in x], axis=0), use_container_width=True, hide_index=True)
            else: st.info("No trades executed yet.")
        
        with tab_l2:
            st.markdown(f"<h3 style='color:{primary_color};'><i class='fa-solid fa-robot'></i> Generate Institutional SMC Chat Prompt</h3>", unsafe_allow_html=True)
            if st.button("Generate Master Market Analysis Prompt", key='gen_prompt_btn'):
                current_vwap_pos = "Above" if curr_p > vwap else "Below"; current_va_pos = "Inside" if val < curr_p < vah else "Outside"
                pcr_status = "Unknown" if not pcr_val else ("Very Bullish" if pcr_val > 1.2 else "Bullish" if pcr_val > 1.0 else "Bearish" if pcr_val < 1.0 else "Very Bearish")
                
                scalper_chat_prompt = f"""You are an Institutional Quant Trader, Smart Money Concept (SMC) Analyst, and High-Frequency Option Scalper specializing in NIFTY 50.

Analyze the live market strictly using the real-time data provided below. Think like a hedge fund trader, not a retail trader.

🔥 LIVE MARKET DATA
- Nifty Spot Price: ₹{curr_p}
- Day Change: {pts} pts
- Current ATR (1m): {round(atr,1)}
- ADX Trend Strength: {round(adx,1)}
- VWAP / POC: ₹{round(vwap,1)}
- Value Area Low (VAL): ₹{round(val,1)}
- Previous Day Low (PDL): {pdl}
- Options PCR: {pcr_val} ({pcr_status})
- BankNifty Alignment: {bn_trend}
- Current AI Context: {ai_msg}
- Price vs VWAP: {current_vwap_pos}
- Value Area Position: {current_va_pos}

📊 INSTITUTIONAL SMC ANALYSIS REQUIRED
1. MARKET STRUCTURE: Determine context (Trending Bearish, Reversal, Liquidity trap, or Range-bound).
2. SMART MONEY ANALYSIS: Are institutions likely accumulating CALLS or PUTS? Identify key liquidity sweep levels.
3. OPTIONS FLOW ANALYSIS: Tell which side has higher probability (CE buyers or PE buyers) based on the full confluence of BN trend, VWAP, and ADX power.
4. EXECUTION DECISION: Give ONE clear action: BUY CE, BUY PE, or NO TRADE.
5. IF TRADE IS GIVEN: Provide ATM Strike {atm_strike}, Spot entry, Spot target (Strict 1:2 R/R), Spot stop-loss (1.5x ATR).

⚠️ STRICT RULES: Be concise. No education. Speak like a prop-desk scalper. Prioritize capital protection. Output in this format:
✅ Market Bias: 
✅ Institutional Direction: 
✅ Best Trade: BUY {atm_strike} [CE/PE] at [Price]
✅ Confidence Score: [X%/100%]
✅ Trap Warning: 
✅ Final Verdict:
"""
                st.text_area("Copy this prompt into your Scalper Chat (ChatGPT/Claude):", value=scalper_chat_prompt, height=450)

except Exception as e: st.error(f"Error Nifty: {e}")

time.sleep(8); st.rerun()
