import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import os

# ==============================================================================
# 1. PERMANENT TRADE HISTORY LOGGER (हमेशा के लिए सेव)
# ==============================================================================
HISTORY_FILE = "trade_record_book.csv"

def save_trade_to_csv(trade_data):
    df = pd.DataFrame([trade_data])
    if not os.path.exists(HISTORY_FILE):
        df.to_csv(HISTORY_FILE, index=False)
    else:
        # डुप्लीकेट एंट्री रोकने के लिए चेक
        existing = pd.read_csv(HISTORY_FILE)
        is_duplicate = ((existing['Time'] == trade_data['Time']) & (existing['Asset'] == trade_data['Asset'])).any()
        if not is_duplicate:
            df.to_csv(HISTORY_FILE, mode='a', header=False, index=False)

# ==============================================================================
# 2. ADVANCED QUANT ENGINE V4.0 (VOLUME SURGE & EXACT ENTRIES)
# ==============================================================================
def calculate_ai_v4(df, symbol):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # कोर इंडिकेटर्स
    df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
    
    # स्मार्ट मनी वॉल्यूम ट्रैकिंग (मोमेंटम के लिए)
    if 'Volume' in df.columns:
        df['Vol_SMA'] = df['Volume'].rolling(window=20).mean()
    else:
        df['Vol_SMA'] = 1

    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['RSI_14'] = 100 - (100 / (1 + rs))

    high, low, close = df['High'].squeeze(), df['Low'].squeeze(), df['Close'].squeeze()
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    df['ATR_14'] = tr.rolling(window=14).mean()

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
    today_trades = []
    
    for i in range(20, len(df)):
        score = 0
        curr_c = round(float(c_list[i]), 2)
        atr = df['ATR_14'].iloc[i]
        timestamp = df.index[i].strftime("%d-%b %H:%M")
        
        # एक्स्ट्रा मोमेंटम चेक (Volume > Average)
        vol_surge = False
        if 'Volume' in df.columns and df['Volume'].iloc[i] > (1.5 * df['Vol_SMA'].iloc[i]):
            vol_surge = True

        # Scoring
        if trend[i] == 1: 
            score += 30
            if curr_c > df['EMA_20'].iloc[i]: score += 20
            if df['RSI_14'].iloc[i] > 60: score += 20
            if tr.iloc[i] > df['ATR_14'].iloc[i]: score += 10
            if vol_surge: score += 20 # स्मार्ट मनी कन्फर्मेशन
        else:
            score += 30
            if curr_c < df['EMA_20'].iloc[i]: score += 20
            if df['RSI_14'].iloc[i] < 40: score += 20
            if tr.iloc[i] > df['ATR_14'].iloc[i]: score += 10
            if vol_surge: score += 20
            
        df.at[df.index[i], 'AI_Score'] = score
        
        # Trade Exit Logic
        if active_trade is not None:
            df.at[df.index[i], 'Signal'] = active_trade['Signal']
            df.at[df.index[i], 'Entry'] = active_trade['Entry']
            df.at[df.index[i], 'Target'] = active_trade['Target']
            df.at[df.index[i], 'StopLoss'] = active_trade['StopLoss']
            
            trade_closed = False
            status_msg = ""
            if active_trade['Type'] in ['CALL', 'BUY']:
                if curr_c >= active_trade['Target']:
                    status_msg, trade_closed = "🎯 TARGET HIT (PROFIT)", True
                elif curr_c <= active_trade['StopLoss']:
                    status_msg, trade_closed = "🛑 SL HIT (LOSS)", True
            elif active_trade['Type'] in ['PUT', 'SELL']:
                if curr_c <= active_trade['Target']:
                    status_msg, trade_closed = "🎯 TARGET HIT (PROFIT)", True
                elif curr_c >= active_trade['StopLoss']:
                    status_msg, trade_closed = "🛑 SL HIT (LOSS)", True
            
            if trade_closed:
                df.at[df.index[i], 'Status'] = status_msg
                trade_data = {
                    "Time": timestamp,
                    "Asset": symbol,
                    "Type": active_trade['Type'],
                    "Entry Price": active_trade['Entry'],
                    "Exit Price": curr_c,
                    "Result": status_msg
                }
                today_trades.append(trade_data)
                save_trade_to_csv(trade_data) # <--- परमानेंट सेव
                active_trade = None 
        else:
            if score >= 85:
                # Nifty के लिए 50 पॉइंट, Stocks के लिए 2x ATR का टारगेट
                if trend[i] == 1:
                    t_type = 'CALL' if "NSEI" in symbol else 'BUY'
                    sig = f'🟢 {t_type} {symbol.replace(".NS","")}'
                    tgt = curr_c + 50 if "NSEI" in symbol else curr_c + (2.5 * atr)
                    sl = curr_c - (1.2 * atr)
                else:
                    t_type = 'PUT' if "NSEI" in symbol else 'SELL'
                    sig = f'🔴 {t_type} {symbol.replace(".NS","")}'
                    tgt = curr_c - 50 if "NSEI" in symbol else curr_c - (2.5 * atr)
                    sl = curr_c + (1.2 * atr)
                
                active_trade = {
                    'Type': t_type, 
                    'Signal': sig, 
                    'Entry': curr_c, 
                    'Target': round(tgt, 2), 
                    'StopLoss': round(sl, 2)
                }
                
                df.at[df.index[i], 'Signal'] = active_trade['Signal']
                df.at[df.index[i], 'Entry'] = active_trade['Entry']
                df.at[df.index[i], 'Target'] = active_trade['Target']
                df.at[df.index[i], 'StopLoss'] = active_trade['StopLoss']

    return df, today_trades, active_trade

# ==============================================================================
# 3. PROFESSIONAL UI SETUP
# ==============================================================================
st.set_page_config(page_title="Scalper Pro AI v4.0", layout="wide")

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
    
    /* Stock Card Styles */
    .stock-card { background: #0c111d; border-radius: 10px; padding: 15px; border-left: 6px solid #1f293d; margin-bottom: 15px; }
    .card-buy { border-color: #00ff66; }
    .card-sell { border-color: #ff3333; }
    </style>
    """, unsafe_allow_html=True)

st.sidebar.markdown("<h2 style='text-align: center; font-weight: 700;'>SCALPER PRO <br><span style='color:#deff9a;'>AI v4.0</span></h2>", unsafe_allow_html=True)
st.sidebar.markdown("<hr style='border-color:#1f293d;'>", unsafe_allow_html=True)
menu = st.sidebar.radio("Navigation Menu", ["⚡ LIVE NIFTY STATION", "📡 LIVE STOCK RADAR", "📖 ALL-TIME HISTORY"])

# ------------------------------------------------------------------------------
# PAGE 1: NIFTY 50 STATION
# ------------------------------------------------------------------------------
if menu == "⚡ LIVE NIFTY STATION":
    st.markdown("<h2 style='color:#f5f5f5;'>⚡ NIFTY 50 AI QUANT STATION</h2>", unsafe_allow_html=True)
    data = yf.download('^NSEI', period='1d', interval='1m', progress=False)
    if not data.empty:
        df, _, active_trade = calculate_ai_v4(data, '^NSEI')
        last = df.iloc[-1]
        
        curr_p = round(float(df['Close'].iloc[-1]), 2)
        open_p = round(float(df['Open'].iloc[0]), 2)
        
        if active_trade is not None:
            cmd_class = "cmd-hold"
            cmd_text = f"⏳ HOLD : [{active_trade['Signal']}] active hai. Target (₹{active_trade['Target']}) ka wait karein."
        elif last['AI_Score'] >= 85:
            atm_strike = int(round(curr_p / 50) * 50)
            opt = "CE" if "CALL" in last['Signal'] else "PE"
            cmd_class = "cmd-buy-c" if opt == "CE" else "cmd-buy-p"
            cmd_text = f"🚀 BUY NIFTY {atm_strike} {opt} NOW! Breakout detected."
        else:
            cmd_class = "cmd-wait"
            cmd_text = "✋ WAIT : Market sideways ya No-Trade Zone mein hai."
            
        st.markdown(f'<div class="command-box {cmd_class}">{cmd_text}</div>', unsafe_allow_html=True)

        c1, c2 = st.columns([1, 2])
        pts = round(curr_p - open_p, 2)
        c1.metric("📊 NIFTY 50 SPOT", f"₹{curr_p:,}", f"{'+' if pts>=0 else ''}{pts} pts Today")
        
        with c2:
            if active_trade is not None:
                color = "#00ff66" if active_trade['Type'] == 'CALL' else "#ff3333"
                st.markdown(f"""
                <div style="border-left: 8px solid {color}; padding: 15px; background: #0c111d; border-radius: 8px;">
                    <h3 style="margin:0; color:{color};">⚡ ACTION: {active_trade['Signal']}</h3>
                    <p style="font-size:20px; margin:5px 0;"><b>ENTRY:</b> ₹{active_trade['Entry']} | <span style="color:#00ff66;"><b>🎯 TARGET:</b> ₹{active_trade['Target']}</span> | <span style="color:#ff3333;"><b>🛑 SL:</b> ₹{active_trade['StopLoss']}</span></p>
                </div>
                """, unsafe_allow_html=True)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Price', line=dict(color='#00ffff')))
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_20'], name='20 EMA', line=dict(color='#ffaa00', dash='dot')))
        fig.update_layout(template='plotly_dark', paper_bgcolor='#05070a', plot_bgcolor='#05070a', height=400)
        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------------------
# PAGE 2: LIVE STOCK RADAR (NEW)
# ------------------------------------------------------------------------------
elif menu == "📡 LIVE STOCK RADAR":
    st.markdown("<h2 style='color:#f5f5f5;'>📡 LIVE STOCK BREAKOUT RADAR</h2>", unsafe_allow_html=True)
    st.write("Top Volume Breakout Stocks scanning... (High Momentum)")
    
    # India ke top high beta stocks
    stocks = ["RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "TATAMOTORS.NS"]
    
    cols = st.columns(3)
    col_idx = 0
    
    for stock in stocks:
        s_data = yf.download(stock, period='1d', interval='1m', progress=False)
        if not s_data.empty:
            s_df, _, s_trade = calculate_ai_v4(s_data, stock)
            name = stock.replace(".NS", "")
            
            with cols[col_idx % 3]:
                if s_trade is not None:
                    color_cls = "card-buy" if s_trade['Type'] == 'BUY' else "card-sell"
                    t_col = "#00ff66" if s_trade['Type'] == 'BUY' else "#ff3333"
                    st.markdown(f"""
                    <div class="stock-card {color_cls}">
                        <h3 style="color:{t_col}; margin:0;">{s_trade['Signal']}</h3>
                        <p style="margin:5px 0; color:#8b949e;">Confidence: >85% (Vol Surge)</p>
                        <h4 style="margin:5px 0; color:#f5f5f5;">ENTRY: ₹{s_trade['Entry']}</h4>
                        <h4 style="margin:5px 0; color:#00ff66;">TARGET: ₹{s_trade['Target']}</h4>
                        <h4 style="margin:0; color:#ff3333;">SL: ₹{s_trade['StopLoss']}</h4>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="stock-card">
                        <h3 style="color:#f5f5f5; margin:0;">{name}</h3>
                        <p style="margin:5px 0; color:#8b949e;">Market Sideways. Wait ⏳</p>
                    </div>
                    """, unsafe_allow_html=True)
            col_idx += 1

# ------------------------------------------------------------------------------
# PAGE 3: PERMANENT HISTORY RECORD
# ------------------------------------------------------------------------------
elif menu == "📖 ALL-TIME HISTORY":
    st.markdown("<h2 style='color:#f5f5f5;'>📖 ALL-TIME TRADE RECORDS</h2>", unsafe_allow_html=True)
    st.write("यहाँ आपकी सारी एंट्रीज़ हमेशा के लिए सेव रहेंगी, ताकि आप एक्यूरेसी नाप सकें।")
    
    if os.path.exists(HISTORY_FILE):
        history_df = pd.read_csv(HISTORY_FILE)
        st.dataframe(history_df.style.apply(lambda x: ['background-color: #021a0d; color: #00ff66' if 'PROFIT' in val else 'background-color: #1a0202; color: #ff3333' if 'LOSS' in val else '' for val in x], subset=['Result']), use_container_width=True)
        
        # Calculate Accuracy
        total = len(history_df)
        wins = len(history_df[history_df['Result'].str.contains('PROFIT', na=False)])
        accuracy = round((wins/total)*100, 2) if total > 0 else 0
        st.success(f"🏆 System Accuracy: {accuracy}% (Total Trades: {total})")
    else:
        st.info("Abhi tak koi trade Target ya SL tak nahi pahucha hai. Data aate hi yahan save ho jayega.")

# ==============================================================================
# FAST AUTO-REFRESH LOGIC (हर 5 सेकंड)
# ==============================================================================
# नोट: Yahoo Finance फ्री API है। अगर 1-1 सेकंड करेंगे तो ब्लॉक हो जाएंगे।
# इसलिए 4-5 सेकंड सबसे बेस्ट और फास्ट है!
time.sleep(5) 
st.rerun()
