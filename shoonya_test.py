import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import os
from datetime import timedelta

# ==============================================================================
# 1. TRADE HISTORY LOGGERS
# ==============================================================================
NIFTY_HISTORY_FILE = "nifty_trade_book.csv"
STOCK_HISTORY_FILE = "stock_trade_book.csv"

def save_trade(trade_data, is_nifty=False):
    filename = NIFTY_HISTORY_FILE if is_nifty else STOCK_HISTORY_FILE
    df_new = pd.DataFrame([trade_data])
    
    if not os.path.exists(filename):
        df_new.to_csv(filename, index=False)
    else:
        try:
            existing = pd.read_csv(filename)
            if 'Time (IST)' not in existing.columns:
                df_new.to_csv(filename, index=False)
            else:
                is_duplicate = ((existing['Time (IST)'] == trade_data['Time (IST)']) & (existing['Asset'] == trade_data['Asset'])).any()
                if not is_duplicate:
                    df_new.to_csv(filename, mode='a', header=False, index=False)
        except:
            df_new.to_csv(filename, index=False)

def load_history(is_nifty=False):
    filename = NIFTY_HISTORY_FILE if is_nifty else STOCK_HISTORY_FILE
    if os.path.exists(filename):
        try:
            df = pd.read_csv(filename)
            if 'Time (IST)' not in df.columns: return pd.DataFrame()
            return df.sort_index(ascending=False)
        except: pass
    return pd.DataFrame()

# ==============================================================================
# 2. INTRADAY QUANT ENGINE (v11.0 - ULTRA STRICT FILTERS)
# ==============================================================================
def calculate_intraday(df, symbol):
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

    # Core EMAs
    df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean() # MAJOR TREND
    
    if 'Volume' in df.columns and df['Volume'].sum() > 0:
        df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['Cumulative_VP'] = (df['Typical_Price'] * df['Volume']).cumsum()
        df['Cumulative_Vol'] = df['Volume'].cumsum()
        df['Baseline'] = df['Cumulative_VP'] / (df['Cumulative_Vol'] + 1e-10) 
        df['Vol_Avg'] = df['Volume'].rolling(20).mean() # 20 Min Volume Avg
    else:
        df['Baseline'] = df['Close'].ewm(span=50, adjust=False).mean() 
        df['Vol_Avg'] = 1

    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['RSI_14'] = 100 - (100 / (1 + rs))

    df['AI_Score'], df['Signal'], df['Entry'], df['Target'], df['StopLoss'], df['Status'] = 0, 'WAIT ⏳', 0.0, 0.0, 0.0, ""
    active_trade = None
    is_nifty = "NSEI" in symbol
    
    start_idx = 200 if len(df) > 200 else 20 # Need 200 candles for EMA 200
    for i in range(start_idx, len(df)):
        score = 0
        curr_c = round(float(df['Close'].iloc[i]), 2)
        baseline_val = float(df['Baseline'].iloc[i])
        ema200_val = float(df['EMA_200'].iloc[i])
        
        candle_time = df.index[i]
        if candle_time.tz is None: candle_time = candle_time.tz_localize('UTC')
        ist_time = candle_time.tz_convert('Asia/Kolkata')
        timestamp = ist_time.strftime("%d-%b %I:%M %p")
        
        # 🚀 VOLUME SURGE CHECK (Smart Money)
        vol_surge = True
        if 'Volume' in df.columns and df['Volume'].sum() > 0:
            current_vol = float(df['Volume'].iloc[i])
            avg_vol = float(df['Vol_Avg'].iloc[i])
            vol_surge = current_vol > (1.5 * avg_vol) # Volume must be 150% of average
        
        # 🛡️ STRICT INSTITUTIONAL SCORING
        # Buy Setup: Above 200 EMA + Above VWAP + 9/21 Crossover
        if df['EMA_9'].iloc[i] > df['EMA_21'].iloc[i] and curr_c > baseline_val and curr_c > ema200_val:
            score += 40  
            if df['RSI_14'].iloc[i] >= 60: score += 25
            if vol_surge: score += 35
            trend_dir = 1
            
        # Sell Setup: Below 200 EMA + Below VWAP + 9/21 Crossunder
        elif df['EMA_9'].iloc[i] < df['EMA_21'].iloc[i] and curr_c < baseline_val and curr_c < ema200_val:
            score += 40 
            if df['RSI_14'].iloc[i] <= 40: score += 25
            if vol_surge: score += 35
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
                trade_data = {
                    "Time (IST)": timestamp, 
                    "Asset": "NIFTY 50" if is_nifty else symbol.replace(".NS", ""), 
                    "Action/Strike": active_trade['Type'], 
                    "Spot Entry (₹)": active_trade['Entry'], 
                    "Spot Exit (₹)": curr_c, 
                    "Spot Target (₹)": active_trade['Target'],
                    "Spot SL (₹)": active_trade['StopLoss'],
                    "Result": status_msg
                }
                save_trade(trade_data, is_nifty=is_nifty)
                active_trade = None 
        else:
            # Must score 100% for Stocks (Trend + RSI + Volume). Nifty can trigger at 85+.
            trigger_score = 85 if is_nifty else 95 
            
            if score >= trigger_score and trend_dir != 0:
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
# 3. SWING TRADING ENGINE (3-4 Days)
# ==============================================================================
def scan_swing_stocks(tickers):
    results = []
    for sym in tickers:
        try:
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
            
            is_uptrend = c > last['EMA_20'] > last['EMA_50']
            is_momentum = last['RSI'] > 60
            is_vol_surge = last['Volume'] > (1.5 * last['Vol_Avg'])
            
            status = "🚀 STRONG BUY" if (is_uptrend and is_momentum and is_vol_surge) else "⏳ WAIT"
            
            results.append({
                "Stock": sym.replace('.NS', ''),
                "LTP (₹)": c,
                "RSI (>60)": f"{round(last['RSI'], 1)} {'✅' if is_momentum else '❌'}",
                "Uptrend": "✅" if is_uptrend else "❌",
                "Vol Surge": "✅" if is_vol_surge else "❌",
                "Action": status,
                "Target": f"₹{round(c * 1.04, 2)}" if status == "🚀 STRONG BUY" else "-",
                "SL": f"₹{round(c * 0.98, 2)}" if status == "🚀 STRONG BUY" else "-"
            })
        except: pass
    return results

# ==============================================================================
# 4. UI SETUP
# ==============================================================================
st.set_page_config(page_title="Scalper Pro AI v11.0", layout="wide")
audio_code = """<audio id="alert-sound" autoplay><source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-500.wav" type="audio/wav"></audio>"""

st.markdown("""
    <style>
    .stApp { background-color: #05070a; color: #ffffff; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    div[data-testid="stMetricValue"] { font-size: 38px; font-weight: 700; color: #00ffff; }
    
    [data-testid="collapsedControl"] { display: none; }
    
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #090d16; border-radius: 10px 10px 0 0; border: 1px solid #1f293d; border-bottom: none; padding: 10px 20px; font-size: 18px; font-weight: bold; }
    .stTabs [aria-selected="true"] { background-color: #1f293d; color: #deff9a !important; border-bottom: 2px solid #deff9a; }
    
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

st.markdown("<h2 style='text-align: center; font-weight: 700;'>SCALPER PRO <span style='color:#deff9a;'>AI v11.0</span></h2>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#1f293d;'>", unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs(["⚡ NIFTY OPTIONS", "📡 INTRADAY STOCKS", "🚀 SWING TRADING", "👨‍💻 ABOUT CREATOR"])

# ------------------------------------------------------------------------------
# TAB 1: NIFTY OPTIONS
# ------------------------------------------------------------------------------
with tab1:
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

            c1, c2, c3 = st.columns([1.2, 1, 2.5])
            pts = round(curr_p - open_p, 2)
            c1.metric("📊 NIFTY 50 SPOT", f"₹{curr_p:,}", f"{'+' if pts>=0 else ''}{pts} pts")
            c2.metric("🎯 BASELINE (EMA 50)", f"₹{baseline_val:,}")
            
            with c3:
                if active_trade is not None:
                    entry_p = active_trade['Entry']
                    target_p = active_trade['Target']
                    
                    if active_trade['Direction'] == 'LONG':
                        progress_pct = ((curr_p - entry_p) / (target_p - entry_p)) * 100 if target_p > entry_p else 0
                    else:
                        progress_pct = ((entry_p - curr_p) / (entry_p - target_p)) * 100 if entry_p > target_p else 0
                        
                    progress_pct = max(0, min(100, progress_pct)) 
                    
                    color = "#00ff66" if active_trade['Direction'] == 'LONG' else "#ff3333"
                    bg_color_fill = f"rgba(0, 255, 102, 0.3)" if active_trade['Direction'] == 'LONG' else f"rgba(255, 51, 51, 0.3)"
                    bg_style = f"background: linear-gradient(90deg, {bg_color_fill} {progress_pct}%, #0c111d {progress_pct}%);"
                    
                    st.markdown(f"""
                    <div style="border-left: 8px solid {color}; padding: 15px; border-radius: 8px; {bg_style} transition: background 0.5s ease;">
                        <h3 style="margin:0; color:{color};">⚡ ACTION: {active_trade['Signal']}</h3>
                        <p style="font-size:18px; margin:5px 0; color:#f5f5f5;"><b>SPOT ENTRY:</b> ₹{entry_p} | <span style="color:#00ff66;"><b>TARGET:</b> ₹{target_p}</span> | <span style="color:#ff3333;"><b>SL:</b> ₹{active_trade['StopLoss']}</span></p>
                        <div style="margin-top: 5px; font-weight: bold; color: #deff9a;">🎯 Target Progress: {progress_pct:.1f}%</div>
                    </div>
                    """, unsafe_allow_html=True)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Price', line=dict(color='#00ffff', width=2.5)))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_9'], name='9 EMA (Fast)', line=dict(color='#00ff66', width=1)))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_21'], name='21 EMA (Slow)', line=dict(color='#ff3333', width=1)))
            fig.add_trace(go.Scatter(x=df.index, y=df['Baseline'], name='Baseline', line=dict(color='#deff9a', width=2, dash='dash')))
            fig.update_layout(template='plotly_dark', paper_bgcolor='#05070a', plot_bgcolor='#05070a', height=400, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("<hr style='border-color:#1f293d;'><h3 style='color:#deff9a;'>📖 NIFTY OPTIONS LOG (Spot Basis)</h3>", unsafe_allow_html=True)
            n_hist = load_history(is_nifty=True)
            if not n_hist.empty: 
                st.dataframe(n_hist.style.apply(lambda x: ['background-color: #021a0d; color: #00ff66; font-weight: bold' if 'PROFIT' in str(val) else 'background-color: #1a0202; color: #ff3333; font-weight: bold' if 'LOSS' in str(val) else '' for val in x], subset=['Result']), use_container_width=True, hide_index=True)
            else:
                st.write("Abhi tak koi naya trade log nahi hua hai.")
    except Exception as e:
        st.error(f"Error: {e}")

# ------------------------------------------------------------------------------
# TAB 2: INTRADAY STOCKS
# ------------------------------------------------------------------------------
with tab2:
    st.write("🔥 Smart Money Filter Active: Trade tabhi milega jab Volume 150% se zyada hoga aur 200 EMA support karega.")
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
                ema200 = round(float(s_df['EMA_200'].iloc[-1]), 2)
                
                with cols[col_idx % 3]:
                    if s_trade is not None:
                        color_cls = "card-buy" if s_trade['Direction'] == 'LONG' else "card-sell"
                        t_col = "#00ff66" if s_trade['Direction'] == 'LONG' else "#ff3333"
                        
                        entry_p = s_trade['Entry']
                        target_p = s_trade['Target']
                        if s_trade['Direction'] == 'LONG': prog = ((curr_p - entry_p) / (target_p - entry_p)) * 100 if target_p > entry_p else 0
                        else: prog = ((entry_p - curr_p) / (entry_p - target_p)) * 100 if entry_p > target_p else 0
                        prog = max(0, min(100, prog))
                        bg_fill = f"rgba(0, 255, 102, 0.3)" if s_trade['Direction'] == 'LONG' else f"rgba(255, 51, 51, 0.3)"
                        bg_style = f"background: linear-gradient(90deg, {bg_fill} {prog}%, #0c111d {prog}%);"
                        
                        st.markdown(f"""
                        <div class="stock-card {color_cls}" style="{bg_style} transition: background 0.5s ease;">
                            <h3 style="color:{t_col}; margin:0;">{s_trade['Signal']}</h3>
                            <p style="margin:5px 0; color:#8b949e;">LTP: ₹{curr_p} | VWAP: ₹{vwap_p}</p>
                            <hr style="border-color:#1f293d; margin: 10px 0;">
                            <h4 style="margin:5px 0; color:#f5f5f5;">ENTRY: ₹{s_trade['Entry']}</h4>
                            <h4 style="margin:5px 0; color:#00ff66;">TARGET: ₹{s_trade['Target']}</h4>
                            <h4 style="margin:0; color:#ff3333;">SL: ₹{s_trade['StopLoss']}</h4>
                            <p style="margin-top: 5px; color: #deff9a; font-weight: bold;">🎯 Prog: {prog:.1f}%</p>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class="stock-card">
                            <h3 style="color:#f5f5f5; margin:0;">{name}</h3>
                            <p style="margin:5px 0; color:#8b949e;">LTP: ₹{curr_p} | VWAP: ₹{vwap_p} <br> 200 EMA: ₹{ema200}</p>
                            <p style="margin:10px 0 0 0; color:#ffaa00;">Waiting for Volume Breakout ⏳</p>
                        </div>
                        """, unsafe_allow_html=True)
                col_idx += 1
        except: pass
    
    st.markdown("<hr style='border-color:#1f293d;'><h3 style='color:#deff9a;'>📖 STOCK TRADE LOG</h3>", unsafe_allow_html=True)
    s_hist = load_history(is_nifty=False)
    if not s_hist.empty: 
        st.dataframe(s_hist.style.apply(lambda x: ['background-color: #021a0d; color: #00ff66; font-weight: bold' if 'PROFIT' in str(val) else 'background-color: #1a0202; color: #ff3333; font-weight: bold' if 'LOSS' in str(val) else '' for val in x], subset=['Result']), use_container_width=True, hide_index=True)

# ------------------------------------------------------------------------------
# TAB 3: SWING TRADING
# ------------------------------------------------------------------------------
with tab3:
    st.write("15 स्टॉक्स का डेली (1-Day) चार्ट स्कैन हो रहा है। (Target: 4%, SL: 2%)")
    swing_list = ["RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "TATAMOTORS.NS", 
                  "INFY.NS", "TCS.NS", "BAJFINANCE.NS", "BHARTIARTL.NS", "ITC.NS", 
                  "LT.NS", "M&M.NS", "MARUTI.NS", "SUNPHARMA.NS", "TATASTEEL.NS"]
    
    with st.spinner("Scanning Daily Charts... Please wait."):
        swing_results = scan_swing_stocks(swing_list)
        
    if swing_results:
        df_swing = pd.DataFrame(swing_results)
        st.dataframe(df_swing.style.apply(lambda x: ['background-color: #021a0d; color: #00ff66; font-weight: bold' if 'STRONG BUY' in str(val) else '' for val in x], subset=['Action']), use_container_width=True, hide_index=True)

# ------------------------------------------------------------------------------
# TAB 4: ABOUT CREATOR
# ------------------------------------------------------------------------------
with tab4:
    st.markdown("<h2 style='color:#deff9a; text-align:center;'>👨‍💻 Meet The Quant Developer</h2>", unsafe_allow_html=True)
    st.markdown("<hr style='border-color:#1f293d;'>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1]) 
    
    with col2:
        try:
            st.markdown("""
                <style>
                .profile-img { border-radius: 50%; display: block; margin-left: auto; margin-right: auto; border: 4px solid #deff9a; box-shadow: 0 4px 15px rgba(222, 255, 154, 0.3); }
                </style>
            """, unsafe_allow_html=True)
            st.image("photo.jpg", width=250, output_format="JPEG")
        except:
            st.info("💡 Tip: GitHub पर 'photo.jpg' नाम से अपनी फोटो अपलोड करें।")
        
        st.markdown("""
        <div style='text-align: center; margin-top: 20px;'>
            <h1 style='color:#f5f5f5; font-size: 40px; margin-bottom: 5px;'>[अपना नाम यहाँ लिखें]</h1>
            <h3 style='color:#00ffff; margin-top: 0;'>Algo Trader & System Architect</h3>
            <p style='color:#8b949e; font-size: 18px; margin-top: 15px;'>
                मैंने इस एडवांस <strong>Scalper Pro AI</strong> को प्योर मोमेंटम और इंस्टीटूशनल डेटा (VWAP & EMA) को डिकोड करने के लिए बनाया है। यह सिस्टम भावनाओं को हटाकर 100% गणितीय सटीकता पर काम करता है।
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div style='background-color: #0c111d; padding: 20px; border-radius: 10px; border: 1px solid #1f293d; margin-top: 20px;'>
            <h4 style='color:#deff9a; margin-bottom: 15px;'>🔗 Connect For Mentorship & Services:</h4>
            <ul style='list-style-type: none; padding-left: 0; font-size: 18px; line-height: 2;'>
                <li>📺 <b>YouTube:</b> <a href="https://youtube.com/c/TechVantageHindi" target="_blank" style="color:#00ff66; text-decoration:none;">TechVantageHindi</a></li>
                <li>📱 <b>Telegram:</b> <a href="https://t.me/AapkaTelegramID" target="_blank" style="color:#00ff66; text-decoration:none;">@JoinMyChannel</a></li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

# ==============================================================================
# REFRESH LOGIC (8 SECONDS)
# ==============================================================================
time.sleep(8) 
st.rerun()
