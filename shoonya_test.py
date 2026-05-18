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
# 1. CORE CONFIGURATION & STYLING (The "Pro" Look)
# ==============================================================================
st.set_page_config(page_title="Scalper Pro AI v14.0", layout="wide", initial_sidebar_state="collapsed")

# Custom CSS for Institutional Dark Theme and Custom Elements
st.markdown("""
    <style>
    /* Main App Background */
    .stApp { background-color: #0c0f14; color: #daffde; }
    
    /* Hide default Streamlit elements */
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    [data-testid="collapsedControl"] { display: none; }
    
    /* Top Bar Clock */
    .live-clock { font-size: 28px; font-weight: 800; text-align: right; font-family: 'Courier New', monospace; padding-right: 10px; }
    
    /* Customized Tabs to look like Buttons */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; justify-content: center; background-color: transparent; padding: 10px; border-radius: 15px;}
    .stTabs [data-baseweb="tab"] { background-color: #1a1f29; border-radius: 10px; border: 1px solid #2d3748; padding: 12px 24px; font-size: 16px; font-weight: 700; color: #8b949e; transition: all 0.2s ease-in-out; }
    .stTabs [aria-selected="true"] { background-color: #deff9a; color: #0c0f14 !important; border-color: #deff9a; box-shadow: 0 0 15px rgba(222, 255, 154, 0.4); }
    .stTabs [data-baseweb="tab"]:hover { border-color: #deff9a; color: #deff9a; }

    /* Condensed Execution Card (Pro View) */
    .ex-card { background: #131720; border-radius: 12px; padding: 18px; border: 1px solid #2d3748; margin-bottom: 15px; border-left: 5px solid transparent; }
    .status-wait { color: #8b949e; border-left-color: #2d3748; }
    .status-long { color: #00ff66; border-left-color: #00ff66; background: linear-gradient(90deg, rgba(0,255,102,0.05) 0%, #131720 100%);}
    .status-short { color: #ff3333; border-left-color: #ff3333; background: linear-gradient(90deg, rgba(255,51,51,0.05) 0%, #131720 100%);}
    .status-eod { color: #ffaa00; border-left-color: #ffaa00; }

    /* Custom Color Boxes for Table Cells */
    .profit-box { background-color: rgba(0, 255, 102, 0.2); color: #00ff66; font-weight: 700; padding: 5px; border-radius: 4px; border: 1px solid #00ff66; }
    .loss-box { background-color: rgba(255, 51, 51, 0.2); color: #ff3333; font-weight: 700; padding: 5px; border-radius: 4px; border: 1px solid #ff3333; }
    .potential-box { background-color: rgba(255, 170, 0, 0.2); color: #ffaa00; font-weight: 700; padding: 5px; border-radius: 4px;}

    /* Stock Radar Cards */
    .radar-card { background: #131720; border-radius: 10px; padding: 15px; border: 1px solid #2d3748; margin-bottom: 10px;}
    .buy-radar { border-color: #00ff66; }
    .potential-radar { border-color: #ffaa00; }
    
    </style>
    """, unsafe_allow_html=True)

audio_code = """<audio id="alert-sound" autoplay><source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-500.wav" type="audio/wav"></audio>"""

# ==============================================================================
# 2. TRADE HISTORY LOGGERS
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
# 3. PRO QUANT ENGINE (ADX, Crossover, EOD, 200 EMA)
# ==============================================================================
def calculate_quant_engine(df, symbol):
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

    # Core Technicals
    df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    # VWAP FALLBACK (If Volume doesn't exist)
    if 'Volume' in df.columns and df['Volume'].sum() > 0:
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        df['Baseline'] = (tp * df['Volume']).cumsum() / (df['Volume'].cumsum() + 1e-10) 
        df['Vol_Avg'] = df['Volume'].rolling(20).mean() 
    else:
        df['Baseline'] = df['Close'].ewm(span=50, adjust=False).mean() 
        df['Vol_Avg'] = 1

    # RSI & ATR
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI_14'] = 100 - (100 / (1 + (gain / (loss + 1e-10))))
    df['ATR_14'] = (pd.concat([df['High'] - df['Low'], (df['High'] - df['Close'].shift(1)).abs(), (df['Low'] - df['Close'].shift(1)).abs()], axis=1).max(axis=1)).rolling(window=14).mean()

    # 🚀 ADX / CHOP ZONE FILTER (v14.0 Strictness)
    df['EMA_Dist_Pct'] = (abs(df['EMA_9'] - df['EMA_21']) / df['Close']) * 100

    df['AI_Score'], df['Signal'], df['Entry'], df['Target'], df['StopLoss'], df['Status'] = 0, 'WAIT ⏳', 0.0, 0.0, 0.0, ""
    active_trade = None
    is_nifty = "NSEI" in symbol
    
    start_idx = 200 if len(df) > 200 else 20 
    for i in range(start_idx, len(df)):
        score = 0
        curr_c = round(float(df['Close'].iloc[i]), 2)
        baseline_val = float(df['Baseline'].iloc[i])
        ema200_val = float(df['EMA_200'].iloc[i])
        atr = float(df['ATR_14'].iloc[i])
        
        candle_time = df.index[i]
        if candle_time.tz is None: candle_time = candle_time.tz_localize('UTC')
        ist_time = candle_time.tz_convert('Asia/Kolkata')
        timestamp = ist_time.strftime("%d-%b %I:%M %p")
        
        # 🕒 EOD CHECK (3:15 PM Cutoff)
        is_eod = ist_time.hour >= 15 and ist_time.minute >= 15 if ist_time.hour < 16 else True
            
        vol_surge = True
        if 'Volume' in df.columns and df['Volume'].sum() > 0:
            vol_surge = float(df['Volume'].iloc[i]) > (1.3 * float(df['Vol_Avg'].iloc[i])) # Relaxed volume surge
            
        # Sideways Filter: Distance between EMAs must be > 0.035% of price
        is_trending = df['EMA_Dist_Pct'].iloc[i] > 0.035
        
        if not is_eod:
            if df['EMA_9'].iloc[i] > df['EMA_21'].iloc[i] and curr_c > baseline_val and curr_c > ema200_val and is_trending:
                score += 40  
                if df['RSI_14'].iloc[i] >= 60: score += 25
                if vol_surge: score += 35
                trend_dir = 1
            elif df['EMA_9'].iloc[i] < df['EMA_21'].iloc[i] and curr_c < baseline_val and curr_c < ema200_val and is_trending:
                score += 40 
                if df['RSI_14'].iloc[i] <= 40: score += 25
                if vol_surge: score += 35
                trend_dir = -1
            else: score, trend_dir = 0, 0
        else: score, trend_dir = 0, 0 # NO NEW TRADES AFTER 3:15 PM
            
        df.at[df.index[i], 'AI_Score'] = score
        
        if active_trade is not None:
            df.at[df.index[i], 'Signal'] = active_trade['Signal']
            df.at[df.index[i], 'Entry'] = active_trade['Entry']
            df.at[df.index[i], 'Target'] = active_trade['Target']
            df.at[df.index[i], 'StopLoss'] = active_trade['StopLoss']
            
            trade_closed = False
            status_msg = ""
            
            if is_eod: status_msg, trade_closed = "⏱️ EOD SQUARE-OFF", True
            elif active_trade['Direction'] == 'LONG':
                if curr_c >= active_trade['Target']: status_msg, trade_closed = "🎯 TARGET HIT (+PROFIT)", True
                elif curr_c <= active_trade['StopLoss']: status_msg, trade_closed = "🛑 SL HIT (-LOSS)", True
            elif active_trade['Direction'] == 'SHORT':
                if curr_c <= active_trade['Target']: status_msg, trade_closed = "🎯 TARGET HIT (+PROFIT)", True
                elif curr_c >= active_trade['StopLoss']: status_msg, trade_closed = "🛑 SL HIT (-LOSS)", True
            
            if trade_closed:
                df.at[df.index[i], 'Status'] = status_msg
                trade_data = {"Time (IST)": timestamp, "Asset": "NIFTY 50" if is_nifty else symbol.replace(".NS", ""), "Action/Strike": active_trade['Type'], "Spot Entry (₹)": active_trade['Entry'], "Spot Exit (₹)": curr_c, "Spot Target (₹)": active_trade['Target'], "Spot SL (₹)": active_trade['StopLoss'], "Result": status_msg}
                save_trade(trade_data, is_nifty=is_nifty)
                active_trade = None 
        else:
            trigger_score = 85 if is_nifty else 95 # Nifty needs less strictness than stocks
            if score >= trigger_score and trend_dir != 0 and not is_eod:
                atm_strike = int(round(curr_c / 50) * 50)
                sl_dist = max(18, atr * 1.2) if is_nifty else curr_c * 0.003 # ATR based SL for Nifty
                tgt_dist = sl_dist * 2 # Standard 1:2 Risk-Reward

                if trend_dir == 1:
                    t_type = f'{atm_strike} CE' if is_nifty else 'BUY'
                    direction = 'LONG'
                    entry, tgt, sl = curr_c, curr_c + tgt_dist, curr_c - sl_dist
                else:
                    t_type = f'{atm_strike} PE' if is_nifty else 'SELL'
                    direction = 'SHORT'
                    entry, tgt, sl = curr_c, curr_c - tgt_dist, curr_c + sl_dist
                
                sig = f'🟢 BUY NIFTY {t_type}' if is_nifty else f'🟢 BUY {symbol.replace(".NS","")}'
                active_trade = {'Type': t_type, 'Signal': sig, 'Entry': round(entry,1), 'Target': round(tgt,1), 'StopLoss': round(sl,1), 'Direction': direction}
                df.at[df.index[i], 'Signal'], df.at[df.index[i], 'Entry'], df.at[df.index[i], 'Target'], df.at[df.index[i], 'StopLoss'] = active_trade['Signal'], active_trade['Entry'], active_trade['Target'], active_trade['StopLoss']

    return df, active_trade

# ==============================================================================
# 4. SWING TRADING ENGINE (DYNAMIC SCORING v13.0)
# ==============================================================================
def scan_swing_stocks(tickers):
    results = []
    for sym in tickers:
        try:
            df = yf.download(sym, period='6mo', interval='1d', progress=False)
            if df.empty or len(df) < 50: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
            df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
            df['RSI'] = 100 - (100 / (1 + (df['Close'].diff().where(df['Close'].diff() > 0, 0).rolling(14).mean() / (-df['Close'].diff().where(df['Close'].diff() < 0, 0).rolling(14).mean() + 1e-10))))
            df['Vol_Avg'] = df['Volume'].rolling(20).mean()
            last = df.iloc[-1]; c = round(float(last['Close']), 2)
            is_uptrend = c > last['EMA_20'] and last['EMA_20'] > last['EMA_50']
            is_momentum = last['RSI'] >= 55; is_vol_surge = last['Volume'] > (1.2 * last['Vol_Avg'])
            score = sum([is_uptrend, is_momentum, is_vol_surge])
            status = "🚀 STRONG BUY" if score == 3 else "🔥 POTENTIAL (Watch)" if score == 2 and is_uptrend else "⏳ WAIT"
            results.append({"Stock": sym.replace('.NS', ''), "LTP (₹)": c, "RSI (>55)": f"{round(last['RSI'], 1)} {'✅' if is_momentum else '❌'}", "Uptrend": "✅" if is_uptrend else "❌", "Vol Surge": "✅" if is_vol_surge else "❌", "Action": status, "Target (5%)": f"₹{round(c * 1.05, 1)}" if status != "⏳ WAIT" else "-", "SL (2.5%)": f"₹{round(c * 0.975, 1)}" if status != "⏳ WAIT" else "-"})
        except: pass
    return results

# ==============================================================================
# 5. UI LAYOUT & EXECUTION
# ==============================================================================
# 🕒 PRO CLOCK & HEADER
tz = pytz.timezone('Asia/Kolkata'); now_ist = datetime.datetime.now(tz)
col_clock1, col_clock2 = st.columns([2, 1])
with col_clock1: st.markdown(f"<h1 style='margin:0; padding:0;'>Scalper Pro <span style='color:#deff9a;'>v14.0</span></h1>", unsafe_allow_html=True)
with col_clock2: 
    color_closed = "#ff3333" if now_ist.hour >= 16 or now_ist.hour < 9 or (now_ist.hour == 15 and now_ist.minute >= 30) else "#daffde"
    st.markdown(f"<div class='live-clock' style='color:{color_closed};'>{now_ist.strftime('%d-%b %I:%M:%S %p')} IST</div>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#2d3748; margin: 10px 0;'>", unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs(["⚡ NIFTY OPTIONS", "📡 INTRADAY STOCKS", "🚀 SWING RADAR", "👨‍💻 CREATOR"])

# ------------------------------------------------------------------------------
# TAB 1: NIFTY OPTIONS (Compact "Bloomberg" View)
# ------------------------------------------------------------------------------
with tab1:
    try:
        data = yf.download('^NSEI', period='1d', interval='1m', progress=False)
        if not data.empty:
            df, active_trade = calculate_quant_engine(data, '^NSEI')
            last = df.iloc[-1]; prev = df.iloc[-2]; curr_p = round(float(df['Close'].iloc[-1]), 2); open_p = round(float(df['Open'].iloc[0]), 2); pts = round(curr_p - open_p, 2)
            is_eod_ui = now_ist.hour >= 15 and now_ist.minute >= 15
            
            # Sound Trigger
            play_sound = False
            if active_trade is None and last['AI_Score'] >= 85 and prev['AI_Score'] < 85: play_sound = True
            if play_sound: st.markdown(audio_code, unsafe_allow_html=True)

            # Execution Box and Key Metrics
            col_met1, col_met2 = st.columns([1, 2.5])
            with col_met1:
                st.metric("NIFTY 50 SPOT", f"₹{curr_p:,}", f"{'+' if pts>=0 else ''}{pts} pts", help="yfinance delayed data")
                st.metric("BASELINE (VWAP/EMA)", f"₹{round(float(last['Baseline']), 1)}", help="Trend Baseline")
            
            with col_met2:
                if is_eod_ui:
                    st.markdown("<div class='ex-card status-eod'><h3>🚫 EOD SQUARE-OFF</h3>Intraday टाइम ओवर। कोई नया ट्रेड नहीं लिया जाएगा।</div>", unsafe_allow_html=True)
                elif active_trade is not None:
                    e, t, sl = active_trade['Entry'], active_trade['Target'], active_trade['StopLoss']; rr = round((t-e)/(e-sl),1)
                    prog = max(0, min(100, (((curr_p-e)/(t-e))*100 if active_trade['Direction']=='LONG' else ((e-curr_p)/(e-t))*100)))
                    # Delta-based Premium Estimate
                    prem_entry_est = 25; prem_tgt = round(abs(t-e)*0.5 + prem_entry_est,1); prem_sl = round(prem_entry_est - abs(e-sl)*0.5,1)
                    
                    st.markdown(f"""
                    <div class='ex-card status-{'long' if active_trade['Direction']=='LONG' else 'short'}'>
                        <h2 style='margin:0;'>{active_trade['Signal']}</h2>
                        <span style='font-size:16px; font-weight: bold;'>Spot Entry: {e} | Target: {t} | SL: {sl} | RR: 1:{rr}</span><br>
                        <span style="color:#00ffff; font-size:14px; font-weight:bold;">📊 Estimated Options Premium (0.5 Delta Basis): Target: ~₹{prem_tgt} | SL: ~₹{prem_sl}</span>
                    </div>
                    """, unsafe_allow_html=True)
                elif last['AI_Score'] >= 85:
                    st.markdown(f"<div class='ex-card status-{'long' if 'BUY' in last['Signal'] else 'short'}'><h2>🚀 ALERT: {last['Signal']}</h2>AI Score: {last['AI_Score']}/100. Fast Momentum Detected!</div>", unsafe_allow_html=True)
                else:
                    st.markdown("<div class='ex-card status-wait'><h3>⏳ WAIT</h3>मार्केट साइडवेज है (ADX Chop Zone Filter Active) या ट्रेंड स्पष्ट नहीं है।</div>", unsafe_allow_html=True)

            # Chart
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Price', line=dict(color='#00ffff', width=2)))
            fig.add_trace(go.Scatter(x=df.index, y=df['Baseline'], name='Baseline', line=dict(color='#deff9a', width=1.5, dash='dash')))
            fig.update_layout(template='plotly_dark', paper_bgcolor='#0c0f14', plot_bgcolor='#0c0f14', height=380, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='#1a1f29'))
            st.plotly_chart(fig, use_container_width=True)
            
            # Log
            st.markdown("<h3 style='color:#deff9a;'>📖 OPTIONS LOG (IST)</h3>", unsafe_allow_html=True)
            n_hist = load_history(is_nifty=True)
            if not n_hist.empty: 
                def style_result(val):
                    if 'TARGET' in val: return 'profit-box'
                    if 'SL HIT' in val or 'SQUARE-OFF' in val: return 'loss-box'
                    return ''
                # Custom Styling for DataFrame Cells
                st.dataframe(n_hist.style.apply(lambda x: [style_result(val) if x.name == 'Result' else '' for val in x], axis=0), use_container_width=True, hide_index=True)
    except Exception as e: st.error(f"Error Nifty: {e}")

# ------------------------------------------------------------------------------
# TAB 2: INTRADAY STOCKS
# ------------------------------------------------------------------------------
with tab2:
    st.write("🔥 Smart Money Filter Active: Trade tabhi milega jab Volume 130% se zyada hoga aur 200 EMA support kareगा।")
    stocks = ["RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "TATAMOTORS.NS", "INFY.NS"]
    cols = st.columns(3); col_idx = 0
    for stock in stocks:
        try:
            s_data = yf.download(stock, period='1d', interval='1m', progress=False)
            if not s_data.empty:
                s_df, s_trade = calculate_quant_engine(s_data, stock); name = stock.replace(".NS", ""); curr_p = round(float(s_df['Close'].iloc[-1]), 2); vwap_p = round(float(s_df['Baseline'].iloc[-1]), 2)
                with cols[col_idx % 3]:
                    if s_trade is not None:
                        color = "#00ff66" if s_trade['Direction'] == 'LONG' else "#ff3333"
                        st.markdown(f"<div class='radar-card buy-radar' style='border-color:{color};'><h3 style='margin:0; color:{color};'>{s_trade['Signal']}</h3>Spot: {curr_p} | Entry: {s_trade['Entry']} | Tgt: {s_trade['Target']}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='radar-card'><h3 style='margin:0;'>{name}</h3>LTP: ₹{curr_p} | Sideways. No Trade ⏳</div>", unsafe_allow_html=True)
                col_idx += 1
        except: pass
    st.markdown("<h3 style='color:#deff9a;'>📖 STOCK TRADE LOG</h3>", unsafe_allow_html=True)
    s_hist = load_history(is_nifty=False)
    if not s_hist.empty: st.dataframe(s_hist, use_container_width=True, hide_index=True)

# ------------------------------------------------------------------------------
# TAB 3: SWING RADAR (Dynamic Scoring)
# ------------------------------------------------------------------------------
with tab3:
    st.write("🔥 15 स्टॉक्स का डेली चार्ट स्कैन हो रहा है। (Target: 5%, SL: 2.5%)")
    swing_list = ["RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "TATAMOTORS.NS", "INFY.NS", "TCS.NS", "ITC.NS", "LT.NS", "M&M.NS"]
    with st.spinner("Scanning..."): swing_results = scan_swing_stocks(swing_list)
    if swing_results:
        df_swing = pd.DataFrame(swing_results)
        # Custom Style for Action Cell
        def style_swing(val):
            if 'STRONG BUY' in val: return 'profit-box'
            if 'POTENTIAL' in val: return 'potential-box'
            return ''
        st.dataframe(df_swing.style.apply(lambda x: [style_swing(val) if x.name == 'Action' else '' for val in x], axis=0), use_container_width=True, hide_index=True)

# ------------------------------------------------------------------------------
# TAB 4: ABOUT CREATOR
# ------------------------------------------------------------------------------
with tab4:
    col_c1, col_c2, col_c3 = st.columns([1, 2, 1]) 
    with col_c2:
        try: st.image("photo.jpg", width=200)
        except: st.info("Tip: GitHub पर 'photo.jpg' अपलोड करें।")
        st.markdown(f"<div style='text-align: center;'><h1 style='color:#f5f5f5;'>[अपना नाम यहाँ लिखें]</h1>Algo Trader | System Architect</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='background-color: #131720; padding: 15px; border-radius: 10px; border: 1px solid #2d3748; margin-top: 20px;'>📺 YouTube: TechVantageHindi | 📱 Telegram: @JoinMyChannel</div>", unsafe_allow_html=True)

# ==============================================================================
# FAST REFRESH (8 SECONDS)
# ==============================================================================
time.sleep(8); st.rerun()
