import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import os
import datetime
import pytz

# ==============================================================================
# 1. CORE CONFIGURATION & THEME (Institutional "Inter" Font & Look)
# ==============================================================================
st.set_page_config(page_title="Scalper Pro AI v15.0", layout="wide", initial_sidebar_state="collapsed")

# Professional Sans-Serif Font (Inter) and Deep Dark Theme
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');

    html, body, [class*="css"]  {
        font-family: 'Inter', sans-serif;
        background-color: #0b0e11;
        color: #e3e9f0;
    }
    
    /* Main Background */
    .stApp { background-color: #0b0e11; }
    
    /* Hide Streamlit default UI */
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    [data-testid="collapsedControl"] { display: none; }
    
    /* Modern Navigation Pills (Tabs) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
        background-color: #14181f;
        padding: 10px;
        border-radius: 12px;
        border: 1px solid #2d3748;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border-radius: 8px;
        padding: 10px 20px;
        font-size: 14px;
        font-weight: 600;
        color: #a0aec0;
        border: none;
        transition: all 0.2s ease;
    }
    .stTabs [aria-selected="true"] {
        background-color: #deff9a;
        color: #0b0e11 !important;
        box-shadow: 0 4px 12px rgba(222, 255, 154, 0.3);
    }
    .stTabs [data-baseweb="tab"]:hover:not([aria-selected="true"]) {
        color: #deff9a;
        background-color: rgba(222, 255, 154, 0.05);
    }

    /* Condensed Execution Card (Glow Effect) */
    .ex-card {
        background: #14181f;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #2d3748;
        margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        transition: box-shadow 0.3s ease;
    }
    .ex-card:hover { box-shadow: 0 4px 15px rgba(222, 255, 154, 0.1); }
    
    .status-badge {
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 800;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    /* Profit/Loss Table Colors */
    .p-box { color: #00ff66; font-weight: 700; background: rgba(0, 255, 102, 0.1); padding: 4px 8px; border-radius: 4px; border: 1px solid #00ff66; }
    .l-box { color: #ff3333; font-weight: 700; background: rgba(255, 51, 51, 0.1); padding: 4px 8px; border-radius: 4px; border: 1px solid #ff3333; }
    
    /* Analytics Metric Card */
    .m-card { background: #14181f; border-radius: 10px; padding: 20px; border: 1px solid #2d3748; text-align: center; }
    
    </style>
    """, unsafe_allow_html=True)

audio_code = """<audio id="alert-sound" autoplay><source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-500.wav" type="audio/wav"></audio>"""

# ==============================================================================
# 2. DATA LOADERS & HISTORY
# ==============================================================================
NIFTY_HISTORY_FILE = "nifty_trade_book.csv"
STOCK_HISTORY_FILE = "stock_trade_book.csv"

def save_trade(trade_data, is_nifty=False):
    filename = NIFTY_HISTORY_FILE if is_nifty else STOCK_HISTORY_FILE
    df_new = pd.DataFrame([trade_data])
    if not os.path.exists(filename): df_new.to_csv(filename, index=False)
    else:
        try:
            existing = pd.read_csv(filename)
            if 'Result' in existing.columns: # Prevent corrupt app
                is_duplicate = ((existing['Time (IST)'] == trade_data['Time (IST)']) & (existing['Asset'] == trade_data['Asset'])).any()
                if not is_duplicate: df_new.to_csv(filename, mode='a', header=False, index=False)
        except: df_new.to_csv(filename, index=False)

def load_history(is_nifty=False):
    filename = NIFTY_HISTORY_FILE if is_nifty else STOCK_HISTORY_FILE
    if os.path.exists(filename):
        try:
            df = pd.read_csv(filename)
            if df.empty or 'Result' not in df.columns: return pd.DataFrame()
            return df.sort_index(ascending=False)
        except: return pd.DataFrame()
    return pd.DataFrame()

# ==============================================================================
# 3. PRO QUANT ENGINE (v15.0: ADX 25+ Trend Filter)
# ==============================================================================
def calculate_quant_engine(df, symbol):
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

    # Core EMAs
    df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
    
    # 🚀 INSTITUTIONAL TREND FILTER: ADX
    # Captures trend strength. ADX > 25 = Strong Trend. ADX < 20 = Choppy/Sideways.
    high, low, close = df['High'].squeeze(), df['Low'].squeeze(), df['Close'].squeeze()
    plus_dm = high.diff(); minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0; minus_dm[minus_dm > 0] = 0
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr_smooth = tr.rolling(window=14).mean()
    df['+DI'] = 100 * (plus_dm.rolling(window=14).mean() / (atr_smooth + 1e-10))
    df['-DI'] = 100 * (abs(minus_dm).rolling(window=14).mean() / (atr_smooth + 1e-10))
    dx = (abs(df['+DI'] - df['-DI']) / (df['+DI'] + df['-DI'] + 1e-10)) * 100
    df['ADX_14'] = dx.rolling(window=14).mean()

    # RSI for Momentum
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI_14'] = 100 - (100 / (1 + (gain / (loss + 1e-10))))

    df['AI_Score'], df['Signal'], df['Entry'], df['Target'], df['StopLoss'], df['Status'] = 0, 'WAIT ⏳', 0.0, 0.0, 0.0, ""
    active_trade = None
    is_nifty = "NSEI" in symbol
    
    start_idx = 30 if len(df) > 30 else 1 # Need data for ADX calculation
    for i in range(start_idx, len(df)):
        curr_c = round(float(df['Close'].iloc[i]), 2)
        adx = float(df['ADX_14'].iloc[i])
        rsi = float(df['RSI_14'].iloc[i])
        
        candle_time = df.index[i]
        if candle_time.tz is None: candle_time = candle_time.tz_localize('UTC')
        ist_time = candle_time.tz_convert('Asia/Kolkata')
        timestamp = ist_time.strftime("%d-%b %I:%M %p")
        
        # 🕒 PROFITABILITY TIME FILTERS
        # 1. Start After Open Range: 9:20 AM
        # 2. No New Trades after 3:00 PM
        is_trade_allowed_time = (ist_time.hour == 9 and ist_time.minute >= 20) or (ist_time.hour > 9 and ist_time.hour < 15)
        # 3. Strict 3:15 EOD Exit
        is_eod = (ist_time.hour == 15 and ist_time.minute >= 15) or (ist_time.hour >= 16)
            
        # 🛡️ THE PROFITABILITY FILTER: Crossover + ADX > 25 (Must have trend strength)
        score = 0
        trend_dir = 0
        if is_trade_allowed_time and not is_eod:
            # TREND MUST BE STRONG (ADX > 25)
            if adx >= 25:
                # Long
                if df['EMA_9'].iloc[i] > df['EMA_21'].iloc[i] and df['+DI'].iloc[i] > df['-DI'].iloc[i]:
                    score = 100 if rsi >= 60 else 70
                    trend_dir = 1
                # Short
                elif df['EMA_9'].iloc[i] < df['EMA_21'].iloc[i] and df['-DI'].iloc[i] > df['+DI'].iloc[i]:
                    score = 100 if rsi <= 40 else 70
                    trend_dir = -1
        
        df.at[df.index[i], 'AI_Score'] = score
        
        if active_trade is not None:
            df.at[df.index[i], 'Signal'] = active_trade['Signal']
            df.at[df.index[i], 'Entry'] = active_trade['Entry']
            df.at[df.index[i], 'Target'] = active_trade['Target']
            df.at[df.index[i], 'StopLoss'] = active_trade['StopLoss']
            
            trade_closed = False
            status_msg = ""
            
            # Strict EOD Exit
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
            # Trigger only at High Confidence (100) and Allowed Time
            if score == 100 and trend_dir != 0:
                atm_strike = int(round(curr_c / 50) * 50)
                # Standardized Intraday Risk Management (Points based on Spot)
                sl_pts = 25; tgt_pts = 50 # Strict 1:2 RRR
                
                if trend_dir == 1:
                    t_type = f'{atm_strike} CE' if is_nifty else 'BUY'
                    entry, tgt, sl = curr_c, curr_c + tgt_pts, curr_c - sl_pts
                    direction = 'LONG'
                else:
                    t_type = f'{atm_strike} PE' if is_nifty else 'SELL'
                    entry, tgt, sl = curr_c, curr_c - tgt_pts, curr_c + sl_pts
                    direction = 'SHORT'
                
                sig = f'🟢 BUY NIFTY {t_type}' if is_nifty else f'🟢 BUY {symbol.replace(".NS","")}'
                active_trade = {'Type': t_type, 'Signal': sig, 'Entry': round(entry,1), 'Target': round(tgt,1), 'StopLoss': round(sl,1), 'Direction': direction}
                df.at[df.index[i], 'Signal'], df.at[df.index[i], 'Entry'], df.at[df.index[i], 'Target'], df.at[df.index[i], 'StopLoss'] = active_trade['Signal'], active_trade['Entry'], active_trade['Target'], active_trade['StopLoss']

    return df, active_trade

# ==============================================================================
# 4. SWING ENGINE (RELAXED FOR DELIVERIES)
# ==============================================================================
def scan_swing_stocks(tickers):
    results = []
    for sym in tickers:
        try:
            df = yf.download(sym, period='6mo', interval='1d', progress=False)
            if df.empty or len(df) < 30: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
            df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean(); loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-10))))
            df['Vol_Avg'] = df['Volume'].rolling(20).mean()
            last = df.iloc[-1]; c = round(float(last['Close']), 2)
            is_uptrend = c > last['EMA_20'] > last['EMA_50']; is_momentum = last['RSI'] >= 58; is_vol_surge = last['Volume'] > (1.2 * last['Vol_Avg'])
            
            status = "🚀 STRONG BUY" if is_uptrend and is_momentum and is_vol_surge else "🔥 POTENTIAL" if is_uptrend and is_momentum else "⏳ WAIT"
            results.append({"Stock": sym.replace('.NS', ''), "LTP (₹)": c, "RSI": round(last['RSI'],1), "Uptrend": "✅" if is_uptrend else "❌", "Action": status})
        except: pass
    return results

# ==============================================================================
# 5. UI LAYOUT & ANALYTICS
# ==============================================================================
# Pro Header
col_h1, col_h2 = st.columns([2, 1])
with col_h1: st.markdown("<h1 style='margin:0; font-weight:800; color:#e3e9f0;'>QUANT<span style='color:#deff9a;'>SCALPER AI</span> v15</h1>", unsafe_allow_html=True)
with col_h2:
    tz_ist = pytz.timezone('Asia/Kolkata'); now = datetime.datetime.now(tz_ist)
    market_status = "CLOSED" if now.hour >= 16 or now.hour < 9 or (now.hour==15 and now.minute>=30) else "LIVE"
    st.markdown(f"<div style='text-align:right; font-weight:700; color:#a0aec0; font-size:16px;'>📅 {now.strftime('%A, %d %b')} | <span style='color:{'#ff3333' if market_status=='CLOSED' else '#00ff66'}'>{now.strftime('%I:%M:%S %p')} IST ({market_status})</span></div>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#2d3748; margin: 10px 0 20px 0;'>", unsafe_allow_html=True)

# THE NAVIGATION PILLS
tab1, tab2, tab3, tab4, tab5 = st.tabs(["⚡ NIFTY INT.", "📡 STOCK INT.", "🚀 SWING RADAR", "📈 P&L ANALYTICS", "👨‍💻 CREATOR"])

# ------------------------------------------------------------------------------
# TAB 1: NIFTY OPTIONS
# ------------------------------------------------------------------------------
with tab1:
    try:
        data = yf.download('^NSEI', period='1d', interval='1m', progress=False)
        if not data.empty:
            df, active_trade = calculate_quant_engine(data, '^NSEI')
            last = df.iloc[-1]; prev = df.iloc[-2]; curr_p = round(float(df['Close'].iloc[-1]), 2); open_p = round(float(df['Open'].iloc[0]), 2); pts = round(curr_p - open_p, 2)
            adx = float(last['ADX_14'])
            
            # UI Message Logic
            is_eod_ui = now.hour >= 15 and now.minute >= 15
            
            if is_eod_ui: color_cmd, txt_cmd = "#ff3333", "EOD Square-Off: इंट्राडे का समय समाप्त। कोई नया ट्रेड नहीं।"
            elif active_trade is not None: color_cmd, txt_cmd = "#ffaa00", f"HOLD : {active_trade['Signal']} सक्रिय है।"
            elif adx < 25: color_cmd, txt_cmd = "#a0aec0", "✋ WAIT: मार्केट साइडवेज है (Chop Zone)। ट्रेड नहीं ले सकते।"
            elif last['AI_Score'] == 100: color_cmd, txt_cmd = "#00ff66", f"🚀 EXECUTE: {last['Signal']} अभी! ट्रेंड मजबूत है।"
            else: color_cmd, txt_cmd = "#a0aec0", "WAIT: परफेक्ट सेटअप का इंतज़ार है।"
            
            st.markdown(f"<div style='background:#14181f; padding:15px; border-radius:10px; border-left:5px solid {color_cmd}; color:{color_cmd}; font-weight:700; margin-bottom:15px; font-size:16px;'>{txt_cmd}</div>", unsafe_allow_html=True)

            # Compact Metrics and Execution Box
            col_met1, col_met2 = st.columns([1, 2])
            with col_met1:
                st.metric("NIFTY SPOT", f"₹{curr_p:,}", f"{pts} pts", help="yfinance delayed data")
                color_adx = "#00ff66" if adx>=25 else "#ff3333"
                st.markdown(f"<div style='background:#14181f; padding:10px; border-radius:8px; border:1px solid #2d3748;'>TREND STRENGTH (ADX): <span style='color:{color_adx}; font-weight:700;'>{round(adx,1)} ({'Trending' if adx>=25 else 'Chop Zone'})</span></div>", unsafe_allow_html=True)
            
            with col_met2:
                if active_trade is not None and not is_eod_ui:
                    color = "#00ff66" if active_trade['Direction']=='LONG' else "#ff3333"
                    rrr = round((active_trade['Target'] - active_trade['Entry']) / (active_trade['Entry'] - active_trade['StopLoss']),1)
                    # Sound for entry
                    if play_sound:= (last['AI_Score']==100 and prev['AI_Score']<100): st.markdown(audio_code, unsafe_allow_html=True)
                    
                    st.markdown(f"""
                    <div class='ex-card'>
                        <div style='display:flex; justify-content:space-between;'>
                            <span class='status-badge' style='background:{'rgba(0,255,102,0.1)' if color=='#00ff66' else 'rgba(255,51,51,0.1)'}; color:{color};'>{active_trade['Direction']} ACTIVE</span>
                            <span style='color:#a0aec0;'>Strike: {active_trade['Type']}</span>
                        </div>
                        <h2 style='margin:10px 0; color:#e3e9f0;'>SPOT ENTRY: ₹{active_trade['Entry']}</h2>
                        <div style='color:#00ff66; font-weight:600;'>TARGET: ₹{active_trade['Target']} (Spot)</div>
                        <div style='color:#ff3333; font-weight:600;'>SL: ₹{active_trade['StopLoss']} (Spot)</div>
                        <div style='color:#8b949e; font-size:12px; margin-top:5px;'>Risk/Reward: 1:{abs(rrr)} (Premium targets rely on Spot move)</div>
                    </div>
                    """, unsafe_allow_html=True)

            # Chart (Pro Dark)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Spot Price', line=dict(color='#deff9a', width=2.5)))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_9'], name='9 EMA', line=dict(color='#00ff66', width=1, dash='dot')))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_21'], name='21 EMA', line=dict(color='#ff3333', width=1, dash='dot')))
            fig.update_layout(template='plotly_dark', paper_bgcolor='#0b0e11', plot_bgcolor='#0b0e11', height=380, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(showgrid=False, title="Time (1-Min)"), yaxis=dict(gridcolor='#2d3748', title="Spot Price"))
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("<h3 style='color:#deff9a;'>📖 NIFTY OPTIONS LOG (IST)</h3>", unsafe_allow_html=True)
            n_hist = load_history(is_nifty=True)
            if not n_hist.empty: 
                # Professional Table Style
                st.dataframe(n_hist[['Time (IST)','Action','Spot Entry','Spot Exit','Points','Result']].style.apply(lambda x: ['p-box' if 'TARGET' in str(val) else 'l-box' if 'SL HIT' in str(val) or 'SQUARE-OFF' in str(val) else '' for val in x], subset=['Result']), use_container_width=True, hide_index=True)
    except Exception as e: st.error(f"Error Nifty Tab: {e}")

# ------------------------------------------------------------------------------
# TAB 2: INTRADAY STOCKS
# ------------------------------------------------------------------------------
with tab2:
    stocks = ["RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "TATAMOTORS.NS", "INFY.NS"]
    cols = st.columns(3); col_idx = 0
    for stock in stocks:
        try:
            s_data = yf.download(stock, period='1d', interval='1m', progress=False)
            if not s_data.empty:
                s_df, s_trade = calculate_quant_engine(s_data, stock); name = stock.replace(".NS", ""); curr_p = round(float(s_df['Close'].iloc[-1]), 2)
                adx_s = float(s_df['ADX_14'].iloc[-1])
                with cols[col_idx % 3]:
                    if s_trade is not None:
                        color = "#00ff66" if s_trade['Direction'] == 'LONG' else "#ff3333"
                        st.markdown(f"<div class='ex-card' style='border-color:{color}; background:rgba(20,24,31,0.5);'><span class='status-badge' style='background:{'rgba(0,255,102,0.1)' if color=='#00ff66' else 'rgba(255,51,51,0.1)'}; color:{color};'>{name} {s_trade['Direction']}</span><h3 style='color:{color}; margin:10px 0;'>ENTRY: ₹{s_trade['Entry']}</h3>LTP: {curr_p} | Tgt: {s_trade['Target']}</div>", unsafe_allow_html=True)
                    elif adx_s < 25:
                        st.markdown(f"<div class='ex-card' style='color:#a0aec0;'><h3>{name}</h3>LTP: {curr_p} | Sideways (ADX:{round(adx_s,1)})</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='ex-card'><h3>{name}</h3>LTP: {curr_p} | Wait Setup...</div>", unsafe_allow_html=True)
                col_idx += 1
        except: pass

# ------------------------------------------------------------------------------
# TAB 3: SWING RADAR (v13 Scoring)
# ------------------------------------------------------------------------------
with tab3:
    st.write("🔥 10 हाई-मोमेंटम स्टॉक्स का डेली चार्ट स्कैन।")
    swing_list = ["RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "TATAMOTORS.NS", "INFY.NS", "TCS.NS", "ITC.NS", "LT.NS", "M&M.NS"]
    with st.spinner("Scanning Charts..."): swing_results = scan_swing_stocks(swing_list)
    if swing_results:
        df_swing = pd.DataFrame(swing_results)
        st.dataframe(df_swing.style.apply(lambda x: ['p-box' if 'STRONG BUY' in str(val) else 'potential-box' if 'POTENTIAL' in str(val) else '' for val in x], subset=['Action']), use_container_width=True, hide_index=True)

# ------------------------------------------------------------------------------
# TAB 4: NEW - P&L ANALYTICS (Self-Analysis Dashboard)
# ------------------------------------------------------------------------------
with tab4:
    st.markdown("<h2 style='color:#deff9a; font-weight:800;'>📊 YOUR TRADING PERFORMANCE AUDIT</h2>", unsafe_allow_html=True)
    st.write("निफ्टी और स्टॉक्स के ट्रेड लॉग्स का ऑटोमैटिक गणित। यह डैशबोर्ड आपको आपकी हकीकत दिखाएगा।")
    st.markdown("<hr style='border-color:#2d3748;'>", unsafe_allow_html=True)
    
    # Load all logs
    df_n = load_history(is_nifty=True)
    df_s = load_history(is_nifty=False)
    
    # Pre-process Spot Points to float (needed for calculation)
    def clean_and_calc(df):
        if df.empty: return df
        # Convert necessary columns to float
        df['Spot Entry'] = pd.to_numeric(df['Spot Entry'], errors='coerce')
        df['Spot Exit'] = pd.to_numeric(df['Spot Exit'], errors='coerce')
        df['Points'] = pd.to_numeric(df['Points'], errors='coerce')
        return df

    df_n_c = clean_and_calc(df_n)
    df_s_c = clean_and_calc(df_s)
    
    all_trades = pd.concat([df_n_c, df_s_c])
    
    if not all_trades.empty:
        # 1. Total Metrics
        total_trades = len(all_trades)
        wins = len(all_trades[all_trades['Result'].str.contains('TARGET HIT|PROFIT', na=False)])
        losses = len(all_trades[all_trades['Result'].str.contains('SL HIT|LOSS|EOD', na=False)])
        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
        total_points = all_trades['Points'].sum()
        avg_rr = round(wins/losses,1) if losses > 0 else wins
        
        c_an1, c_an2, c_an3, c_an4 = st.columns(4)
        with c_an1: st.metric("Total Trades Executed", total_trades)
        with c_an2: st.metric("Winning Trades ✅", wins)
        with c_an3: 
            color_wr = "normal" if win_rate >= 60 else "inverse" # Red if below 60%
            st.metric("Total Win Rate %", f"{round(win_rate, 1)}%", delta_color=color_wr)
        with c_an4:
            color_pts = "normal" if total_points >= 0 else "inverse" 
            st.metric("Total Spot Points P&L", f"{round(total_points, 1)} pts", delta_color=color_pts, help="Estimated points based on Spot move.")

        st.markdown("<br>", unsafe_allow_html=True)
        
        # 2. Performance Chart (Nifty vs Stocks P&L Points)
        col_an_ch1, col_an_ch2 = st.columns([1, 1])
        
        with col_an_ch1:
            st.write("🔄 Nifty vs Stocks: Accumulated Points")
            pts_data = pd.DataFrame({'Asset': ['Nifty Options', 'Intraday Stocks'], 'Points': [df_n_c['Points'].sum() if not df_n_c.empty else 0, df_s_c['Points'].sum() if not df_s_c.empty else 0]})
            fig_pts = go.Figure(data=[go.Bar(x=pts_data['Asset'], y=pts_data['Points'], marker_color=['#00ffff', '#deff9a'], text=pts_data['Points'], textposition='outside')])
            fig_pts.update_layout(template='plotly_dark', paper_bgcolor='#0b0e11', plot_bgcolor='#0b0e11', height=300, margin=dict(l=0,r=0,t=10,b=0), yaxis=dict(title="Spot Points"))
            st.plotly_chart(fig_pts, use_container_width=True)
            
        with col_an_ch2:
            st.write("📊 Trade Result Distribution")
            res_count = all_trades['Result'].str.extract(r'(TARGET HIT|PROFIT|SL HIT|LOSS|EOD)')[0].value_counts()
            fig_res = go.Figure(data=[go.Pie(labels=res_count.index, values=res_count.values, hole=.5, marker_colors=['#00ff66', '#ff3333', '#ffaa00'])])
            fig_res.update_layout(template='plotly_dark', paper_bgcolor='#0b0e11', plot_bgcolor='#0b0e11', height=300, margin=dict(l=0,r=0,t=10,b=0), showlegend=False)
            st.plotly_chart(fig_res, use_container_width=True)
            
        st.write("⚠️ Pro Tip: अगर Win Rate 60% से कम है और Total Points लाल (Negative) हैं, तो या तो ADX फ़िल्टर को और सख्त करें या मार्केट साइडवेज होने पर ट्रेड न लें।")
            
    else:
        st.info("डैशबोर्ड को एक्टिवेट करने के लिए पहले कम से कम एक ट्रेड क्लोज करें।")

# ------------------------------------------------------------------------------
# TAB 5: ABOUT CREATOR
# ------------------------------------------------------------------------------
with tab5:
    col_c1, col_c2, col_c3 = st.columns([1, 2, 1]) 
    with col_c2:
        try: st.image("photo.jpg", width=200)
        except: st.info("Tip: GitHub पर 'photo.jpg' अपलोड करें।")
        st.markdown(f"<div style='text-align:center;'><h1>[अपना नाम]</h1>Quant Developer | Algo Trader</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='background:#14181f; padding:20px; border-radius:10px; border:1px solid #2d3748; text-align:center;'>📺 YouTube: TechVantageHindi | 📱 Telegram: @JoinMyChannel<br>This system is for quantitative research only.</div>", unsafe_allow_html=True)

# ==============================================================================
# FAST REFRESH (8 SECONDS)
# ==============================================================================
time.sleep(8); st.rerun()
