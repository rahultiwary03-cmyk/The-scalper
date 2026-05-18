import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import os

# ==============================================================================
# 1. PERMANENT TRADE HISTORY LOGGER
# ==============================================================================
HISTORY_FILE = "trade_record_book.csv"

def save_trade_to_csv(trade_data):
    df = pd.DataFrame([trade_data])
    if not os.path.exists(HISTORY_FILE):
        df.to_csv(HISTORY_FILE, index=False)
    else:
        existing = pd.read_csv(HISTORY_FILE)
        is_duplicate = ((existing['Time'] == trade_data['Time']) & (existing['Asset'] == trade_data['Asset'])).any()
        if not is_duplicate:
            df.to_csv(HISTORY_FILE, mode='a', header=False, index=False)

# ==============================================================================
# 2. INSTITUTIONAL QUANT ENGINE V5.0 (VWAP + 200 EMA + SENTIMENT)
# ==============================================================================
def calculate_ai_v5(df, symbol):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # 1. Intraday VWAP (असली मार्केट सेंटिमेंट)
    df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
    df['VP'] = df['Typical_Price'] * df['Volume']
    df['Cumulative_VP'] = df['VP'].cumsum()
    df['Cumulative_Vol'] = df['Volume'].cumsum()
    df['VWAP'] = df['Cumulative_VP'] / (df['Cumulative_Vol'] + 1e-10)

    # 2. Major & Minor Trends
    df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean() # लॉन्ग टर्म ट्रेंड
    
    # 3. RSI & ATR
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['RSI_14'] = 100 - (100 / (1 + rs))

    high, low, close = df['High'].squeeze(), df['Low'].squeeze(), df['Close'].squeeze()
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    df['ATR_14'] = tr.rolling(window=14).mean()

    df['AI_Score'], df['Signal'], df['Entry'], df['Target'], df['StopLoss'], df['Status'] = 0, 'WAIT ⏳', 0.0, 0.0, 0.0, ""

    active_trade = None
    today_trades = []
    
    # कम से कम 200 कैंडल चाहिए EMA_200 के लिए, इसलिए लूप को थोड़ा सुरक्षित रखते हैं
    start_idx = 20 if len(df) > 20 else 1
    
    for i in range(start_idx, len(df)):
        score = 0
        curr_c = round(float(close.iloc[i]), 2)
        atr = float(df['ATR_14'].iloc[i])
        vwap_val = float(df['VWAP'].iloc[i])
        ema200_val = float(df['EMA_200'].iloc[i])
        timestamp = df.index[i].strftime("%d-%b %H:%M")
        
        # --- STRICT INSTITUTIONAL SCORING LOGIC ---
        # CALL/BUY Zone (तभी खरीदें जब मार्केट VWAP और 200 EMA के ऊपर हो)
        if curr_c > vwap_val and curr_c > ema200_val:
            score += 40  # मेजर सेंटिमेंट बुलिश है
            if curr_c > df['EMA_20'].iloc[i]: score += 20
            if df['RSI_14'].iloc[i] > 55: score += 20
            if 'Volume' in df.columns and df['Volume'].iloc[i] > df['Volume'].rolling(20).mean().iloc[i]: score += 20
            trend_dir = 1
            
        # PUT/SELL Zone (तभी बेचें जब मार्केट VWAP और 200 EMA के नीचे हो)
        elif curr_c < vwap_val and curr_c < ema200_val:
            score += 40  # मेजर सेंटिमेंट बियरिश है
            if curr_c < df['EMA_20'].iloc[i]: score += 20
            if df['RSI_14'].iloc[i] < 45: score += 20
            if 'Volume' in df.columns and df['Volume'].iloc[i] > df['Volume'].rolling(20).mean().iloc[i]: score += 20
            trend_dir = -1
        else:
            # नो-ट्रेड ज़ोन (मार्केट कन्फ्यूज़ है)
            score = 0
            trend_dir = 0
            
        df.at[df.index[i], 'AI_Score'] = score
        
        # Trade Exit Logic
        if active_trade is not None:
            df.at[df.index[i], 'Signal'] = active_trade['Signal']
            df.at[df.index[i], 'Entry'] = active_trade['Entry']
            df.at[df.index[i], 'Target'] = active_trade['Target']
            df.at[df.index[i], 'StopLoss'] = active_trade['StopLoss']
            
            trade_closed = False
            status_msg = ""
            
            # Target / SL Checking
            if active_trade['Direction'] == 'LONG':
                if curr_c >= active_trade['Target']:
                    status_msg, trade_closed = "🎯 TARGET HIT (PROFIT)", True
                elif curr_c <= active_trade['StopLoss']:
                    status_msg, trade_closed = "🛑 SL HIT (LOSS)", True
            elif active_trade['Direction'] == 'SHORT':
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
                save_trade_to_csv(trade_data)
                active_trade = None 
        else:
            # 85% से ऊपर स्कोर होने पर ही पक्की एंट्री
            if score >= 85 and trend_dir != 0:
                atm_strike = int(round(curr_c / 50) * 50)
                
                if trend_dir == 1:
                    t_type = f'{atm_strike} CE' if "NSEI" in symbol else 'BUY'
                    sig = f'🟢 BUY NIFTY {t_type}' if "NSEI" in symbol else f'🟢 BUY {symbol.replace(".NS","")}'
                    tgt = curr_c + 50 if "NSEI" in symbol else curr_c + (2 * atr)
                    sl = curr_c - (1 * atr) # Tight SL
                    direction = 'LONG'
                else:
                    t_type = f'{atm_strike} PE' if "NSEI" in symbol else 'SELL'
                    sig = f'🔴 BUY NIFTY {t_type}' if "NSEI" in symbol else f'🔴 SELL {symbol.replace(".NS","")}'
                    tgt = curr_c - 50 if "NSEI" in symbol else curr_c - (2 * atr)
                    sl = curr_c + (1 * atr) # Tight SL
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

    return df, today_trades, active_trade

# ==============================================================================
# 3. PROFESSIONAL UI SETUP
# ==============================================================================
st.set_page_config(page_title="Scalper Pro AI v5.0", layout="wide")

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

st.sidebar.markdown("<h2 style='text-align: center; font-weight: 700;'>SCALPER PRO <br><span style='color:#deff9a;'>AI v5.0</span></h2>", unsafe_allow_html=True)
st.sidebar.markdown("<hr style='border-color:#1f293d;'>", unsafe_allow_html=True)
menu = st.sidebar.radio("Navigation Menu", ["⚡ LIVE NIFTY STATION", "📡 LIVE STOCK RADAR", "📖 ALL-TIME HISTORY"])

# ------------------------------------------------------------------------------
# PAGE 1: NIFTY 50 STATION
# ------------------------------------------------------------------------------
if menu == "⚡ LIVE NIFTY STATION":
    st.markdown("<h2 style='color:#f5f5f5;'>⚡ NIFTY 50 AI QUANT STATION</h2>", unsafe_allow_html=True)
    try:
        data = yf.download('^NSEI', period='1d', interval='1m', progress=False)
        if not data.empty:
            df, _, active_trade = calculate_ai_v5(data, '^NSEI')
            last = df.iloc[-1]
            
            curr_p = round(float(df['Close'].iloc[-1]), 2)
            open_p = round(float(df['Open'].iloc[0]), 2)
            
            # VWAP Sentiment Display
            vwap_val = round(float(last['VWAP']), 2)
            sentiment = "🟢 BULLISH (Above VWAP)" if curr_p > vwap_val else "🔴 BEARISH (Below VWAP)"
            
            if active_trade is not None:
                cmd_class = "cmd-hold"
                cmd_text = f"⏳ HOLD : [{active_trade['Signal']}] active hai. Spot Target (₹{active_trade['Target']}) ka wait karein."
            elif last['AI_Score'] >= 85:
                cmd_class = "cmd-buy-c" if "CE" in last['Signal'] else "cmd-buy-p"
                cmd_text = f"🚀 {last['Signal']} NOW! Institutional Breakout Detected."
            else:
                cmd_class = "cmd-wait"
                cmd_text = f"✋ WAIT : Market {sentiment} hai par Breakout nahi hai."
                
            st.markdown(f'<div class="command-box {cmd_class}">{cmd_text}</div>', unsafe_allow_html=True)

            c1, c2, c3 = st.columns([1.5, 1, 2])
            pts = round(curr_p - open_p, 2)
            c1.metric("📊 NIFTY 50 SPOT", f"₹{curr_p:,}", f"{'+' if pts>=0 else ''}{pts} pts Today")
            c2.metric("🎯 INSTITUTIONAL VWAP", f"₹{vwap_val:,}")
            
            with c3:
                if active_trade is not None:
                    color = "#00ff66" if active_trade['Direction'] == 'LONG' else "#ff3333"
                    st.markdown(f"""
                    <div style="border-left: 8px solid {color}; padding: 15px; background: #0c111d; border-radius: 8px;">
                        <h3 style="margin:0; color:{color};">⚡ {active_trade['Signal']}</h3>
                        <p style="font-size:18px; margin:5px 0;"><b>SPOT ENTRY:</b> ₹{active_trade['Entry']} | <span style="color:#00ff66;"><b>TARGET:</b> ₹{active_trade['Target']}</span> | <span style="color:#ff3333;"><b>SL:</b> ₹{active_trade['StopLoss']}</span></p>
                    </div>
                    """, unsafe_allow_html=True)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Price', line=dict(color='#00ffff', width=2)))
            fig.add_trace(go.Scatter(x=df.index, y=df['VWAP'], name='VWAP (Sentiment)', line=dict(color='#deff9a', width=2, dash='solid')))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_200'], name='200 EMA (Trend)', line=dict(color='#ff3333', width=1, dash='dot')))
            fig.update_layout(template='plotly_dark', paper_bgcolor='#05070a', plot_bgcolor='#05070a', height=450)
            st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Data fetching error: {e}")

# ------------------------------------------------------------------------------
# PAGE 2: LIVE STOCK RADAR (CLEANED UP)
# ------------------------------------------------------------------------------
elif menu == "📡 LIVE STOCK RADAR":
    st.markdown("<h2 style='color:#f5f5f5;'>📡 LIVE STOCK BREAKOUT RADAR</h2>", unsafe_allow_html=True)
    st.write("VWAP और 200 EMA के आधार पर पक्के स्टॉक सिग्नल्स...")
    
    stocks = ["RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "TATAMOTORS.NS", "INFY.NS"]
    
    cols = st.columns(3)
    col_idx = 0
    
    for stock in stocks:
        try:
            s_data = yf.download(stock, period='1d', interval='1m', progress=False)
            if not s_data.empty:
                s_df, _, s_trade = calculate_ai_v5(s_data, stock)
                name = stock.replace(".NS", "")
                curr_p = round(float(s_df['Close'].iloc[-1]), 2)
                vwap_p = round(float(s_df['VWAP'].iloc[-1]), 2)
                
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

# ------------------------------------------------------------------------------
# PAGE 3: PERMANENT HISTORY RECORD
# ------------------------------------------------------------------------------
elif menu == "📖 ALL-TIME HISTORY":
    st.markdown("<h2 style='color:#f5f5f5;'>📖 ALL-TIME TRADE RECORDS</h2>", unsafe_allow_html=True)
    st.write("VWAP फिल्टर लगने के बाद आपकी नई एक्यूरेसी यहाँ दिखेगी।")
    
    if os.path.exists(HISTORY_FILE):
        history_df = pd.read_csv(HISTORY_FILE)
        # Sort by Time descending
        history_df = history_df.sort_index(ascending=False)
        st.dataframe(history_df.style.apply(lambda x: ['background-color: #021a0d; color: #00ff66' if 'PROFIT' in str(val) else 'background-color: #1a0202; color: #ff3333' if 'LOSS' in str(val) else '' for val in x], subset=['Result']), use_container_width=True)
        
        total = len(history_df)
        wins = len(history_df[history_df['Result'].str.contains('PROFIT', na=False, case=False)])
        accuracy = round((wins/total)*100, 2) if total > 0 else 0
        st.success(f"🏆 System Accuracy: {accuracy}% (Total Trades: {total})")
    else:
        st.info("No trades have been completed yet. Data will appear here automatically.")

# Auto Refresh Every 5 Seconds
time.sleep(5) 
st.rerun()
