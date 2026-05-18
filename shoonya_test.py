import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ==============================================================================
# 1. ADVANCED QUANT ENGINE V2.0 (50-PT TARGET, DELTA & REWARD SYSTEM)
# ==============================================================================
def calculate_ai_v2(df, symbol):
    # yfinance के मल्टी-इंडेक्स कॉलम की समस्या को ठीक करने के लिए
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # कोर टेक्निकल इंडिकेटर्स
    df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
    
    # RSI कैलकुलेशन
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['RSI_14'] = 100 - (100 / (1 + rs))

    # डायनेमिक स्टॉप लॉस के लिए ATR कैलकुलेशन
    high, low, close = df['High'].squeeze(), df['Low'].squeeze(), df['Close'].squeeze()
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    df['ATR_14'] = tr.rolling(window=14).mean()

    # सुपरट्रेंड (Factor=3, Period=10)
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

    # एआई फील्ड्स को इनिशियलाइज करना
    df['AI_Score'] = 0
    df['Signal'] = 'WAIT ⏳'
    df['Entry'] = 0.0
    df['Target'] = 0.0
    df['StopLoss'] = 0.0
    df['Status'] = ""

    # लाइव ट्रेड स्टेट ट्रैकर (सिग्नल्स को मिस होने से बचाने के लिए)
    active_trade = None
    
    for i in range(20, len(df)):
        score = 0
        curr_c = round(float(c_list[i]), 2)
        atr = df['ATR_14'].iloc[i]
        
        # स्कोरिंग लॉजिक
        if trend[i] == 1:  # CALL सेंटिमेंट
            score += 30
            if curr_c > df['EMA_20'].iloc[i]: score += 30
            if df['RSI_14'].iloc[i] > 60: score += 25
            if tr.iloc[i] > df['ATR_14'].iloc[i]: score += 15
        else:  # PUT सेंटिमेंट
            score += 30
            if curr_c < df['EMA_20'].iloc[i]: score += 30
            if df['RSI_14'].iloc[i] < 40: score += 25
            if tr.iloc[i] > df['ATR_14'].iloc[i]: score += 15
            
        df.at[df.index[i], 'AI_Score'] = score
        
        # एक्टिव ट्रेड और रिवॉर्ड मैनेजमेंट लॉजिक
        if active_trade is not None:
            df.at[df.index[i], 'Signal'] = active_trade['Signal']
            df.at[df.index[i], 'Entry'] = active_trade['Entry']
            df.at[df.index[i], 'Target'] = active_trade['Target']
            df.at[df.index[i], 'StopLoss'] = active_trade['StopLoss']
            
            if active_trade['Type'] == 'CALL':
                if curr_c >= active_trade['Target']:
                    df.at[df.index[i], 'Status'] = "🏆 TARGET HIT (+50 PTS) 🏆"
                    active_trade = None
                elif curr_c <= active_trade['StopLoss']:
                    df.at[df.index[i], 'Status'] = "🛑 SL HIT (EXIT) 🛑"
                    active_trade = None
            elif active_trade['Type'] == 'PUT':
                if curr_c <= active_trade['Target']:
                    df.at[df.index[i], 'Status'] = "🏆 TARGET HIT (+50 PTS) 🏆"
                    active_trade = None
                elif curr_c >= active_trade['StopLoss']:
                    df.at[df.index[i], 'Status'] = "🛑 SL HIT (EXIT) 🛑"
                    active_trade = None
        else:
            if score >= 85:
                if trend[i] == 1:
                    sig = '🟢 AI CALL ACTION'
                    tgt = curr_c + 50 if "NSEI" in symbol else curr_c + (2 * atr)
                    sl = curr_c - (1.2 * atr)
                    active_trade = {'Type': 'CALL', 'Signal': sig, 'Entry': curr_c, 'Target': round(tgt, 2), 'StopLoss': round(sl, 2)}
                else:
                    sig = '🔴 AI PUT ACTION'
                    tgt = curr_c - 50 if "NSEI" in symbol else curr_c - (2 * atr)
                    sl = curr_c + (1.2 * atr)
                    active_trade = {'Type': 'PUT', 'Signal': sig, 'Entry': curr_c, 'Target': round(tgt, 2), 'StopLoss': round(sl, 2)}
                
                df.at[df.index[i], 'Signal'] = active_trade['Signal']
                df.at[df.index[i], 'Entry'] = active_trade['Entry']
                df.at[df.index[i], 'Target'] = active_trade['Target']
                df.at[df.index[i], 'StopLoss'] = active_trade['StopLoss']

    return df

# ==============================================================================
# 2. ULTRA-PROFESSIONAL UI SETUP (PURE DARK THEME)
# ==============================================================================
st.set_page_config(page_title="Scalper Pro AI v2.0", layout="wide")

# एडवांस डार्क थीम सीएसएस (सफेद साइडबार को पूरी तरह डार्क करने के लिए)
st.markdown("""
    <style>
    .stApp { background-color: #05070a; color: #ffffff; }
    
    /* साइडबार का कम्प्लीट डार्क लुक */
    [data-testid="stSidebar"] { background-color: #090d16 !important; border-right: 1px solid #1f293d !important; }
    [data-testid="stSidebar"] * { color: #f5f5f5 !important; }
    
    /* डिफ़ॉल्ट स्ट्रीमलिट हेडर और फुटर को छिपाना */
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    
    /* लाइव मेट्रिक्स की स्टाइलिंग */
    div[data-testid="stMetricValue"] { font-size: 38px; font-weight: 700; color: #00ffff; }
    
    /* रिवॉर्ड और स्टेटस बैज */
    .reward-box { padding: 22px; border-radius: 12px; text-align: center; font-weight: bold; font-size: 24px; border: 2px solid; margin-bottom: 20px; }
    .target-hit { background-color: #021a0d; color: #00ff66; border-color: #00ff66; box-shadow: 0 0 20px rgba(0, 255, 102, 0.4); }
    .sl-hit { background-color: #1a0202; color: #ff3333; border-color: #ff3333; box-shadow: 0 0 20px rgba(255, 51, 51, 0.4); }
    .wait-box { background-color: #0c111d; color: #8b949e; border-color: #1f293d; border-style: dashed; }
    
    /* सिग्नल कार्ड्स */
    .signal-card { border-left: 10px solid; padding: 20px; background: #0c111d; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
    </style>
    """, unsafe_allow_html=True)

# ऑडियो अलर्ट के लिए बीप साउंड (प्रीमियम एक्सपीरियंस)
beep_sound = '<audio autoplay><source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-500.wav" type="audio/wav"></audio>'

# साइडबार ब्रांडिंग
st.sidebar.markdown("<h2 style='text-align: center; font-weight: 700;'>SCALPER PRO <br><span style='color:#deff9a;'>AI v2.0</span></h2>", unsafe_allow_html=True)
st.sidebar.markdown("<hr style='border-color:#1f293d;'>", unsafe_allow_html=True)
menu = st.sidebar.radio("Navigation Menu", ["⚡ LIVE NIFTY STATION", "📡 MOMENTUM RADAR"])

# ------------------------------------------------------------------------------
# पेज 1: लाइव निफ्टी स्टेशन
# ------------------------------------------------------------------------------
if menu == "⚡ LIVE NIFTY STATION":
    st.markdown("<h2 style='color:#f5f5f5;'>⚡ NIFTY 50 AI QUANT STATION</h2>", unsafe_allow_html=True)
    
    data = yf.download('^NSEI', period='1d', interval='1m', progress=False)
    if not data.empty:
        df = calculate_ai_v2(data, '^NSEI')
        last = df.iloc[-1]
        
        curr_p = round(float(df['Close'].iloc[-1]), 2)
        open_p = round(float(df['Open'].iloc[0]), 2)
        points_change = round(curr_p - open_p, 2)
        pct_change = round((points_change / open_p) * 100, 2)
        score = last['AI_Score']
        
        # लाइव पॉइंट्स (Delta) के साथ टॉप रो लेआउट
        c1, c2 = st.columns([1, 2])
        
        # बिल्कुल ज़ेरोधा की तरह हरा/लाल सिंबल और लाइव पॉइंट दिखाना
        sign = "+" if points_change >= 0 else ""
        c1.metric(
            label="📊 NIFTY 50 INDEX", 
            value=f"₹{curr_p:,}", 
            delta=f"{sign}{points_change} pts ({sign}{pct_change}%) Today"
        )
        
        with c2:
            # रियल-टाइम रिवॉर्ड / एग्जिट बैज लॉजिक
            if last['Status'] != "":
                is_tgt = "TARGET" in last['Status']
                style_class = "target-hit" if is_tgt else "sl-hit"
                st.markdown(f'<div class="reward-box {style_class}">{last["Status"]}</div>', unsafe_allow_html=True)
                st.markdown(beep_sound, unsafe_allow_html=True)
            elif score >= 85:
                st.markdown(beep_sound, unsafe_allow_html=True)
                color = "#00ff66" if "CALL" in last['Signal'] else "#ff3333"
                st.markdown(f"""
                <div class="signal-card" style="border-color:{color};">
                    <h2 style="margin:0; color:{color};">{last['Signal']} ({score}% CONFIDENCE)</h2>
                    <p style="font-size:22px; margin:10px 0; color:#f5f5f5;">
                        <b>ENTRY:</b> ₹{last['Entry']} | 
                        <span style="color:#00ff66;"><b>🎯 TARGET:</b> ₹{last['Target']}</span> | 
                        <span style="color:#ff3333;"><b>🛑 SL:</b> ₹{last['StopLoss']}</span>
                    </p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown('<div class="reward-box wait-box">⏳ AI ENGINE STATUS: MONITORING 85% INSTITUTIONAL BREAKOUT ZONE...</div>', unsafe_allow_html=True)

        # लाइव कैंडलस्टिक/लाइन चार्ट
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Live Price', line=dict(color='#00ffff', width=2.5)))
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_20'], name='20 EMA Trend', line=dict(color='#ffaa00', width=1.5, dash='dot')))
        
        fig.update_layout(
            template='plotly_dark', 
            paper_bgcolor='#05070a', 
            plot_bgcolor='#05070a', 
            height=460,
            margin=dict(l=10, r=10, t=20, b=10),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor='#1f293d')
        )
        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------------------
# पेज 2: मोमेंटम राडार (स्टॉक्स के लिए)
# ------------------------------------------------------------------------------
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
                    "Stock Asset": stock.replace(".NS",""),
                    "Current Price": f"₹{round(float(s_data['Close'].iloc[-1]), 2):,}",
                    "AI Strength": f"{s_last['AI_Score']}%",
                    "Direction": s_last['Signal'],
                    "Trigger Entry": f"₹{s_last['Entry']}",
                    "Target Move": f"₹{s_last['Target']}",
                    "Risk StopLoss": f"₹{s_last['StopLoss']}"
                })
    
    if grid_data:
        st.dataframe(pd.DataFrame(grid_data), use_container_width=True)
    else:
        st.info("No high-conviction (>85%) institutional breakout stocks found in the radar at this moment.")
