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
import concurrent.futures 

# ==============================================================================
# 1. 🔑 SHOONYA API CREDENTIALS 
# ==============================================================================
SHOONYA_UID = "FN209492" 
SHOONYA_PWD = "Rahul@1995" 
SHOONYA_API_KEY = "7cf713be1c14cb0020e7012d412c5f05" 
SHOONYA_VC = "FN209492_U" 
SHOONYA_TOTP_SECRET = "7S4S46UM2426XWQZ5726OO6QIXD6LYNT" 

LIVE_TRADING = False  # ⚠️ CHANGE TO TRUE TO FIRE REAL ORDERS

# ==============================================================================
# 2. SHOONYA LIVE DATA & EXECUTION ENGINE
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
        
        # 🟢 Added Headers to bypass firewall / bot protection
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        
        res = requests.post(
            'https://api.shoonya.com/NorenWClientTP/QuickAuth', 
            data='jData=' + json.dumps(payload), 
            headers=headers,
            timeout=5
        )
        
        # 🟢 Safe parsing logic so it never crashes with "line 1 column 1"
        if not res.text.strip():
            return None, "Empty response from Shoonya server."
            
        try:
            data = res.json()
        except ValueError:
            return None, f"Firewall Blocked (HTTP {res.status_code}). Check Credentials/IP."
            
        if data.get('stat') == 'Ok': 
            return data.get('susertoken'), "Success"
        else: 
            return None, data.get('emsg', 'Unknown Error')
            
    except Exception as e: 
        return None, str(e)

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

def place_shoonya_order(susertoken, symbol, qty, buy_or_sell):
    """Fires actual orders to Shoonya."""
    if not susertoken or not LIVE_TRADING: return "PAPER TRADE LOGGED"
    try:
        payload = {
            "uid": SHOONYA_UID, "actid": SHOONYA_UID, "exch": "NFO", 
            "tsym": symbol, "qty": str(qty), "prc": "0", "prd": "M", 
            "trantype": buy_or_sell, "prctyp": "MKT", "ret": "DAY"
        }
        headers = {'Authorization': f'Bearer {SHOONYA_UID} {susertoken}'}
        res = requests.post('https://api.shoonya.com/NorenWClientTP/PlaceOrder', data='jData=' + json.dumps(payload), headers=headers)
        return res.json().get('norenordno', "Order Failed")
    except Exception as e: return f"API Error: {str(e)}"

def get_nse_pcr():
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=3)
        res = session.get("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY", headers=headers, timeout=3)
        data = res.json()
        tot_ce = data['filtered']['CE']['totOI']
        tot_pe = data['filtered']['PE']['totOI']
        return round(tot_pe / tot_ce, 2) if tot_ce > 0 else 1.0
    except: return None 

SH_TOKENS = {'^NSEI': '26000', '^NSEBANK': '26009'}

# ==============================================================================
# 3. CORE CONFIGURATION & THEME 
# ==============================================================================
st.set_page_config(page_title="Scalper Pro AI v19.0", layout="wide", initial_sidebar_state="collapsed")

if 'theme' not in st.session_state: st.session_state.theme = 'dark' 

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
    div[data-testid="stMetricValue"] > div {{ color: {primary_color} !important; font-size: 24px !important; font-weight: 800; }}
    div[data-testid="stMetricLabel"] > label {{ color: {metric_label} !important; font-size: 13px !important; font-weight: 700 !important; letter-spacing: 0.5px; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 12px; background-color: {card_bg}; padding: 10px; border-radius: 12px; border: 1px solid {border_color}; }}
    .stTabs [data-baseweb="tab"] {{ background-color: transparent; border-radius: 8px; padding: 10px 20px; font-size: 14px; font-weight: 600; color: #a0aec0; border: none; }}
    .stTabs [aria-selected="true"] {{ background-color: {primary_color}; color: #0b0e11 !important; box-shadow: 0 4px 12px rgba(222, 255, 154, 0.3); }}
    .ex-card {{ background: {card_bg}; border-radius: 12px; padding: 20px; border: 1px solid {border_color}; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
    .inst-box {{ background: rgba(20, 24, 31, 0.05); padding: 12px; border-radius: 8px; border-left: 4px solid {secondary_color}; margin-bottom: 10px; border: 1px solid {border_color};}}
    .status-badge {{ padding: 4px 10px; border-radius: 6px; font-weight: 800; font-size: 12px; text-transform: uppercase; }}
    </style>
    """, unsafe_allow_html=True)

if 'shoonya_token' not in st.session_state:
    token, msg = shoonya_login()
    st.session_state.shoonya_token = token
    st.session_state.shoonya_msg = msg

# ==============================================================================
# 4. TRADE LOGGERS
# ==============================================================================
NIFTY_HISTORY_FILE = "nifty_trade_book.csv"
EXPECTED_COLUMNS = ["Time (IST)", "Asset", "Action", "Spot Entry", "Spot Exit", "Points", "Result", "Order ID"]

def save_trade(trade_data):
    df_new = pd.DataFrame([trade_data])
    if not os.path.exists(NIFTY_HISTORY_FILE): df_new.to_csv(NIFTY_HISTORY_FILE, index=False)
    else: df_new.to_csv(NIFTY_HISTORY_FILE, mode='a', header=False, index=False)

def load_history():
    if os.path.exists(NIFTY_HISTORY_FILE):
        try: return pd.read_csv(NIFTY_HISTORY_FILE).sort_index(ascending=False)
        except: return pd.DataFrame()
    return pd.DataFrame()

def style_results(val):
    if 'TARGET' in str(val) or 'PROFIT' in str(val): return 'background-color: rgba(0, 255, 102, 0.1); color: #00ff66; font-weight: bold;'
    if 'SL HIT' in str(val) or 'LOSS' in str(val): return 'background-color: rgba(255, 51, 51, 0.1); color: #ff3333; font-weight: bold;'
    if 'TSL HIT' in str(val) or 'BREAKEVEN' in str(val): return 'background-color: rgba(255, 170, 0, 0.1); color: #ffaa00; font-weight: bold;'
    return ''

@st.cache_data(ttl=1800)
def fetch_daily_data_cached():
    return yf.download('^NSEI', period='5d', interval='1d', progress=False)

# ==============================================================================
# 5. THE ANTI-REPAINT SMC ENGINE WITH RSI & TSL
# ==============================================================================
def calculate_quant_engine(df, symbol, banknifty_df=None, daily_df=None):
    if st.session_state.shoonya_token and symbol in SH_TOKENS:
        live_ltp = get_shoonya_ltp(SH_TOKENS[symbol], st.session_state.shoonya_token)
        if live_ltp: df.at[df.index[-1], 'Close'] = live_ltp 

    # RSI Calculation
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['RSI'] = 100 - (100 / (1 + rs))

    if 'Volume' in df.columns and df['Volume'].sum() > 0:
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        df['Baseline'] = (tp * df['Volume']).cumsum() / (df['Volume'].cumsum() + 1e-10) 
        df['VWAP_Std'] = np.sqrt((((df['Close'] - df['Baseline'])**2) * df['Volume']).cumsum() / (df['Volume'].cumsum() + 1e-10))
        df['VAH'] = df['Baseline'] + df['VWAP_Std'] 
        df['VAL'] = df['Baseline'] - df['VWAP_Std'] 
    else:
        df['Baseline'] = df['Close'].ewm(span=50, adjust=False).mean() 
        df['VAH'] = df['Baseline'] * 1.001; df['VAL'] = df['Baseline'] * 0.999
    
    bn_bearish = bn_bullish = False
    if banknifty_df is not None and not banknifty_df.empty:
        bn_ltp = float(banknifty_df['Close'].iloc[-1])
        bn_baseline = float(banknifty_df['Close'].ewm(span=50, adjust=False).mean().iloc[-1])
        bn_bearish, bn_bullish = bn_ltp < bn_baseline, bn_ltp > bn_baseline

    high, low, close = df['High'], df['Low'], df['Close']
    plus_dm, minus_dm = high.diff(), low.diff()
    plus_dm[plus_dm < 0] = 0; minus_dm[minus_dm > 0] = 0
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    df['ATR_14'] = tr.rolling(window=14).mean()
    df['+DI'] = 100 * (plus_dm.rolling(window=14).mean() / (df['ATR_14'] + 1e-10))
    df['-DI'] = 100 * (abs(minus_dm).rolling(window=14).mean() / (df['ATR_14'] + 1e-10))
    df['ADX_14'] = ((abs(df['+DI'] - df['-DI']) / (df['+DI'] + df['-DI'] + 1e-10)) * 100).rolling(window=14).mean()

    df['AI_Score'], df['Signal'], df['Msg'] = 0, 'WAIT ⏳', "Scanning SMC Setup..."
    active_trade = None
    
    for i in range(30, len(df)):
        prev_c, prev_h, prev_l = float(df['Close'].iloc[i-1]), float(df['High'].iloc[i-1]), float(df['Low'].iloc[i-1])
        prev_baseline, prev_adx, prev_atr, prev_rsi = float(df['Baseline'].iloc[i-1]), float(df['ADX_14'].iloc[i-1]), float(df['ATR_14'].iloc[i-1]), float(df['RSI'].iloc[i-1])
        curr_h, curr_l, curr_o, curr_c = float(df['High'].iloc[i]), float(df['Low'].iloc[i]), float(df['Open'].iloc[i]), float(df['Close'].iloc[i])
        
        ist_time = df.index[i].tz_convert('Asia/Kolkata')
        is_trade_window = (ist_time.hour == 9 and ist_time.minute >= 20) or (ist_time.hour > 9 and ist_time.hour < 15)
        is_eod = (ist_time.hour == 15 and ist_time.minute >= 15)
        
        score, trend_dir, msg, entry_price = 0, 0, "✋ WAIT: Setup not aligned.", 0.0
        
        # Strategy Logic (Added RSI Filters to block false breakouts)
        if is_trade_window and not is_eod and prev_adx >= 22:
            if prev_c < prev_baseline and bn_bearish and prev_rsi < 45: # Momentum must be bearish
                if curr_l < prev_l: 
                    score, trend_dir, entry_price, msg = 100, -1, min(prev_l, curr_o), "📉 EXECUTE PE: Breakdown Locked."
            elif prev_c > prev_baseline and bn_bullish and prev_rsi > 55: # Momentum must be bullish
                if curr_h > prev_h: 
                    score, trend_dir, entry_price, msg = 100, 1, max(prev_h, curr_o), "🚀 EXECUTE CE: Breakout Locked."
        
        df.at[df.index[i], 'Msg'] = msg; df.at[df.index[i], 'AI_Score'] = score
        
        if active_trade is not None:
            trade_closed, status_msg, exit_price = False, "", 0.0
            
            # TRAILING STOP LOSS LOGIC
            if active_trade['Direction'] == 'LONG':
                if curr_c > active_trade['Entry'] + (active_trade['Target'] - active_trade['Entry']) * 0.5:
                    active_trade['StopLoss'] = max(active_trade['StopLoss'], active_trade['Entry']) # Move SL to Breakeven
                    active_trade['TSL_Active'] = True

                if curr_h >= active_trade['Target']: status_msg, trade_closed, exit_price = "🎯 TARGET HIT", True, active_trade['Target']
                elif curr_l <= active_trade['StopLoss']: 
                    status_msg, trade_closed, exit_price = "🛡️ TSL HIT (BREAKEVEN)" if active_trade.get('TSL_Active') else "🛑 SL HIT (-LOSS)", True, active_trade['StopLoss']
            
            elif active_trade['Direction'] == 'SHORT':
                if curr_c < active_trade['Entry'] - (active_trade['Entry'] - active_trade['Target']) * 0.5:
                    active_trade['StopLoss'] = min(active_trade['StopLoss'], active_trade['Entry']) # Move SL to Breakeven
                    active_trade['TSL_Active'] = True

                if curr_l <= active_trade['Target']: status_msg, trade_closed, exit_price = "🎯 TARGET HIT", True, active_trade['Target']
                elif curr_h >= active_trade['StopLoss']: 
                    status_msg, trade_closed, exit_price = "🛡️ TSL HIT (BREAKEVEN)" if active_trade.get('TSL_Active') else "🛑 SL HIT (-LOSS)", True, active_trade['StopLoss']
            
            if is_eod and not trade_closed: status_msg, trade_closed, exit_price = "⏱️ EOD SQUARE-OFF", True, curr_c

            if trade_closed:
                trade_pts = round(exit_price - active_trade['Entry'] if active_trade['Direction']=='LONG' else active_trade['Entry'] - exit_price, 1)
                trade_data = {"Time (IST)": ist_time.strftime("%d-%b %I:%M %p"), "Asset": "NIFTY 50", "Action": active_trade['Type'], "Spot Entry": active_trade['Entry'], "Spot Exit": exit_price, "Points": trade_pts, "Result": status_msg, "Order ID": active_trade.get('OrderID', 'Paper')}
                save_trade(trade_data); active_trade = None 
        else:
            if score == 100 and trend_dir != 0 and is_trade_window:
                atm_strike = int(round(entry_price / 50) * 50)
                sl_pts = max(18.0, round(prev_atr * 1.5, 1)); tgt_pts = round(sl_pts * 2.0, 1)
                if trend_dir == 1: tgt, sl, direction, t_type = entry_price + tgt_pts, entry_price - sl_pts, 'LONG', f'{atm_strike} CE'
                else: tgt, sl, direction, t_type = entry_price - tgt_pts, entry_price + sl_pts, 'SHORT', f'{atm_strike} PE'
                
                # EXECUTE ORDER IN SHOONYA
                order_id = place_shoonya_order(st.session_state.shoonya_token, f"NIFTY{t_type}", 50, "B")
                
                active_trade = {'Type': t_type, 'Signal': f'🟢 BUY NIFTY {t_type}', 'Entry': round(entry_price,1), 'Target': round(tgt,1), 'StopLoss': round(sl,1), 'Direction': direction, 'TSL_Active': False, 'OrderID': order_id}
                df.at[df.index[i], 'Signal'] = active_trade['Signal']
    return df, active_trade

# ==============================================================================
# 6. UI LAYOUT 
# ==============================================================================
header_col1, header_col2 = st.columns([15, 5])
with header_col1: 
    sh_status = f"<span style='color:{primary_color};'><i class='fa-solid fa-link'></i> Live Link</span>" if st.session_state.shoonya_token else f"<span style='color:#ff3333;'>🔴 API: {st.session_state.get('shoonya_msg', 'Disabled')}</span>"
    exec_mode = "<span style='color:#ff3333;'>LIVE TRADING: ENABLED</span>" if LIVE_TRADING else "<span style='color:#a0aec0;'>PAPER TRADING: ENABLED</span>"
    st.markdown(f"<h1 style='margin:0; font-weight:800; color:{text_color};'>QUANT<span style='color:{primary_color};'>SCALPER AI</span> v19.0 <span style='font-size:12px; color:#00ffff;'>⚡TURBO</span> <br><span style='font-size:14px'>{sh_status} | {exec_mode}</span></h1>", unsafe_allow_html=True)
with header_col2:
    tz_ist = pytz.timezone('Asia/Kolkata'); now = datetime.datetime.now(tz_ist)
    market_status = "CLOSED" if now.hour >= 16 or now.hour < 9 or (now.hour==15 and now.minute>=30) else "LIVE"
    st.markdown(f"<div style='text-align:right; font-weight:700; color:#a0aec0; font-size:16px;'>📅 {now.strftime('%d %b')} | <span style='color:{'#ff3333' if market_status=='CLOSED' else primary_color}'>{now.strftime('%I:%M:%S %p')} IST</span></div>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#2d3748; margin: 10px 0 15px 0;'>", unsafe_allow_html=True)

try:
    def fetch_nifty(): return yf.download('^NSEI', period='1d', interval='1m', progress=False)
    def fetch_bn(): return yf.download('^NSEBANK', period='1d', interval='1m', progress=False)
    
    daily_data = fetch_daily_data_cached() 
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        f_nifty, f_bn, f_pcr = executor.submit(fetch_nifty), executor.submit(fetch_bn), executor.submit(get_nse_pcr)
        data, bn_data, pcr_val = f_nifty.result(), f_bn.result(), f_pcr.result()
    
    for d in [data, bn_data, daily_data]:
        if not d.empty:
            if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
            d.index = d.index.tz_convert('Asia/Kolkata') if d.index.tz is not None else d.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
    
    if not data.empty:
        df, active_trade = calculate_quant_engine(data, '^NSEI', bn_data, daily_data)
        last = df.iloc[-1]; curr_p = round(float(last['Close']), 2); pts = round(curr_p - round(float(df['Open'].iloc[0]), 2), 2)
        
        adx, atr, rsi = float(last['ADX_14']), float(last['ATR_14']), float(last['RSI'])
        vwap, vah, val = float(last['Baseline']), float(last['VAH']), float(last['VAL'])
        ai_msg = str(last['Msg'])
        bn_trend = "BULLISH 🟢" if (float(bn_data['Close'].ewm(span=50).mean().iloc[-1]) < float(bn_data['Close'].iloc[-1])) else "BEARISH 🔴"
        
        if active_trade is not None: color_cmd, txt_cmd = "#ffaa00", f"HOLD: {active_trade['Signal']} ACTIVE."
        elif last['AI_Score'] == 100: color_cmd, txt_cmd = "#00ff66", f"🚀 EXECUTE: {last['Signal']} NOW!"
        else: color_cmd, txt_cmd = metric_label, ai_msg
        
        st.markdown(f"<div style='background:{card_bg}; padding:12px; border-radius:10px; border-left:5px solid {color_cmd}; font-weight:700; margin-bottom:12px; border: 1px solid {border_color}; font-size:15px;'>{txt_cmd}</div>", unsafe_allow_html=True)

        m1, m2, m3, m4, m5 = st.columns(5)
        with m1: st.metric("NIFTY SPOT", f"₹{curr_p:,}", f"{pts} pts")
        with m2: st.metric("RSI (1m)", f"{round(rsi, 1)}", "Overbought" if rsi>70 else "Oversold" if rsi<30 else "Neutral", delta_color="off")
        with m3: st.metric("BankNifty Sync", bn_trend)
        with m4: st.metric("Options PCR", f"{pcr_val}" if pcr_val else "Err")
        with m5: st.metric("Institution POC", f"₹{round(vwap,1)}")

        st.markdown("<br>", unsafe_allow_html=True); col_met1, col_met2 = st.columns([1, 2])
        with col_met1:
            st.markdown(f"""
            <div class='inst-box' style='color:{text_color};'>
                <div style='color:{metric_label}; font-size:11px; text-transform:uppercase;'>Market Microstructure</div>
                <div style='margin-top:8px;'><b>Trend Power (ADX):</b> <span style='color:#00ff66;'>{round(adx,1)}</span></div>
                <div><b>Dynamic Risk (ATR):</b> <span style='color:#00ffff;'>{round(atr,1)} pts</span></div>
                <div><b>Value Area High:</b> {round(vah,1)}</div>
                <div><b>Value Area Low:</b> {round(val,1)}</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col_met2:
            if active_trade is not None:
                color_trade = "#00ff66" if active_trade['Direction']=='LONG' else "#ff3333"
                live_pnl = round((curr_p - active_trade['Entry']) if active_trade['Direction']=='LONG' else (active_trade['Entry'] - curr_p), 1)
                tsl_status = "ACTIVE 🛡️" if active_trade.get('TSL_Active') else "WAITING"
                
                st.markdown(f"""
                <div class='ex-card' style='border: 2px solid {color_trade};'>
                    <div style='display:flex; justify-content:space-between;'>
                        <span class='status-badge' style='background:{bg_color}; border: 1px solid {color_trade}; color:{color_trade};'>{active_trade['Direction']} ACTIVE</span>
                        <span style='color:#00ffff; font-size: 12px;'>Order ID: {active_trade.get('OrderID')}</span>
                    </div>
                    <div style='display:flex; justify-content:space-between; align-items:center;'>
                        <h2 style='margin:10px 0;'>ENTRY: ₹{active_trade['Entry']}</h2>
                        <h3 style='color:{"#00ff66" if live_pnl > 0 else "#ff3333"};'>PnL: {live_pnl} pts</h3>
                    </div>
                    <div style='color:#00ff66; font-weight:700; font-size:18px;'>TARGET: ₹{active_trade['Target']}</div>
                    <div style='color:#ffaa00; font-weight:700; font-size:18px;'>TRAILING SL: ₹{active_trade['StopLoss']} (Status: {tsl_status})</div>
                </div>
                """, unsafe_allow_html=True)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df['VAH'], line=dict(width=0), showlegend=False))
        fig.add_trace(go.Scatter(x=df.index, y=df['VAL'], line=dict(width=0), fill='tonexty', fillcolor="rgba(0,255,255,0.1)", name='Value Area'))
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Spot Price', line=dict(color='#deff9a', width=2.5)))
        fig.add_trace(go.Scatter(x=df.index, y=df['Baseline'], name='POC', line=dict(color=secondary_color, width=1.5, dash='dash')))
        
        # Add Trade Markers to Chart
        if active_trade:
            fig.add_hline(y=active_trade['Entry'], line_dash="solid", line_color="#00ffff", annotation_text="Entry")
            fig.add_hline(y=active_trade['Target'], line_dash="dot", line_color="#00ff66", annotation_text="Target")
            fig.add_hline(y=active_trade['StopLoss'], line_dash="dot", line_color="#ff3333", annotation_text="Stop Loss")

        fig.update_layout(template='plotly_dark' if st.session_state.theme == 'dark' else 'plotly_white', paper_bgcolor=plot_paper, plot_bgcolor=plot_bg, height=400, margin=dict(l=0,r=0,t=0,b=0))
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("<hr style='border-color:#2d3748;'>", unsafe_allow_html=True); tab_l1, tab_l2 = st.tabs(["📖 TRADING LOG", "⚙️ SYSTEM SETTINGS"])
        
        with tab_l1:
            n_hist = load_history()
            if not n_hist.empty: st.dataframe(n_hist.style.apply(lambda x: [style_results(val) if x.name == 'Result' else '' for val in x], axis=0), use_container_width=True, hide_index=True)
            else: st.info("No trades executed yet.")
        
        with tab_l2:
            st.warning("⚠️ **Live Execution Safety Limit:** Keep LIVE_TRADING = False while backtesting. The `place_shoonya_order()` function is currently set up for NFO options with Quantity=50. Ensure you adjust the specific token lookup if needed before changing LIVE_TRADING to True.")

except Exception as e: st.error(f"Error Engine: {e}")

time.sleep(8); st.rerun()
