import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# ==========================================
# 1. AI MULTI-CONFIRMATION ENGINE & QUANT LOGIC
# ==========================================
def calculate_ai_score_and_levels(df, is_stock=False):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # A. 20 EMA Calculation
    df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()

    # B. RSI 14 Calculation
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['RSI_14'] = 100 - (100 / (1 + rs))

    # C. ATR 14 & Volatility Expansion Check
    high = df['High'].squeeze()
    low = df['Low'].squeeze()
    close = df['Close'].squeeze()
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['ATR_14'] = tr.rolling(window=14).mean()
    df['ATR_Expanding'] = df['ATR_14'] > df['ATR_14'].shift(1)

    # D. Supertrend (3, 10) Logic
    atr_10 = tr.rolling(window=10).mean()
    hl2 = (high + low) / 2
    final_ub = hl2 + (3 * atr_10)
    final_lb = hl2 - (3 * atr_10)
    trend = np.ones(len(df))
    
    # Fast list conversion for speed optimization
    f_ub = final_ub.tolist()
    f_lb = final_lb.tolist()
    c_list = close.tolist()
    
    for i in range(1, len(df)):
        if not (f_ub[i] < f_ub[i-1] or c_list[i-1] > f_ub[i-1]): f_ub[i] = f_ub[i-1]
        if not (f_lb[i] > f_lb[i-1] or c_list[i-1] < f_lb[i-1]): f_lb[i] = f_lb[i-1]
        if trend[i-1] == 1 and c_list[i] < f_lb[i]: trend[i] = -1
        elif trend[i-1] == -1 and c_list[i] > f_ub[i]: trend[i] = 1
        else: trend[i] = trend[i-1]
        
    df['Trend'] = trend

    # E. AI CONFIRMATION SCORE (0 - 100)
    df['AI_Score'] = 0
    df['Signal'] = 'WAIT ⏳'
    df['Entry'] = 0.0
    df['Target'] = 0.0
    df['StopLoss'] = 0.0

    for i in range(14, len(df)):
        score = 0
        curr_close = round(c_list[i], 2)
        curr_rsi = df['RSI_14'].iloc[i]
        curr_atr = df['ATR_14'].iloc[i]
        is_atr_expanding = df['ATR_Expanding'].iloc[i]
        
        # 🟢 CALL BIAS SCORING
        if trend[i] == 1:
            score += 30  # Trend alignment
            if c_list[i] > df['EMA_20'].iloc[i]: score += 30  # EMA confirmation
            if curr_rsi > 60: score += 25  # Momentum check
            if is_atr_expanding: score += 15  # Volatility check
            
            if score >= 85:
                df.at[df.index[i], 'Signal'] = '🟢 AI CALL ACTION'
                df.at[df.index[i], 'AI_Score'] = score
                df.at[df.index[i], 'Entry'] = curr_close
                df.at[df.index[i], 'Target'] = round(curr_close + (2 * curr_atr), 2)
                df.at[df.index[i], 'StopLoss'] = round(curr_close - (1 * curr_atr), 2)
                
        # 🔴 PUT BIAS SCORING
        elif trend[i] == -1:
            score += 30  # Trend alignment
            if c_list[i] < df['EMA_20'].iloc[i]: score += 30  # EMA confirmation
            if curr_rsi < 40: score += 25  # Momentum check
            if is_atr_expanding: score += 15  # Volatility check
            
            if score >= 85:
                df.at[df.index[i], 'Signal'] = '🔴 AI PUT ACTION'
                df.at[df.index[i], 'AI_Score'] = score
                df.at[df.index[i], 'Entry'] = curr_close
                df.at[df.index[i], 'Target'] = round(curr_close - (2 * curr_atr), 2)
                df.at[df.index[i], 'StopLoss'] = round(curr_close + (1 * curr_atr), 2)
                
        if df['AI_Score'].iloc[i] == 0:
            df.at[df.index[i], 'AI_Score'] = score

    return df

# ==========================================
# 2. PREMIUM DIGITAL UI/UX DESIGN (Futuristic Dark)
# ==========================================
st.set_page_config(page_title="Pinnacle Quant Station", layout="wide")

# Pure Black (#05070a) and Futuristic Neon Themes via CSS
st.markdown("""
    <style>
    .stApp { background-color: #05070a; color: #ffffff; font-family: 'Courier New', monospace; }
    div[data-testid="stSidebar"] { background-color: #090d16 !important; border-right: 1px solid #1f293d; }
    
    /* Neon Flashing Animations */
    @keyframes flash-green { 0%, 100% { border-color: #00ff66; box-shadow: 0 0 10px #00ff66; } 50% { border-color: #023c1a; box-shadow: none; } }
    @keyframes flash-red { 0%, 100% { border-color: #ff3333; box-shadow: 0 0 10px #ff3333; } 50% { border-color: #420c0c; box-shadow: none; } }
    
    .ai-card { padding: 25px; border-radius: 12px; text-align: center; margin-bottom: 20px; border: 2px solid; }
    .ai-call { background-color: #021a0d; color: #00ff66; animation: flash-green 2s infinite; }
    .ai-put { background-color: #1a0202; color: #ff3333; animation: flash-red 2s infinite; }
    .ai-wait { background-color: #0d1117; color: #8b949e; border-color: #30363d; }
    
    .digital-title { font-size: 28px; font-weight: bold; letter-spacing: 2px; }
    .digital-metrics { font-size: 22px; margin-top: 15px; font-weight: bold; color: #ffffff; }
    .score-badge { background-color: #1f293d; padding: 5px 15px; border-radius: 20px; font-size: 16px; color: #00ffff; }
    </style>
    """, unsafe_allow_html=True)

# 📡 EMBEDDED LIGHTWEIGHT AUDIO ALERT (Sharp Notification Beep)
audio_beep_html = """
    <audio autoplay>
        <source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-500.wav" type="audio/wav">
    </audio>
    """

# Sidebar Navigation Grid
st.sidebar.markdown("# 🧠 QUANT SECTOR")
page_selection = st.sidebar.radio("पेज का चयन करें:", ["⚡ NIFTY AI PREDICTIVE STATION", "📡 ADVANCED MOMENTUM RADAR"])
st.sidebar.markdown("---")

# ------------------------------------------
# SECTOR 1: NIFTY AI PREDICTIVE STATION
# ------------------------------------------
if page_selection == "⚡ NIFTY AI PREDICTIVE STATION":
    st.title("⚡ NIFTY 50 AI PREDICTIVE QUANT STATION")
    st.markdown("---")
    
    try:
        # Fetching 1-Minute Candle Data
        with st.spinner("Fetching Real-Time Institutional Feed..."):
            nifty_data = yf.download(tickers='^NSEI', period='1d', interval='1m', progress=False)
            
        if not nifty_data.empty:
            analyzed_data = calculate_ai_score_and_levels(nifty_data, is_stock=False)
            latest_row = analyzed_data.iloc[-1]
            current_signal = latest_row['Signal']
            ai_score = latest_row['AI_Score']
            latest_close = round(analyzed_data['Close'].squeeze().iloc[-1].item(), 2)
            
            col1, col2 = st.columns([1, 2])
            with col1:
                st.metric(label="📊 NIFTY 50 INDEX INDEX", value=f"₹{latest_close}")
                st.markdown(f"<p style='text-align:center;'>AI Confidence Score: <span class='score-badge'>{ai_score}%</span></p>", unsafe_allow_html=True)
                
            with col2:
                # 🧠 AI Prediction Cards logic with 85%+ validation
                if "CALL" in current_signal and ai_score >= 85:
                    st.markdown(audio_beep_html, unsafe_allow_html=True)  # Trigger sound
                    st.markdown(f"""
                    <div class="ai-card ai-call">
                        <div class="digital-title">💥 SYSTEM ACTION: {current_signal} ({ai_score}% CONFIDENCE)</div>
                        <div class="digital-metrics">🛫 ENTRY: ₹{latest_row['Entry']} | 🎯 TARGET: ₹{latest_row['Target']} | 🛑 SL: ₹{latest_row['StopLoss']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                elif "PUT" in current_signal and ai_score >= 85:
                    st.markdown(audio_beep_html, unsafe_allow_html=True)  # Trigger sound
                    st.markdown(f"""
                    <div class="ai-card ai-put">
                        <div class="digital-title">🔥 SYSTEM ACTION: {current_signal} ({ai_score}% CONFIDENCE)</div>
                        <div class="digital-metrics">🛫 ENTRY: ₹{latest_row['Entry']} | 🎯 TARGET: ₹{latest_row['Target']} | 🛑 SL: ₹{latest_row['StopLoss']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="ai-card ai-wait">
                        <div class="digital-title">⏳ AI ENGINE STATUS: MONITORING SCALPING RANGES</div>
                        <div class="digital-metrics" style="color:#6e7681; font-size:16px;">Current Signals score ({ai_score}%) below institutional threshold (85%). Waiting for Multi-Confirmation.</div>
                    </div>
                    """, unsafe_allow_html=True)
            
            # High-tech Plotly Graph
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=analyzed_data.index, y=analyzed_data['Close'].squeeze(), mode='lines', name='Price', line=dict(color='#00ffff', width=2)))
            fig.add_trace(go.Scatter(x=analyzed_data.index, y=analyzed_data['EMA_20'].squeeze(), mode='lines', name='20 EMA', line=dict(color='#ffaa00', dash='dot')))
            fig.update_layout(template='plotly_dark', paper_bgcolor='#05070a', plot_bgcolor='#05070a', margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
            
            # Logs Grid
            st.markdown("### 📋 AI Quant Logs (Last 15 Bars)")
            st.dataframe(analyzed_data[['Close', 'RSI_14', 'ATR_14', 'AI_Score', 'Signal', 'Entry', 'Target', 'StopLoss']].tail(15).sort_index(ascending=False), use_container_width=True)
            
    except Exception as e:
        st.error(f"Sync Interrupted: {e}")

# ------------------------------------------
# SECTOR 2: ADVANCED MOMENTUM RADAR (Screener Grid)
# ------------------------------------------
else:
    st.title("📡 REAL-TIME INSTI-MOMENTUM RADAR GRID")
    st.markdown("---")
    st.markdown("### ⚡ AI Breakout Radar (Showing >85% Score Conviction Only)")
    
    watchlist = ["RELIANCE.NS", "SBIN.NS", "TATAMOTORS.NS", "TCS.NS", "HDFCBANK.NS"]
    radar_records = []
    play_sound = False
    
    with st.spinner("Executing High-Speed Watchlist Multi-Scanning..."):
        for stock in watchlist:
            try:
                s_feed = yf.download(tickers=stock, period='1d', interval='1m', progress=False)
                if not s_feed.empty:
                    s_an = calculate_ai_score_and_levels(s_feed, is_stock=True)
                    s_last = s_an.iloc[-1]
                    s_score = s_last['AI_Score']
                    s_sig = s_last['Signal']
                    
                    # Core Strict Filter: Only allow 85%+ confirmed trends into the dashboard
                    if s_score >= 85 and ('BUY' in s_sig or 'SELL' in s_sig):
                        play_sound = True
                        radar_records.append({
                            "📌 INSTRUMENT": stock.replace('.NS', ''),
                            "💰 LIVE PRICE": f"₹{round(s_an['Close'].squeeze().iloc[-1].item(), 2)}",
                            "🧠 AI CONVICTION": f"{s_score}%",
                            "🚨 POSITION SIGNAL": s_sig,
                            "🛫 QUANT ENTRY": f"₹{s_last['Entry']}",
                            "🎯 QUANT TARGET": f"₹{s_last['Target']}",
                            "🛑 QUANT STOPLOSS": f"₹{s_last['StopLoss']}"
                        })
            except:
                pass
                
    # Sound notification engine trigger
    if play_sound:
        st.markdown(audio_beep_html, unsafe_allow_html=True)
        
    if radar_records:
        st.dataframe(pd.DataFrame(radar_records), use_container_width=True)
    else:
        st.info("⏳ SCANNERS OPTIMIZED: No stocks have crossed the ultra-strict 85% AI validation barrier yet. Preventing false breakout entries.")
        
    # --- Single Chart Deep Dive Sync ---
    st.markdown("---")
    st.markdown("### 🔍 Individual Asset Deep Scan View")
    st.sidebar.markdown("### ⚙️ DEEP SCAN CONFIG")
    deep_asset = st.sidebar.selectbox("Deep Scan के लिए स्टॉक चुनें:", watchlist)
    
    try:
        d_feed = yf.download(tickers=deep_asset, period='1d', interval='1m', progress=False)
        if not d_feed.empty:
            d_an = calculate_ai_score_and_levels(d_feed, is_stock=True)
            d_last = d_an.iloc[-1]
            
            col3, col4 = st.columns(2)
            with col3:
                st.metric(label=f"📊 {deep_asset.replace('.NS','')}", value=f"₹{round(d_an['Close'].squeeze().iloc[-1].item(), 2)}")
            with col4:
                st.write(f"**AI Confidence:** {d_last['AI_Score']}% | **Current Trend:** {d_last['Signal']}")
                
            fig_d = go.Figure()
            fig_d.add_trace(go.Scatter(x=d_an.index, y=d_an['Close'].squeeze(), mode='lines', name='Price', line=dict(color='#00bfff', width=2)))
            fig_d.add_trace(go.Scatter(x=d_an.index, y=d_an['EMA_20'].squeeze(), mode='lines', name='20 EMA', line=dict(color='#ffaa00', dash='dot')))
            fig_d.update_layout(template='plotly_dark', paper_bgcolor='#05070a', plot_bgcolor='#05070a', margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_d, use_container_width=True)
    except Exception as e:
        st.error(f"Deep Scan Asset Error: {e}")