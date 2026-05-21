import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# 1. PAGE SETUP & PERSISTENT STATE
st.set_page_config(page_title="QuantScalper AI v20.0", layout="wide")

# ये स्टेट्स कभी डिलीट नहीं होंगी, चाहे पेज कितनी बार भी रिफ्रेश हो
if 'trade_active' not in st.session_state: st.session_state.trade_active = False
if 'trade_details' not in st.session_state: st.session_state.trade_details = {}

st.title("QUANT SCALPER AI v20.0 [STABLE]")

# 2. SEMI-AUTO TRADING BUTTONS (Robust Logic)
col1, col2, col3 = st.columns([1, 1, 2])

with col1:
    if st.button("🟢 BUY CE"):
        st.session_state.trade_active = True
        st.session_state.trade_details = {'Type': 'CE', 'Entry': 23750, 'SL': 23730}
with col2:
    if st.button("🔴 BUY PE"):
        st.session_state.trade_active = True
        st.session_state.trade_details = {'Type': 'PE', 'Entry': 23750, 'SL': 23770}

# 3. TRADE MANAGEMENT
if st.session_state.trade_active:
    trade = st.session_state.trade_details
    st.warning(f"ACTIVE: {trade['Type']} | Entry: {trade['Entry']} | SL: {trade['SL']}")
    if st.button("Close Trade"):
        st.session_state.trade_active = False
        st.session_state.trade_details = {}
        st.rerun()

# 4. DATA ENGINE (v18.8 का सुपर-फास्ट इंजन)
@st.cache_data(ttl=30)
def get_data():
    return yf.download('^NSEI', period='1d', interval='1m', progress=False)

try:
    df = get_data()
    if not df.empty:
        # SMC Calculation
        df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
        
        # Display Chart
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Price', line=dict(color='#deff9a')))
        fig.add_trace(go.Scatter(x=df.index, y=df['VWAP'], name='VWAP', line=dict(color='#00ffff', dash='dash')))
        fig.update_layout(template='plotly_dark', height=400)
        st.plotly_chart(fig, use_container_width=True)
except:
    st.error("System initializing...")
