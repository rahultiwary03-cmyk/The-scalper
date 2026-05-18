import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time

# ==============================================================================
# 1. ADVANCED QUANT ENGINE V3.1 (CE/PE STRIKE CALCULATION & LIVE COMMANDS)
# ==============================================================================
def calculate_ai_v2(df, symbol):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Core Indicators
    df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
    
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
    trade_history = [] 
    
    for i in range(20, len(df)):
        score = 0
        curr_c = round(float(c_list[i]), 2)
        atr = df['ATR_14'].iloc[i]
        timestamp = df.index[i].strftime("%H:%M")
        
        # Scoring
        if trend[i] == 1: 
            score += 30
            if curr_c > df['EMA_20'].iloc[i]: score += 30
            if df['RSI_14'].iloc[i] > 60: score += 25
            if tr.iloc[i] > df['ATR_14'].iloc[i]: score += 15
        else:
            score += 30
            if curr_c < df['EMA_20'].iloc[i]: score += 30
            if df['RSI_14'].iloc[i] < 40: score += 25
            if tr.iloc[i] > df['ATR_14'].iloc[i]: score += 15
            
        df.at[df.index[i], 'AI_Score'] = score
        
        # Trade Management & Logging
        if active_trade is not None:
            df.at[df.index[i], 'Signal'] = active_trade['Signal']
            df.at[df.index[i], 'Entry'] = active_trade['Entry']
            df.at[df.index[i], 'Target'] = active_trade['Target']
            df.at[df.index[i], 'StopLoss'] = active_trade['StopLoss']
            
            trade_closed = False
            status_msg = ""
            if active_trade['Type'] == 'CE':
                if curr_c >= active_trade['Target']:
                    status_msg, trade_closed = "🎯 TARGET HIT (+50)", True
                elif curr_c <= active_trade['StopLoss']:
                    status_msg, trade_closed = "🛑 SL HIT", True
            elif active_trade['Type'] == 'PE':
                if curr_c <= active_trade['Target']:
                    status_msg, trade_closed = "🎯 TARGET HIT (+50)", True
                elif curr_c >= active_trade['StopLoss']:
                    status_msg, trade_closed = "🛑 SL HIT", True
            
            if trade_closed:
                df.at[df.index[i], 'Status'] = status_msg
                trade_history.append({
                    "Time": timestamp,
                    "Option Strike": active_trade['Option'],
                    "Spot Entry": active_trade['Entry'],
                    "Spot Exit": curr_c,
                    "Spot Target": active_trade['Target'],
                    "Result": status_msg
                })
                active_trade = None 
        else:
            if score >= 85:
                # NAYA FEATURE: ATM Strike Price Calculator (Nearest 50)
                atm_strike = int(round(curr_c / 50) * 50)
                
                if trend[i] == 1:
                    opt_type = 'CE'
                    sig = f'🟢 BUY NIFTY {atm_strike} CE'
                    tgt = curr_c + 50 if "NSEI" in symbol else curr_c + (2 * atr)
                    sl = curr_c - (1.2 * atr)
                else:
                    opt_type = 'PE'
                    sig = f'🔴 BUY NIFTY {atm_strike} PE'
                    tgt = curr_c - 50 if "NSEI" in symbol else curr_c - (2 * atr)
                    sl = curr_c + (1.2 * atr)
                
                active_trade = {
                    'Type': opt_type, 
                    'Option': f'{atm_strike} {opt_type}',
                    'Signal': sig, 
                    'Entry': curr_c, 
                    'Target': round(tgt, 2), 
                    'StopLoss': round(sl, 2)
                }
                
                df.at[df.index[i], 'Signal'] = active_trade['Signal']
                df.at[df.index[i], 'Entry'] = active_trade['Entry']
                df.at[df.index[i], 'Target'] = active_trade['Target']
                df.at[df.index[i], 'StopLoss'] = active_trade['StopLoss']

    return df, trade_history, active_trade

# ==============================================================================
# 2. ULTRA-PROFESSIONAL UI SETUP
# ==============================================================================
st.set_page_config(page_title="Scalper Pro AI", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #05070a; color: #ffffff; }
    [data-testid="stSidebar"] { background-color: #090d16 !important; border-right: 1px solid #1f293d !important; }
    [data-testid="stSidebar"] * { color: #f5f5f5 !important; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    div[data-testid="stMetricValue"] { font-size: 38px; font-weight: 700; color: #00ffff; }
    
    .command-box { padding: 15px; border-radius: 10px; text-align: center; font-weight: bold; font-size: 26px; border: 3px solid; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
    .cmd-wait { background-color: #111827; color: #8b949e; border-color: #1f293d; }
    .cmd-hold { background-color: #3d2600; color: #ffaa00; border-color: #ffaa00; }
    .cmd-buy-c { background-color: #021a0d; color: #00ff66; border-color: #00ff66; }
    .cmd-buy-p { background-color: #1a0202; color: #ff3333; border-color: #ff3333; }
    </style>
    """, unsafe_allow_html=True)

st.sidebar.markdown("<h2 style='text-align: center; font-weight: 700;'>SCALPER PRO <br><span style='color:#deff9a;'>AI v3.1</span></h2>", unsafe_allow_html=True)
st.sidebar.markdown("<hr style='border-color:#1f293d;'>", unsafe_allow_html=True)
menu = st.sidebar.radio("Navigation Menu", ["⚡ LIVE NIFTY STATION"])

if menu == "⚡ LIVE NIFTY STATION":
    st.markdown("<h2 style='color:#f5f5f5;'>⚡ NIFTY 50 AI QUANT STATION</h2>", unsafe_allow_html=True)
    
    data = yf.download('^NSEI', period='1d', interval='1m', progress=False)
    if not data.empty:
        df, trade_history, active_trade = calculate_ai_v2(data, '^NSEI')
        last = df.iloc[-1]
        
        curr_p = round(float(df['Close'].iloc[-1]), 2)
        open_p = round(float(df['Open'].iloc[0]), 2)
        points_change = round(curr_p - open_p, 2)
        
        # ---------------------------------------------------------
        # COMMAND CENTER: CE/PE Strike Recommendations
        # ---------------------------------------------------------
        if active_trade is not None:
            cmd_class = "cmd-hold"
            cmd_text = f"⏳ HOLD POSITION : [{active_trade['Option']}] abhi active hai. Spot Target (₹{active_trade['Target']}) ka wait karein."
        elif last['AI_Score'] >= 85:
            cmd_class = "cmd-buy-c" if "CE" in last['Signal'] else "cmd-buy-p"
            cmd_text = f"🚀 {last['Signal']} NOW! Entry lein."
        else:
            cmd_class = "cmd-wait"
            cmd_text = "✋ WAIT : Market No-Trade Zone mein hai. AI Breakout ka wait karein."
            
        st.markdown(f'<div class="command-box {cmd_class}">{cmd_text}</div>', unsafe_allow_html=True)
        # ---------------------------------------------------------

        c1, c2 = st.columns([1, 2])
        sign = "+" if points_change >= 0 else ""
        c1.metric(label="📊 NIFTY 50 SPOT", value=f"₹{curr_p:,}", delta=f"{sign}{points_change} pts Today")
        
        with c2:
            if active_trade is not None:
                color = "#00ff66" if active_trade['Type'] == 'CE' else "#ff3333"
                st.markdown(f"""
                <div style="border-left: 8px solid {color}; padding: 15px; background: #0c111d; border-radius: 8px;">
                    <h3 style="margin:0; color:{color};">⚡ ACTION: {active_trade['Signal']}</h3>
                    <p style="font-size:20px; margin:5px 0; color:#f5f5f5;"><b>SPOT ENTRY:</b> ₹{active_trade['Entry']} | <span style="color:#00ff66;"><b>🎯 SPOT TARGET:</b> ₹{active_trade['Target']}</span> | <span style="color:#ff3333;"><b>🛑 SPOT SL:</b> ₹{active_trade['StopLoss']}</span></p>
                </div>
                """, unsafe_allow_html=True)
            elif last['Status'] != "":
                st.info(f"Last Action: {last['Status']}")

        # Chart
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Live Price', line=dict(color='#00ffff', width=2.5)))
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_20'], name='20 EMA', line=dict(color='#ffaa00', width=1.5, dash='dot')))
        fig.update_layout(template='plotly_dark', paper_bgcolor='#05070a', plot_bgcolor='#05070a', height=400, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

        # ---------------------------------------------------------
        # TODAY'S TRADE HISTORY
        # ---------------------------------------------------------
        st.markdown("<h3 style='color:#deff9a; margin-top:20px;'>📖 Options Trade Log (Spot Basis)</h3>", unsafe_allow_html=True)
        if len(trade_history) > 0:
            history_df = pd.DataFrame(trade_history)
            st.dataframe(history_df, use_container_width=True)
        else:
            st.write("Abhi tak aaj ka koi trade close nahi hua hai.")

# Auto Refresh Every 60 Seconds
time.sleep(60)
st.rerun()
