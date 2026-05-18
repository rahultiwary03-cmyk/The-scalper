import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# ==========================================
# 1. ADVANCED AI ENGINE v2.0 (50-PT TARGET & REWARD LOGIC)
# ==========================================
def calculate_ai_v2(df, symbol):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # A. Indicators
    df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
    
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['RSI_14'] = 100 - (100 / (1 + rs))

    # ATR for SL Calculation
    high, low, close = df['High'].squeeze(), df['Low'].squeeze(), df['Close'].squeeze()
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    df['ATR_14'] = tr.rolling(window=14).mean()

    # Supertrend (3, 10)
    atr_10 = tr.rolling(window=10).mean()
    hl2 = (high + low) / 2
    f_ub, f_lb = (hl2 + (3 * atr_10)).tolist(), (hl2 - (3 * atr_10)).tolist()
    c_list, trend = close.tolist(), np.ones(len(df))
    
    for i in range(1, len(df)):
        if not (f_ub[i] < f_ub[i-1] or c_list[i-1] > f_ub[i-1]): f_ub[i] = f_ub[i-1]
        if not (f_lb[i] > f_lb[i-1] or c_list[i-1] < f_lb[i-1]): f_lb[i] = f_lb[i-1]
        if trend[i-1] == 1 and c_list[i] < f_lb[i]: trend[i] = -1
        elif trend[i-1] == -1 and c_list[i] > f_ub[i]: trend[i] = 1
        else: trend[i] = trend[i-1]
    df['Trend'] = trend

    # AI Scoring & Dynamic Rewards
    df['AI_Score'] = 0
    df['Signal'] = 'WAIT ⏳'
    df['Entry'], df['Target'], df['StopLoss'], df['Status'] = 0.0, 0.0, 0.0, ""

    for i in range(20, len(df)):
        score = 0
        curr_c = round(c_list[i], 2)
        atr = df['ATR_14'].iloc[i]
        
        # Scoring Logic (Max 100)
        if trend[i] == 1: # CALL
            score += 30 if trend[i] == 1 else 0
            score += 30 if curr_c > df['EMA_20'].iloc[i] else 0
            score += 25 if df['RSI_14'].iloc[i] > 60 else 0
            score += 15 if tr.iloc[i] > df['ATR_14'].iloc[i] else 0
            
            if score >= 85:
                df.at[df.index[i], 'Signal'] = '🟢 AI CALL ACTION'
                df.at[df.index[i], 'Entry'] = curr_c
                # 50 Point Fixed Target for Nifty, ATR for others
                tgt = curr_c + 50 if "NSEI" in symbol else curr_c + (2 * atr)
                df.at[df.index[i], 'Target'] = round(tgt, 2)
                df.at[df.index[i], 'StopLoss'] = round(curr_c - (1.2 * atr), 2)
        
        elif trend[i] == -1: # PUT
            score += 30 if trend[i] == -1 else 0
            score += 30 if curr_c < df['EMA_20'].iloc[i] else 0
            score += 25 if df['RSI_14'].iloc[i] < 40 else 0
            score += 15 if tr.iloc[i] > df['ATR_14'].iloc[i] else 0
            
            if score >= 85:
                df.at[df.index[i], 'Signal'] = '🔴 AI PUT ACTION'
                df.at[df.index[i], 'Entry'] = curr_c
                tgt = curr_c - 50 if "NSEI" in symbol else curr_c - (2 * atr)
                df.at[df.index[i], 'Target'] = round(tgt, 2)
                df.at[df.index[i], 'StopLoss'] = round(curr_c + (1.2 * atr), 2)
        
        df.at[df.index[i], 'AI_Score'] = score
        
        # Live Status Check (Reward Logic)
        if i > 0 and df['Entry'].iloc[i-1] > 0:
            entry_p = df['Entry'].iloc[i-1]
            target_p = df['Target'].iloc[i-1]
            sl_p = df['StopLoss'].iloc[i-1]
            
            if (trend[i-1] == 1 and curr_c >= target_p) or (trend[i-1] == -1 and curr_c <= target_p):
                df.at[df.index[i], 'Status'] = "🏆 TARGET HIT (+50 PTS) 🏆"
            elif (trend[i-1] == 1 and curr_c <= sl_p) or (trend[i-1] == -1 and curr_c >= sl_p):
                df.at[df.index[i], 'Status'] = "🛑 SL HIT (EXIT) 🛑"

    return df

# ==========================================
# 2. ULTRA-PROFESSIONAL UI (BLACK THEME)
# ==========================================
st.set_page_config(page_title="Scalper Pro AI v2.0", layout="wide")

# Hide Streamlit Default UI
st.markdown("""
    <style>
    .stApp { background-color: #05070a; color: #ffffff; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    div[data-testid="stMetricValue"] { font-size: 35px; color: #00ffff; }
    
    /* Reward Badges */
    .reward-box { padding: 20px; border-radius: 15px; text-align: center; font-weight: bold; font-size: 24px; border: 2px solid; }
    .target-hit { background-color: #021a0d; color: #00ff66; border-color: #00ff66; box-shadow: 0 0 20px #00ff66; }
    .sl-hit { background-color: #1a0202; color: #ff3333; border-color: #ff3333; }
    .wait-box { background-color: #090d16; color: #8b949e; border-color: #1f293d; }
    
    .signal-card { border-left: 10px solid; padding: 20px; background: #0c111d; border-radius: 10px; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# Sound Alert
beep_sound = '<audio autoplay><source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-500.wav" type="audio/wav"></audio>'

# Sidebar
st.sidebar.markdown("<h1 style='color:#deff9a;'>Scalper Pro AI v2.0</h1>", unsafe_allow_html=True)
menu = st.sidebar.radio("Navigation", ["⚡ LIVE NIFTY STATION", "📡 MOMENTUM RADAR"])

# ------------------------------------------
# PAGE 1: LIVE NIFTY STATION
# ------------------------------------------
if menu == "⚡ LIVE NIFTY STATION":
    st.markdown("<h2 style='color:#f5f5f5;'>⚡ NIFTY 50 AI QUANT STATION</h2>", unsafe_allow_html=True)
    
    data = yf.download('^NSEI', period='1d', interval='1m', progress=False)
    if not data.empty:
        df = calculate_ai_v2(data, '^NSEI')
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        curr_p = round(df['Close'].iloc[-1].item(), 2)
        score = last['AI_Score']
        
        # UI Top Row
        c1, c2 = st.columns([1, 2])
        c1.metric("NIFTY 50 LIVE", f"₹{curr_p}")
        
        with c2:
            # Reward / Status Message Logic
            if last['Status'] != "":
                st.markdown(f'<div class="reward-box {"target-hit" if "TARGET" in last["Status"] else "sl-hit"}">{last["Status"]}</div>', unsafe_allow_html=True)
                if "TARGET" in last['Status']: st.markdown(beep_sound, unsafe_allow_html=True)
            elif score >= 85:
                st.markdown(beep_sound, unsafe_allow_html=True)
                color = "#00ff66" if "CALL" in last['Signal'] else "#ff3333"
                st.markdown(f"""
                <div class="signal-card" style="border-color:{color};">
                    <h2 style="margin:0; color:{color};">{last['Signal']} ({score}% CONFIDENCE)</h2>
                    <p style="font-size:22px; margin:10px 0;"><b>ENTRY:</b> ₹{last['Entry']} | <b>🎯 TARGET:</b> ₹{last['Target']} | <b>🛑 SL:</b> ₹{last['StopLoss']}</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown('<div class="reward-box wait-box">⏳ MONITORING 85% CONFIDENCE BREAKOUT...</div>', unsafe_allow_html=True)

        # Chart
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Price', line=dict(color='#00ffff', width=2)))
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_20'], name='20 EMA', line=dict(color='#ffaa00', dash='dot')))
        fig.update_layout(template='plotly_dark', paper_bgcolor='#05070a', plot_bgcolor='#05070a', height=450)
        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# PAGE 2: MOMENTUM RADAR (STOCKS)
# ------------------------------------------
else:
    st.markdown("<h2 style='color:#f5f5f5;'>📡 LIVE STOCK MOMENTUM RADAR</h2>", unsafe_allow_html=True)
    watchlist = ["RELIANCE.NS", "SBIN.NS", "TATAMOTORS.NS", "TCS.NS", "HDFCBANK.NS"]
    
    grid_data = []
    for stock in watchlist:
        s_data = yf.download(stock, period='1d', interval='1m', progress=False)
        if not s_data.empty:
            s_df = calculate_ai_v2(s_data, stock)
            s_last = s_df.iloc[-1]
            if s_last['AI_Score'] >= 85:
                grid_data.append({
                    "Stock": stock.replace(".NS",""),
                    "Price": f"₹{round(s_data['Close'].iloc[-1].item(),2)}",
                    "Score": f"{s_last['AI_Score']}%",
                    "Signal": s_last['Signal'],
                    "Entry": s_last['Entry'],
                    "Target": s_last['Target'],
                    "SL": s_last['StopLoss']
                })
    
    if grid_data:
        st.table(pd.DataFrame(grid_data))
    else:
        st.info("No high-conviction (>85%) stocks found in the radar right now.")
