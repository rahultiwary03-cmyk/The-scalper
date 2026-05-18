import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import os

# ==============================================================================
# 1. DUAL TRADE HISTORY LOGGERS (निफ्टी और स्टॉक्स के लिए अलग-अलग)
# ==============================================================================
NIFTY_HISTORY_FILE = "nifty_trade_book.csv"
STOCK_HISTORY_FILE = "stock_trade_book.csv"

def save_trade(trade_data, is_nifty=False):
    filename = NIFTY_HISTORY_FILE if is_nifty else STOCK_HISTORY_FILE
    df = pd.DataFrame([trade_data])
    if not os.path.exists(filename):
        df.to_csv(filename, index=False)
    else:
        existing = pd.read_csv(filename)
        is_duplicate = ((existing['Time'] == trade_data['Time']) & (existing['Asset'] == trade_data['Asset'])).any()
        if not is_duplicate:
            df.to_csv(filename, mode='a', header=False, index=False)

def load_history(is_nifty=False):
    filename = NIFTY_HISTORY_FILE if is_nifty else STOCK_HISTORY_FILE
    if os.path.exists(filename):
        df = pd.read_csv(filename)
        return df.sort_index(ascending=False)
    return pd.DataFrame()

# ==============================================================================
# 2. HYPER-SENSITIVE QUANT ENGINE V6.0 (EMA 9/21 + Baseline + Supertrend)
# ==============================================================================
def calculate_ai_v6(df, symbol):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Fast Momentum EMAs for exact entry catching
    df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
    
    # Baseline Sentiment (VWAP for stocks, EMA_50 for Nifty because YFinance has no Nifty volume)
    if 'Volume' in df.columns and df['Volume'].sum() > 0:
        df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['Cumulative_VP'] = (df['Typical_Price'] * df['Volume']).cumsum()
        df['Cumulative_Vol'] = df['Volume'].cumsum()
        df['Baseline'] = df['Cumulative_VP'] / (df['Cumulative_Vol'] + 1e-10) # VWAP
    else:
        df['Baseline'] = df['Close'].ewm(span=50, adjust=False).mean() # EMA 50 Fallback

    # RSI & ATR
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['RSI_14'] = 100 - (100 / (1 + rs))

    high, low, close = df['High'].squeeze(), df['Low'].squeeze(), df['Close'].squeeze()
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    df['ATR_14'] = tr.rolling(window=14).mean()

    # Supertrend (10, 3) for confirmation
    atr_10 = tr.rolling(window=10).mean()
    hl2 = (high + low) / 2
    f_ub = (hl2 + (3 * atr_10)).tolist()
    f_lb = (hl2 - (3 * atr_10)).tolist()
    c_list = close.tolist()
    trend = np.ones(len(df))
    
    for i in range(1, len(df)):
        if not (f_ub[i] < f_ub[i-1] or c_list[i-1] > f_ub[i-1]): f_ub[i] = f_ub[i-1]
        if not (f_lb[i] > f_lb[i-1] or c_list[i-1] < f_lb[i-1]): f_lb[i] = f_lb[i-1]
        if trend[i-1] == 1 and c_list[i] < f_lb[i]: trend[i] = -1
        elif trend[i-1] == -1 and c_list[i] > f_ub[i]: trend[i] = 1
        else: trend[i] = trend[i-1]
    df['Trend'] = trend

    df['AI_Score'], df['Signal'], df['Entry'], df['Target'], df['StopLoss'], df['Status'] = 0, 'WAIT ⏳', 0.0, 0.0, 0.0, ""

    active_trade = None
    is_nifty = "NSEI" in symbol
    
    start_idx = 20 if len(df) > 20 else 1
    
    for i in range(start_idx, len(df)):
        score = 0
        curr_c = round(float(df['Close'].iloc[i]), 2)
        baseline_val = float(df['Baseline'].iloc[i])
        timestamp = df.index[i].strftime("%d-%b %H:%M")
        
        # --- HYPER-SENSITIVE SCORING ---
        if df['EMA_9'].iloc[i] > df['EMA_21'].iloc[i] and curr_c > baseline_val:
            score += 40  # Bullish Crossover & Above Baseline
            if trend[i] == 1: score += 20
            if df['RSI_14'].iloc[i] > 55: score += 25
            trend_dir = 1
            
        elif df['EMA_9'].iloc[i] < df['EMA_21'].iloc[i] and curr_c < baseline_val:
            score += 40  # Bearish Crossover & Below Baseline
            if trend[i] == -1: score += 20
            if df['RSI_14'].iloc[i] < 45: score += 25
            trend_dir = -1
        else:
            score = 0
            trend_dir = 0
            
        df.at[df.index[i], 'AI_Score'] = score
        
        # Trade Management
        if active_trade is not None:
            df.at[df.index[i], 'Signal'] = active_trade['Signal']
            df.at[df.index[i], 'Entry'] = active_trade['Entry']
            df.at[df.index[i], 'Target'] = active_trade['Target']
            df.at[df.index[i], 'StopLoss'] = active_trade['StopLoss']
            
            trade_closed = False
            status_msg = ""
            
            if active_trade['Direction'] == 'LONG':
                if curr_c >= active_trade['Target']:
                    status_msg, trade_closed = "🎯 TARGET HIT (+PROFIT)", True
                elif curr_c <= active_trade['StopLoss']:
                    status_msg, trade_closed = "🛑 SL HIT (-LOSS)", True
            elif active_trade['Direction'] == 'SHORT':
                if curr_c <= active_trade['Target']:
                    status_msg, trade_closed = "🎯 TARGET HIT (+PROFIT)", True
                elif curr_c >= active_trade['StopLoss']:
                    status_msg, trade_closed = "🛑 SL HIT (-LOSS)", True
            
            if trade_closed:
                df.at[df.index[i], 'Status'] = status_msg
                trade_data = {
                    "Time": timestamp,
                    "Asset": "NIFTY 50" if is_nifty else symbol.replace(".NS", ""),
                    "Type": active_trade['Type'],
                    "Entry Price": active_trade['Entry'],
                    "Exit Price": curr_c,
                    "Result": status_msg
                }
                save_trade(trade_data, is_nifty=is_nifty)
                active_trade = None 
        else:
            if score >= 85 and trend_dir != 0:
                atm_strike = int(round(curr_c / 50) * 50)
                
                if trend_dir == 1:
                    t_type = f'{atm_strike} CE' if is_nifty else 'BUY'
                    sig = f'🟢 BUY NIFTY {t_type}' if is_nifty else f'🟢 BUY {symbol.replace(".NS","")}'
                    tgt = curr_c + 50 if is_nifty else curr_c + (curr_c * 0.006)
                    sl = curr_c - 25 if is_nifty else curr_c - (curr_c * 0.003)
                    direction = 'LONG'
                else:
                    t_type = f'{atm_strike} PE' if is_nifty else 'SELL'
                    sig = f'🔴 BUY NIFTY {t_type}' if is_nifty else f'🔴 SELL {symbol.replace(".NS","")}'
                    tgt = curr_c - 50 if is_nifty else curr_c - (curr_c * 0.006)
                    sl = curr_c + 25 if is_nifty else curr_c + (curr_c * 0.003)
                    direction = 'SHORT'
                
                active_trade = {
                    'Type': t_type, 
                    'Signal': sig, 
                    'Entry': curr_c, 
                    'Target': round(tgt, 2), 
                    'StopLoss': round(sl, 2),
                    'Direction': direction
                }
                
                df.at[df.index[i], 'Signal'] = active_trade['Signal']
                df.at[df.index[i], 'Entry'] = active_trade['Entry']
                df.at[df.index[i], 'Target'] = active_trade['Target']
                df.at[df.index[i], 'StopLoss'] = active_trade['StopLoss']

    return df, active_trade

# ==============================================================================
# 3. PURE SEPARATED UI SETUP
# ==============================================================================
st.set_page_config(page_title="Scalper Pro AI v6.0", layout="wide")

# Audio alert hidden in markdown
audio_code = """<audio id="alert-sound" autoplay><source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-500.wav" type="audio/wav"></audio>"""

st.markdown("""
    <style>
    .stApp { background-color: #05070a; color: #ffffff; }
    [data-testid="stSidebar"] { background-color: #090d16 !important; border-right: 1px solid #1f293d !important; }
    [data-testid="stSidebar"] * { color: #f5f5f5 !important; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    div[data-testid="stMetricValue"] { font-size: 38px; font-weight: 700; color: #00ffff; }
    
    .command-box { padding: 15px; border-radius: 10px; text-align: center; font-weight: bold; font-size: 26px; border: 3px solid; margin-bottom: 20px; }
    .cmd-wait { background-color: #111827; color: #8b949e; border-color: #1f293d; }
    .cmd-hold { background-color: #3d2600; color: #ffaa00; border-color: #ffaa00; }
    .cmd-buy-c { background-color: #021a0d; color: #00ff66; border-color: #00ff66; }
    .cmd-buy-p { background-color: #1a0202; color: #ff3333; border-color: #ff3333; }
    
    .stock-card { background: #0c111d; border-radius: 10px; padding: 20px; border-left: 6px solid #1f293d; margin-bottom: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
    .card-buy { border-color: #00ff66; }
    .card-sell { border-color: #ff3333; }
    </style>
    """, unsafe_allow_html=True)

st.sidebar.markdown("<h2 style='text-align: center; font-weight: 700;'>SCALPER PRO <br><span style='color:#deff9a;'>AI v6.0</span></h2>", unsafe_allow_html=True)
st.sidebar.markdown("<hr style='border-color:#1f293d;'>", unsafe_allow_html=True)
menu = st.sidebar.radio("Navigation Menu", ["⚡ NIFTY OPTIONS", "📡 STOCK RADAR"])

# ==============================================================================
# PAGE 1: NIFTY OPTIONS (सिर्फ निफ्टी और उसका रिकॉर्ड)
# ==============================================================================
if menu == "⚡ NIFTY OPTIONS":
    st.markdown("<h2 style='color:#f5f5f5;'>⚡ NIFTY 50 OPTIONS TERMINAL</h2>", unsafe_allow_html=True)
    try:
        data = yf.download('^NSEI', period='1d', interval='1m', progress=False)
        if not data.empty:
            df, active_trade = calculate_ai_v6(data, '^NSEI')
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            curr_p = round(float(df['Close'].iloc[-1]), 2)
            open_p = round(float(df['Open'].iloc[0]), 2)
            baseline_val = round(float(last['Baseline']), 2)
            sentiment = "🟢 BULLISH" if curr_p > baseline_val else "🔴 BEARISH"
            
            # Sound Trigger Check
            play_sound = False
            
            if active_trade is not None:
                cmd_class = "cmd-hold"
                cmd_text = f"⏳ HOLD : [{active_trade['Type']}] active hai. Spot Target (₹{active_trade['Target']}) ka wait karein."
            elif last['AI_Score'] >= 85:
                cmd_class = "cmd-buy-c" if "CE" in last['Signal'] else "cmd-buy-p"
                cmd_text = f"🚀 {last['Signal']} NOW! Fast Momentum Detected."
                if prev['AI_Score'] < 85: play_sound = True # Naya signal
            else:
                cmd_class = "cmd-wait"
                cmd_text = f"✋ WAIT : Market {sentiment} hai par Momentum weak hai."
            
            if play_sound: st.markdown(audio_code, unsafe_allow_html=True)
                
            st.markdown(f'<div class="command-box {cmd_class}">{cmd_text}</div>', unsafe_allow_html=True)

            c1, c2, c3 = st.columns([1.5, 1, 2])
            pts = round(curr_p - open_p, 2)
            c1.metric("📊 NIFTY 50 SPOT", f"₹{curr_p:,}", f"{'+' if pts>=0 else ''}{pts} pts Today")
            c2.metric("🎯 BASELINE (EMA 50)", f"₹{baseline_val:,}")
            
            with c3:
                if active_trade is not None:
                    color = "#00ff66" if active_trade['Direction'] == 'LONG' else "#ff3333"
                    st.markdown(f"""
                    <div style="border-left: 8px solid {color}; padding: 15px; background: #0c111d; border-radius: 8px;">
                        <h3 style="margin:0; color:{color};">⚡ ACTION: {active_trade['Signal']}</h3>
                        <p style="font-size:18px; margin:5px 0;"><b>SPOT ENTRY:</b> ₹{active_trade['Entry']} | <span style="color:#00ff66;"><b>TARGET:</b> ₹{active_trade['Target']}</span> | <span style="color:#ff3333;"><b>SL:</b> ₹{active_trade['StopLoss']}</span></p>
                    </div>
                    """, unsafe_allow_html=True)

            # Chart (Price vs EMA 9 vs EMA 21 vs Baseline)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Price', line=dict(color='#00ffff', width=2.5)))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_9'], name='9 EMA (Fast)', line=dict(color='#00ff66', width=1)))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_21'], name='21 EMA (Slow)', line=dict(color='#ff3333', width=1)))
            fig.add_trace(go.Scatter(x=df.index, y=df['Baseline'], name='Baseline', line=dict(color='#deff9a', width=2, dash='dash')))
            fig.update_layout(template='plotly_dark', paper_bgcolor='#05070a', plot_bgcolor='#05070a', height=450, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)
            
            # Nifty History
            st.markdown("<hr style='border-color:#1f293d;'><h3 style='color:#deff9a;'>📖 NIFTY OPTIONS LOG</h3>", unsafe_allow_html=True)
            n_hist = load_history(is_nifty=True)
            if not n_hist.empty:
                st.dataframe(n_hist.style.apply(lambda x: ['background-color: #021a0d; color: #00ff66' if 'PROFIT' in str(val) else 'background-color: #1a0202; color: #ff3333' if 'LOSS' in str(val) else '' for val in x], subset=['Result']), use_container_width=True)
            else:
                st.write("No Nifty trades logged yet.")
    except Exception as e:
        st.error(f"Nifty Data Error: {e}")

# ==============================================================================
# PAGE 2: STOCK RADAR (सिर्फ स्टॉक्स और उनका रिकॉर्ड)
# ==============================================================================
elif menu == "📡 STOCK RADAR":
    st.markdown("<h2 style='color:#f5f5f5;'>📡 LIVE STOCK BREAKOUT RADAR</h2>", unsafe_allow_html=True)
    
    stocks = ["RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "TATAMOTORS.NS", "INFY.NS"]
    cols = st.columns(3)
    col_idx = 0
    play_sound_stock = False
    
    for stock in stocks:
        try:
            s_data = yf.download(stock, period='1d', interval='1m', progress=False)
            if not s_data.empty:
                s_df, s_trade = calculate_ai_v6(s_data, stock)
                name = stock.replace(".NS", "")
                curr_p = round(float(s_df['Close'].iloc[-1]), 2)
                vwap_p = round(float(s_df['Baseline'].iloc[-1]), 2)
                
                # Check for new signal to play sound
                if s_trade is not None and s_df.iloc[-2]['AI_Score'] < 85 and s_df.iloc[-1]['AI_Score'] >= 85:
                    play_sound_stock = True

                with cols[col_idx % 3]:
                    if s_trade is not None:
                        color_cls = "card-buy" if s_trade['Direction'] == 'LONG' else "card-sell"
                        t_col = "#00ff66" if s_trade['Direction'] == 'LONG' else "#ff3333"
                        st.markdown(f"""
                        <div class="stock-card {color_cls}">
                            <h3 style="color:{t_col}; margin:0;">{s_trade['Signal']}</h3>
                            <p style="margin:5px 0; color:#8b949e;">LTP: ₹{curr_p} | VWAP: ₹{vwap_p}</p>
                            <hr style="border-color:#1f293d; margin: 10px 0;">
                            <h4 style="margin:5px 0; color:#f5f5f5;">ENTRY: ₹{s_trade['Entry']}</h4>
                            <h4 style="margin:5px 0; color:#00ff66;">TARGET: ₹{s_trade['Target']}</h4>
                            <h4 style="margin:0; color:#ff3333;">SL: ₹{s_trade['StopLoss']}</h4>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class="stock-card">
                            <h3 style="color:#f5f5f5; margin:0;">{name}</h3>
                            <p style="margin:5px 0; color:#8b949e;">LTP: ₹{curr_p} | VWAP: ₹{vwap_p}</p>
                            <p style="margin:10px 0 0 0; color:#ffaa00;">No clear trend. Wait ⏳</p>
                        </div>
                        """, unsafe_allow_html=True)
                col_idx += 1
        except:
            pass
            
    if play_sound_stock: st.markdown(audio_code, unsafe_allow_html=True)
    
    # Stock History
    st.markdown("<hr style='border-color:#1f293d;'><h3 style='color:#deff9a;'>📖 STOCK TRADE LOG</h3>", unsafe_allow_html=True)
    s_hist = load_history(is_nifty=False)
    if not s_hist.empty:
        st.dataframe(s_hist.style.apply(lambda x: ['background-color: #021a0d; color: #00ff66' if 'PROFIT' in str(val) else 'background-color: #1a0202; color: #ff3333' if 'LOSS' in str(val) else '' for val in x], subset=['Result']), use_container_width=True)
    else:
        st.write("No Stock trades logged yet.")

# ==============================================================================
# FAST AUTO-REFRESH (5 SECONDS)
# ==============================================================================
time.sleep(5) 
st.rerun()
