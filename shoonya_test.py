import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import os

# ==============================================================================
# 1. DUAL TRADE HISTORY LOGGERS 
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
        return pd.read_csv(filename).sort_index(ascending=False)
    return pd.DataFrame()

# ==============================================================================
# 2. INTRADAY QUANT ENGINE (1-Minute Scalping)
# ==============================================================================
def calculate_intraday(df, symbol):
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

    df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
    
    if 'Volume' in df.columns and df['Volume'].sum() > 0:
        df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['Cumulative_VP'] = (df['Typical_Price'] * df['Volume']).cumsum()
        df['Cumulative_Vol'] = df['Volume'].cumsum()
        df['Baseline'] = df['Cumulative_VP'] / (df['Cumulative_Vol'] + 1e-10) 
    else:
        df['Baseline'] = df['Close'].ewm(span=50, adjust=False).mean() 

    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['RSI_14'] = 100 - (100 / (1 + rs))

    df['AI_Score'], df['Signal'], df['Entry'], df['Target'], df['StopLoss'], df['Status'] = 0, 'WAIT ⏳', 0.0, 0.0, 0.0, ""
    active_trade = None
    is_nifty = "NSEI" in symbol
    
    for i in range(20, len(df)):
        score = 0
        curr_c = round(float(df['Close'].iloc[i]), 2)
        baseline_val = float(df['Baseline'].iloc[i])
        timestamp = df.index[i].strftime("%d-%b %H:%M")
        
        # Crossover Logic
        if df['EMA_9'].iloc[i] > df['EMA_21'].iloc[i] and curr_c > baseline_val:
            score += 40  
            if df['RSI_14'].iloc[i] > 55: score += 45
            trend_dir = 1
        elif df['EMA_9'].iloc[i] < df['EMA_21'].iloc[i] and curr_c < baseline_val:
            score += 40 
            if df['RSI_14'].iloc[i] < 45: score += 45
            trend_dir = -1
        else:
            score, trend_dir = 0, 0
            
        df.at[df.index[i], 'AI_Score'] = score
        
        if active_trade is not None:
            df.at[df.index[i], 'Signal'] = active_trade['Signal']
            df.at[df.index[i], 'Entry'] = active_trade['Entry']
            df.at[df.index[i], 'Target'] = active_trade['Target']
            df.at[df.index[i], 'StopLoss'] = active_trade['StopLoss']
            
            trade_closed = False
            status_msg = ""
            
            if active_trade['Direction'] == 'LONG':
                if curr_c >= active_trade['Target']: status_msg, trade_closed = "🎯 TARGET HIT (+PROFIT)", True
                elif curr_c <= active_trade['StopLoss']: status_msg, trade_closed = "🛑 SL HIT (-LOSS)", True
            elif active_trade['Direction'] == 'SHORT':
                if curr_c <= active_trade['Target']: status_msg, trade_closed = "🎯 TARGET HIT (+PROFIT)", True
                elif curr_c >= active_trade['StopLoss']: status_msg, trade_closed = "🛑 SL HIT (-LOSS)", True
            
            if trade_closed:
                df.at[df.index[i], 'Status'] = status_msg
                trade_data = {"Time": timestamp, "Asset": "NIFTY 50" if is_nifty else symbol.replace(".NS", ""), "Type": active_trade['Type'], "Entry Price": active_trade['Entry'], "Exit Price": curr_c, "Result": status_msg}
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
                
                active_trade = {'Type': t_type, 'Signal': sig, 'Entry': curr_c, 'Target': round(tgt, 2), 'StopLoss': round(sl, 2), 'Direction': direction}
                df.at[df.index[i], 'Signal'], df.at[df.index[i], 'Entry'], df.at[df.index[i], 'Target'], df.at[df.index[i], 'StopLoss'] = active_trade['Signal'], active_trade['Entry'], active_trade['Target'], active_trade['StopLoss']

    return df, active_trade

# ==============================================================================
# 3. SWING TRADING ENGINE (3-4 Days Momentum Scanner)
# ==============================================================================
def scan_swing_stocks(tickers):
    results = []
    for sym in tickers:
        try:
            # 3 महीने का डेली डेटा ला रहे हैं (Swing के लिए)
            df = yf.download(sym, period='3mo', interval='1d', progress=False)
            if df.empty or len(df) < 50: continue
            
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            
            df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
            df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
            
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / (loss + 1e-10)
            df['RSI'] = 100 - (100 / (1 + rs))
            df['Vol_Avg'] = df['Volume'].rolling(20).mean()
            
            last = df.iloc[-1]
            c = round(float(last['Close']), 2)
            
            # SWING CONDITIONS (3-4 din tak upar jane wale)
            is_uptrend = c > last['EMA_20'] > last['EMA_50']  # Golden Crossover
            is_momentum = last['RSI'] > 60                    # Strong Buying
            is_vol_surge = last['Volume'] > (1.5 * last['Vol_Avg']) # Smart Money Entry
            
            if is_uptrend and is_momentum and is_vol_surge:
                results.append({
                    "Stock": sym.replace('.NS', ''),
                    "Entry (LTP)": c,
                    "Target (4%)": round(c * 1.04, 2),
                    "StopLoss (2%)": round(c * 0.98, 2),
                    "RSI": round(last['RSI'], 1),
                    "Status": "🚀 STRONG BUY"
                })
        except: pass
    return results

# ==============================================================================
# 4. UI SETUP (Sidebar हमेशा खुला रहेगा)
# ==============================================================================
st.set_page_config(page_title="Scalper Pro AI v7.0", layout="wide", initial_sidebar_state="expanded")

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
    </style>
    """, unsafe_allow_html=True)

st.sidebar.markdown("<h2 style='text-align: center; font-weight: 700;'>SCALPER PRO <br><span style='color:#deff9a;'>AI v7.0</span></h2>", unsafe_allow_html=True)
st.sidebar.markdown("<hr style='border-color:#1f293d;'>", unsafe_allow_html=True)

# 3 मेनू ऑप्शंस
menu = st.sidebar.radio("Navigation Menu", ["⚡ NIFTY OPTIONS (Intraday)", "📡 STOCK RADAR (Intraday)", "🚀 SWING TRADING (3-4 Days)"])

# ------------------------------------------------------------------------------
# PAGE 1: NIFTY OPTIONS
# ------------------------------------------------------------------------------
if menu == "⚡ NIFTY OPTIONS (Intraday)":
    st.markdown("<h2 style='color:#f5f5f5;'>⚡ NIFTY 50 OPTIONS TERMINAL</h2>", unsafe_allow_html=True)
    try:
        data = yf.download('^NSEI', period='1d', interval='1m', progress=False)
        if not data.empty:
            df, active_trade = calculate_intraday(data, '^NSEI')
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            curr_p = round(float(df['Close'].iloc[-1]), 2)
            open_p = round(float(df['Open'].iloc[0]), 2)
            baseline_val = round(float(last['Baseline']), 2)
            
            play_sound = False
            
            if active_trade is not None:
                cmd_class = "cmd-hold"
                cmd_text = f"⏳ HOLD : [{active_trade['Type']}] active hai. Spot Target (₹{active_trade['Target']}) ka wait karein."
            elif last['AI_Score'] >= 85:
                cmd_class = "cmd-buy-c" if "CE" in last['Signal'] else "cmd-buy-p"
                cmd_text = f"🚀 {last['Signal']} NOW! Fast Momentum Detected."
                if prev['AI_Score'] < 85: play_sound = True
            else:
                cmd_class = "cmd-wait"
                cmd_text = "✋ WAIT : Market Sideways hai ya Trend weak hai."
            
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

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Price', line=dict(color='#00ffff', width=2.5)))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_9'], name='9 EMA (Fast)', line=dict(color='#00ff66', width=1)))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_21'], name='21 EMA (Slow)', line=dict(color='#ff3333', width=1)))
            fig.add_trace(go.Scatter(x=df.index, y=df['Baseline'], name='Baseline', line=dict(color='#deff9a', width=2, dash='dash')))
            fig.update_layout(template='plotly_dark', paper_bgcolor='#05070a', plot_bgcolor='#05070a', height=450, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("<hr style='border-color:#1f293d;'><h3 style='color:#deff9a;'>📖 NIFTY OPTIONS LOG</h3>", unsafe_allow_html=True)
            n_hist = load_history(is_nifty=True)
            if not n_hist.empty: st.dataframe(n_hist.style.apply(lambda x: ['background-color: #021a0d; color: #00ff66' if 'PROFIT' in str(val) else 'background-color: #1a0202; color: #ff3333' if 'LOSS' in str(val) else '' for val in x], subset=['Result']), use_container_width=True)
    except Exception as e:
        st.error(f"Error: {e}")

# ------------------------------------------------------------------------------
# PAGE 2: STOCK RADAR (Intraday)
# ------------------------------------------------------------------------------
elif menu == "📡 STOCK RADAR (Intraday)":
    st.markdown("<h2 style='color:#f5f5f5;'>📡 INTRADAY STOCK RADAR (1-Min)</h2>", unsafe_allow_html=True)
    stocks = ["RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "TATAMOTORS.NS", "INFY.NS"]
    cols = st.columns(3)
    col_idx = 0
    
    for stock in stocks:
        try:
            s_data = yf.download(stock, period='1d', interval='1m', progress=False)
            if not s_data.empty:
                s_df, s_trade = calculate_intraday(s_data, stock)
                name = stock.replace(".NS", "")
                curr_p = round(float(s_df['Close'].iloc[-1]), 2)
                vwap_p = round(float(s_df['Baseline'].iloc[-1]), 2)
                
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
        except: pass
    
    st.markdown("<hr style='border-color:#1f293d;'><h3 style='color:#deff9a;'>📖 STOCK TRADE LOG</h3>", unsafe_allow_html=True)
    s_hist = load_history(is_nifty=False)
    if not s_hist.empty: st.dataframe(s_hist.style.apply(lambda x: ['background-color: #021a0d; color: #00ff66' if 'PROFIT' in str(val) else 'background-color: #1a0202; color: #ff3333' if 'LOSS' in str(val) else '' for val in x], subset=['Result']), use_container_width=True)

# ------------------------------------------------------------------------------
# PAGE 3: SWING TRADING (3-4 Days) - NEW
# ------------------------------------------------------------------------------
elif menu == "🚀 SWING TRADING (3-4 Days)":
    st.markdown("<h2 style='color:#f5f5f5;'>🚀 SWING TRADING RADAR (3-4 Days Target)</h2>", unsafe_allow_html=True)
    st.write("यह इंजन 1-Day कैंडलस्टिक पर **Golden Crossover (EMA 20 > EMA 50)** और **Heavy Volume Breakout** ढूँढता है। (डिलीवरी में खरीदें)")
    
    # Top 15 High Momentum / Nifty 50 Stocks
    swing_list = ["RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "TATAMOTORS.NS", 
                  "INFY.NS", "TCS.NS", "BAJFINANCE.NS", "BHARTIARTL.NS", "ITC.NS", 
                  "LT.NS", "M&M.NS", "MARUTI.NS", "SUNPHARMA.NS", "TATASTEEL.NS"]
    
    with st.spinner("Scanning Daily Charts for 3-4 Days Momentum... Please wait."):
        swing_results = scan_swing_stocks(swing_list)
        
    if swing_results:
        st.success("🔥 High Momentum Stocks Found!")
        df_swing = pd.DataFrame(swing_results)
        st.dataframe(df_swing, use_container_width=True)
    else:
        st.info("📉 Abhi market mein koi perfect Swing Breakout nahi mila. Kal dubara check karein.")

# ==============================================================================
# REFRESH LOGIC
# ==============================================================================
# Swing tab par bar-bar refresh ki zaroorat nahi hoti, but intraday ke liye 8 seconds set kiya hai
time.sleep(8) 
st.rerun()
