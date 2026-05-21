import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import os
import datetime
import pytz
import requests
import json
import hashlib
import concurrent.futures

try:
    import pyotp
    SH_AVAILABLE = True
except ImportError:
    SH_AVAILABLE = False

# ==============================================================================
# 1. CONFIG
# ==============================================================================
APP_NAME = "QuantScalper AI v19.0"
NIFTY_HISTORY_FILE = "nifty_trade_book.csv"
EXPECTED_COLUMNS = ["Time (IST)", "Asset", "Action", "Spot Entry", "Spot Exit", "Points", "Result"]

SHOONYA_UID = os.getenv("SHOONYA_UID", "FN209492")
SHOONYA_PWD = os.getenv("SHOONYA_PWD", "Rahul@1995")
SHOONYA_API_KEY = os.getenv("SHOONYA_API_KEY", "3007acd3cd50a75e4e8eb1bfc0e1459a")
SHOONYA_VC = os.getenv("SHOONYA_VC", "FN209492_U")
SHOONYA_TOTP_SECRET = os.getenv("SHOONYA_TOTP_SECRET", "666J4TSFQRM624X75B6WZ32PMUH3477P")

SH_TOKENS = {
    "^NSEI": "26000",
    "^NSEBANK": "26009",
    "RELIANCE.NS": "2885",
    "HDFCBANK.NS": "1333",
}

# Safer strategy filters
MIN_ADX = 24
ADX_LOOKBACK = 4
VOLUME_MULTIPLIER = 1.20
BREAKOUT_ATR_BUFFER = 0.25
MAX_VWAP_DISTANCE_ATR = 1.20
MIN_ATR_SL = 18.0
ATR_SL_MULTIPLIER = 1.50
RR_MULTIPLIER = 2.0
COOLDOWN_MINUTES_AFTER_SL = 15
NO_NEW_TRADE_AFTER_HOUR = 14
NO_NEW_TRADE_AFTER_MINUTE = 45

# ==============================================================================
# 2. STREAMLIT SETUP
# ==============================================================================
st.set_page_config(page_title=APP_NAME, layout="wide", initial_sidebar_state="collapsed")

if "theme" not in st.session_state:
    st.session_state.theme = "dark"

if "cooldown_until" not in st.session_state:
    st.session_state.cooldown_until = None

if st.session_state.theme == "dark":
    primary_color = "#deff9a"
    secondary_color = "#00ffff"
    bg_color = "#0b0e11"
    text_color = "#e3e9f0"
    card_bg = "#14181f"
    border_color = "#2d3748"
    metric_label = "#8b949e"
    plot_paper = "#0b0e11"
    plot_bg = "#0b0e11"
    green = "#00ff66"
    red = "#ff3333"
    orange = "#ffaa00"
else:
    primary_color = "#2e7d32"
    secondary_color = "#0277bd"
    bg_color = "#f0f2f6"
    text_color = "#31333F"
    card_bg = "#ffffff"
    border_color = "#d1d5db"
    metric_label = "#555555"
    plot_paper = "#f0f2f6"
    plot_bg = "#ffffff"
    green = "#1b5e20"
    red = "#c62828"
    orange = "#ef6c00"

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
        background-color: {bg_color};
        color: {text_color};
    }}

    .stApp {{
        background-color: {bg_color};
    }}

    #MainMenu, footer, header {{
        visibility: hidden;
    }}

    [data-testid="collapsedControl"] {{
        display: none;
    }}

    div[data-testid="stMetricValue"] > div {{
        color: {primary_color} !important;
        font-size: 28px !important;
    }}

    div[data-testid="stMetricLabel"] > label {{
        color: {metric_label} !important;
        font-size: 13px !important;
        font-weight: 700 !important;
        letter-spacing: 0.5px;
    }}

    .signal-box {{
        background: {card_bg};
        padding: 12px;
        border-radius: 10px;
        border: 1px solid {border_color};
        font-weight: 700;
        margin-bottom: 12px;
        font-size: 15px;
    }}

    .ex-card {{
        background: {card_bg};
        border-radius: 12px;
        padding: 20px;
        border: 1px solid {border_color};
        margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }}

    .inst-box {{
        background: rgba(20, 24, 31, 0.05);
        padding: 12px;
        border-radius: 8px;
        border-left: 4px solid {secondary_color};
        margin-bottom: 10px;
        border-top: 1px solid {border_color};
        border-right: 1px solid {border_color};
        border-bottom: 1px solid {border_color};
    }}

    .status-badge {{
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 800;
        font-size: 12px;
        text-transform: uppercase;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

audio_code = """
<audio id="alert-sound" autoplay>
    <source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-500.wav" type="audio/wav">
</audio>
"""

# ==============================================================================
# 3. SHOONYA API
# ==============================================================================
def shoonya_login():
    if not SH_AVAILABLE:
        return None, "pyotp missing"

    if not SHOONYA_API_KEY or SHOONYA_API_KEY == "YOUR_API_KEY":
        return None, "No API Key"

    if not SHOONYA_PWD or SHOONYA_PWD == "YOUR_PASSWORD":
        return None, "No Password"

    if not SHOONYA_TOTP_SECRET or SHOONYA_TOTP_SECRET == "YOUR_TOTP_SECRET":
        return None, "No TOTP Secret"

    try:
        pwd_sha256 = hashlib.sha256(SHOONYA_PWD.encode("utf-8")).hexdigest()
        app_key_sha256 = hashlib.sha256(f"{SHOONYA_UID}|{SHOONYA_API_KEY}".encode("utf-8")).hexdigest()
        totp = pyotp.TOTP(SHOONYA_TOTP_SECRET).now()

        payload = {
            "apkversion": "1.0.0",
            "uid": SHOONYA_UID,
            "pwd": pwd_sha256,
            "factor2": totp,
            "vc": SHOONYA_VC,
            "appkey": app_key_sha256,
            "imei": "abc12345",
            "source": "API",
        }

        res = requests.post(
            "https://api.shoonya.com/NorenWClientTP/QuickAuth",
            data="jData=" + json.dumps(payload),
            timeout=8,
        )

        try:
            data = res.json()
        except ValueError:
            return None, f"HTTP {res.status_code}"

        if data.get("stat") == "Ok":
            return data.get("susertoken"), "Success"

        return None, data.get("emsg", "Unknown Error")

    except Exception as e:
        return None, str(e)


def get_shoonya_ltp(token, susertoken):
    if not susertoken:
        return None

    try:
        payload = {"uid": SHOONYA_UID, "exch": "NSE", "token": str(token)}
        headers = {"Authorization": f"Bearer {SHOONYA_UID} {susertoken}"}

        res = requests.post(
            "https://api.shoonya.com/NorenWClientTP/GetQuotes",
            data="jData=" + json.dumps(payload),
            headers=headers,
            timeout=5,
        )

        data = res.json()

        if data.get("stat") == "Ok" and data.get("lp"):
            return float(data.get("lp"))

        return None

    except Exception:
        return None


if "shoonya_token" not in st.session_state:
    token, msg = shoonya_login()
    st.session_state.shoonya_token = token
    st.session_state.shoonya_msg = msg

# ==============================================================================
# 4. DATA HELPERS
# ==============================================================================
def normalize_yf_data(df):
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df.index.tz is not None:
        df.index = df.index.tz_convert("Asia/Kolkata")
    else:
        df.index = df.index.tz_localize("UTC").tz_convert("Asia/Kolkata")

    return df


def safe_series(df, col):
    s = df[col]
    if isinstance(s, pd.DataFrame):
        return s.iloc[:, 0]
    return s


@st.cache_data(ttl=1800)
def fetch_daily_data_cached():
    df = yf.download("^NSEI", period="5d", interval="1d", progress=False, auto_adjust=False)
    return normalize_yf_data(df)


@st.cache_data(ttl=20)
def fetch_intraday_cached(symbol):
    df = yf.download(symbol, period="1d", interval="1m", progress=False, auto_adjust=False)
    return normalize_yf_data(df)


@st.cache_data(ttl=60)
def get_nse_pcr():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/option-chain",
        }

        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=5)

        res = session.get(
            "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
            headers=headers,
            timeout=5,
        )

        data = res.json()
        tot_ce = data["filtered"]["CE"]["totOI"]
        tot_pe = data["filtered"]["PE"]["totOI"]

        if tot_ce > 0:
            return round(tot_pe / tot_ce, 2)

        return None

    except Exception:
        return None


def save_trade(trade_data):
    df_new = pd.DataFrame([trade_data])

    if not os.path.exists(NIFTY_HISTORY_FILE):
        df_new.to_csv(NIFTY_HISTORY_FILE, index=False)
        return

    try:
        existing = pd.read_csv(NIFTY_HISTORY_FILE)

        if not all(col in existing.columns for col in EXPECTED_COLUMNS):
            df_new.to_csv(NIFTY_HISTORY_FILE, index=False)
            return

        is_duplicate = (
            (existing["Time (IST)"] == trade_data["Time (IST)"])
            & (existing["Asset"] == trade_data["Asset"])
            & (existing["Action"] == trade_data["Action"])
        ).any()

        if not is_duplicate:
            df_new.to_csv(NIFTY_HISTORY_FILE, mode="a", header=False, index=False)

    except Exception:
        df_new.to_csv(NIFTY_HISTORY_FILE, index=False)


def load_history():
    if not os.path.exists(NIFTY_HISTORY_FILE):
        return pd.DataFrame()

    try:
        df = pd.read_csv(NIFTY_HISTORY_FILE)
        return df.sort_index(ascending=False) if not df.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def style_results(val):
    text = str(val)

    if "TARGET" in text or "PROFIT" in text:
        return "background-color: rgba(0, 255, 102, 0.1); color: #00ff66; font-weight: bold;"

    if "SL HIT" in text or "LOSS" in text or "SQUARE-OFF" in text:
        return "background-color: rgba(255, 51, 51, 0.1); color: #ff3333; font-weight: bold;"

    return ""

# ==============================================================================
# 5. INDICATORS
# ==============================================================================
def add_indicators(df):
    df = df.copy()

    high = safe_series(df, "High")
    low = safe_series(df, "Low")
    close = safe_series(df, "Close")
    volume = safe_series(df, "Volume") if "Volume" in df.columns else pd.Series(0, index=df.index)

    if "Volume" in df.columns and volume.sum() > 0:
        tp = (high + low + close) / 3
        cum_vol = volume.cumsum() + 1e-10

        df["Baseline"] = (tp * volume).cumsum() / cum_vol
        df["VWAP_Variance"] = (((close - df["Baseline"]) ** 2) * volume).cumsum() / cum_vol
        df["VWAP_Std"] = np.sqrt(df["VWAP_Variance"])
        df["VAH"] = df["Baseline"] + df["VWAP_Std"]
        df["VAL"] = df["Baseline"] - df["VWAP_Std"]
        df["Volume_MA20"] = volume.rolling(20).mean()
    else:
        df["Baseline"] = close.ewm(span=50, adjust=False).mean()
        df["VAH"] = df["Baseline"] * 1.001
        df["VAL"] = df["Baseline"] * 0.999
        df["Volume_MA20"] = 0

    plus_dm = high.diff()
    minus_dm = low.diff()

    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0

    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.rolling(14).mean()

    df["ATR_14"] = atr
    df["+DI"] = 100 * (plus_dm.rolling(14).mean() / (atr + 1e-10))
    df["-DI"] = 100 * (abs(minus_dm).rolling(14).mean() / (atr + 1e-10))
    df["ADX_14"] = (
        (abs(df["+DI"] - df["-DI"]) / (df["+DI"] + df["-DI"] + 1e-10)) * 100
    ).rolling(14).mean()

    df["EMA_20"] = close.ewm(span=20, adjust=False).mean()
    df["EMA_50"] = close.ewm(span=50, adjust=False).mean()

    return df


def get_previous_day_levels(daily_df):
    if daily_df is None or daily_df.empty or len(daily_df) < 2:
        return 0.0, 0.0

    try:
        pdh = float(safe_series(daily_df, "High").iloc[-2])
        pdl = float(safe_series(daily_df, "Low").iloc[-2])
        return pdh, pdl
    except Exception:
        return 0.0, 0.0


def get_banknifty_alignment(banknifty_df):
    if banknifty_df is None or banknifty_df.empty or len(banknifty_df) < 60:
        return False, False, "UNKNOWN"

    close = safe_series(banknifty_df, "Close")
    bn_ltp = float(close.iloc[-1])
    bn_prev = float(close.iloc[-2])
    bn_baseline = float(close.ewm(span=50, adjust=False).mean().iloc[-1])

    bullish = bn_ltp > bn_baseline and bn_ltp > bn_prev
    bearish = bn_ltp < bn_baseline and bn_ltp < bn_prev

    if bullish:
        label = "BULLISH"
    elif bearish:
        label = "BEARISH"
    else:
        label = "NEUTRAL"

    return bullish, bearish, label

# ==============================================================================
# 6. IMPROVED ANTI-WHIPSAW ENGINE
# ==============================================================================
def calculate_quant_engine(df, symbol, banknifty_df=None, daily_df=None):
    df = df.copy()

    if st.session_state.shoonya_token and symbol in SH_TOKENS:
        live_ltp = get_shoonya_ltp(SH_TOKENS[symbol], st.session_state.shoonya_token)
        if live_ltp and not df.empty:
            df.at[df.index[-1], "Close"] = live_ltp

    df = add_indicators(df)
    pdh, pdl = get_previous_day_levels(daily_df)
    bn_bullish, bn_bearish, bn_label = get_banknifty_alignment(banknifty_df)

    df["AI_Score"] = 0
    df["Signal"] = "WAIT"
    df["Entry"] = 0.0
    df["Target"] = 0.0
    df["StopLoss"] = 0.0
    df["Status"] = ""
    df["Msg"] = "WAIT: Scanning high-probability setup..."

    active_trade = None

    start_idx = 60

    for i in range(start_idx, len(df)):
        curr_time = df.index[i].tz_convert("Asia/Kolkata")

        prev_c = float(df["Close"].iloc[i - 1])
        prev_h = float(df["High"].iloc[i - 1])
        prev_l = float(df["Low"].iloc[i - 1])
        prev_baseline = float(df["Baseline"].iloc[i - 1])
        prev_adx = float(df["ADX_14"].iloc[i - 1]) if pd.notna(df["ADX_14"].iloc[i - 1]) else 0.0
        prev_atr = float(df["ATR_14"].iloc[i - 1]) if pd.notna(df["ATR_14"].iloc[i - 1]) else 0.0

        curr_o = float(df["Open"].iloc[i])
        curr_h = float(df["High"].iloc[i])
        curr_l = float(df["Low"].iloc[i])
        curr_c = float(df["Close"].iloc[i])
        curr_vol = float(df["Volume"].iloc[i]) if "Volume" in df.columns else 0.0
        vol_ma20 = float(df["Volume_MA20"].iloc[i]) if pd.notna(df["Volume_MA20"].iloc[i]) else 0.0

        is_trade_window = (
            (curr_time.hour == 9 and curr_time.minute >= 45)
            or (curr_time.hour > 9 and curr_time.hour < NO_NEW_TRADE_AFTER_HOUR)
            or (curr_time.hour == NO_NEW_TRADE_AFTER_HOUR and curr_time.minute <= NO_NEW_TRADE_AFTER_MINUTE)
        )

        is_eod = curr_time.hour == 15 and curr_time.minute >= 15

        cooldown_active = (
            st.session_state.cooldown_until is not None
            and curr_time < st.session_state.cooldown_until
        )

        score = 0
        trend_dir = 0
        entry_price = 0.0
        msg = "WAIT: Setup not aligned."

        adx_rising = False
        if i - ADX_LOOKBACK >= 0 and pd.notna(df["ADX_14"].iloc[i - ADX_LOOKBACK]):
            adx_rising = prev_adx > float(df["ADX_14"].iloc[i - ADX_LOOKBACK])

        vol_ok = True
        if vol_ma20 > 0:
            vol_ok = curr_vol > vol_ma20 * VOLUME_MULTIPLIER

        not_overextended = True
        if prev_atr > 0:
            not_overextended = abs(prev_c - prev_baseline) < prev_atr * MAX_VWAP_DISTANCE_ATR

        bullish_break = False
        bearish_break = False

        if prev_atr > 0:
            bullish_break = curr_c > prev_h and (curr_c - prev_h) > prev_atr * BREAKOUT_ATR_BUFFER
            bearish_break = curr_c < prev_l and (prev_l - curr_c) > prev_atr * BREAKOUT_ATR_BUFFER

        above_vwap = prev_c > prev_baseline
        below_vwap = prev_c < prev_baseline

        no_trade_zone = abs(curr_c - prev_baseline) < max(prev_atr * 0.15, 3)

        filters_ok = (
            is_trade_window
            and not is_eod
            and not cooldown_active
            and prev_adx >= MIN_ADX
            and adx_rising
            and vol_ok
            and not_overextended
            and not no_trade_zone
        )

        if cooldown_active:
            msg = f"COOLDOWN: Waiting until {st.session_state.cooldown_until.strftime('%I:%M %p')} after SL."
        elif is_eod:
            msg = "EOD: Trading window closed."
        elif not is_trade_window:
            msg = "WAIT: Outside high-quality trading window."
        elif prev_adx < MIN_ADX:
            msg = f"WAIT: ADX weak ({round(prev_adx, 1)})."
        elif not adx_rising:
            msg = "WAIT: ADX not rising, trend power weak."
        elif not vol_ok:
            msg = "WAIT: Volume confirmation missing."
        elif not not_overextended:
            msg = "WAIT: Price overextended from VWAP."
        elif no_trade_zone:
            msg = "WAIT: Price inside VWAP chop zone."
        elif filters_ok:
            if above_vwap and bn_bullish:
                if bullish_break:
                    score = 100
                    trend_dir = 1
                    entry_price = max(prev_h, curr_o)
                    msg = "EXECUTE CE: Confirmed VWAP breakout with volume and BN alignment."
                else:
                    msg = "WAIT: Bullish structure ready, waiting candle-close breakout."
            elif below_vwap and bn_bearish:
                if bearish_break:
                    score = 100
                    trend_dir = -1
                    entry_price = min(prev_l, curr_o)
                    msg = "EXECUTE PE: Confirmed VWAP breakdown with volume and BN alignment."
                else:
                    msg = "WAIT: Bearish structure ready, waiting candle-close breakdown."
            else:
                msg = f"WAIT: BankNifty alignment not supportive ({bn_label})."

        df.at[df.index[i], "Msg"] = msg
        df.at[df.index[i], "AI_Score"] = score

        if active_trade is not None:
            trade_closed = False
            status_msg = ""
            exit_price = 0.0

            if is_eod:
                status_msg = "EOD SQUARE-OFF"
                trade_closed = True
                exit_price = curr_c

            elif active_trade["Direction"] == "LONG":
                if curr_h >= active_trade["Target"]:
                    status_msg = "TARGET HIT (+PROFIT)"
                    trade_closed = True
                    exit_price = active_trade["Target"]
                elif curr_l <= active_trade["StopLoss"]:
                    status_msg = "SL HIT (-LOSS)"
                    trade_closed = True
                    exit_price = active_trade["StopLoss"]

            elif active_trade["Direction"] == "SHORT":
                if curr_l <= active_trade["Target"]:
                    status_msg = "TARGET HIT (+PROFIT)"
                    trade_closed = True
                    exit_price = active_trade["Target"]
                elif curr_h >= active_trade["StopLoss"]:
                    status_msg = "SL HIT (-LOSS)"
                    trade_closed = True
                    exit_price = active_trade["StopLoss"]

            if trade_closed:
                trade_pts = round(
                    exit_price - active_trade["Entry"]
                    if active_trade["Direction"] == "LONG"
                    else active_trade["Entry"] - exit_price,
                    1,
                )

                trade_data = {
                    "Time (IST)": curr_time.strftime("%d-%b %I:%M %p"),
                    "Asset": "NIFTY 50",
                    "Action": active_trade["Type"],
                    "Spot Entry": active_trade["Entry"],
                    "Spot Exit": round(exit_price, 1),
                    "Points": trade_pts,
                    "Result": status_msg,
                }

                save_trade(trade_data)

                if "SL HIT" in status_msg:
                    st.session_state.cooldown_until = curr_time + datetime.timedelta(
                        minutes=COOLDOWN_MINUTES_AFTER_SL
                    )

                active_trade = None

        else:
            if score == 100 and trend_dir != 0 and is_trade_window:
                atm_strike = int(round(entry_price / 50) * 50)

                atr_sl_pts = max(MIN_ATR_SL, round(prev_atr * ATR_SL_MULTIPLIER, 1))

                if trend_dir == 1:
                    direction = "LONG"
                    t_type = f"{atm_strike} CE"
                    structure_sl = curr_l
                    sl = min(entry_price - atr_sl_pts, structure_sl)
                    risk = entry_price - sl
                    tgt = entry_price + risk * RR_MULTIPLIER
                    signal = f"BUY NIFTY {t_type}"

                else:
                    direction = "SHORT"
                    t_type = f"{atm_strike} PE"
                    structure_sl = curr_h
                    sl = max(entry_price + atr_sl_pts, structure_sl)
                    risk = sl - entry_price
                    tgt = entry_price - risk * RR_MULTIPLIER
                    signal = f"BUY NIFTY {t_type}"

                active_trade = {
                    "Type": t_type,
                    "Signal": signal,
                    "Entry": round(entry_price, 1),
                    "Target": round(tgt, 1),
                    "StopLoss": round(sl, 1),
                    "Direction": direction,
                    "Risk": round(risk, 1),
                }

                df.at[df.index[i], "Signal"] = active_trade["Signal"]
                df.at[df.index[i], "Entry"] = active_trade["Entry"]
                df.at[df.index[i], "Target"] = active_trade["Target"]
                df.at[df.index[i], "StopLoss"] = active_trade["StopLoss"]

    return df, active_trade

# ==============================================================================
# 7. UI HEADER
# ==============================================================================
header_col1, header_col2, header_theme = st.columns([10, 10, 3])

with header_col1:
    if st.session_state.shoonya_token:
        sh_status = f"<span style='color:{primary_color}; font-size:14px;'>Shoonya API Linked</span>"
    else:
        sh_status = f"<span style='color:{red}; font-size:14px;'>Shoonya API: {st.session_state.get('shoonya_msg', 'Disabled')}</span>"

    st.markdown(
        f"""
        <h1 style='margin:0; font-weight:800; color:{text_color};'>
            QUANT<span style='color:{primary_color};'>SCALPER AI</span> v19.0
            <span style='font-size:12px; color:{secondary_color};'>ANTI-WHIPSAW</span>
            <br>{sh_status}
        </h1>
        """,
        unsafe_allow_html=True,
    )

with header_col2:
    tz_ist = pytz.timezone("Asia/Kolkata")
    now = datetime.datetime.now(tz_ist)

    market_status = (
        "CLOSED"
        if now.hour >= 16 or now.hour < 9 or (now.hour == 15 and now.minute >= 30)
        else "LIVE"
    )

    st.markdown(
        f"""
        <div style='text-align:right; font-weight:700; color:#a0aec0; font-size:16px;'>
            {now.strftime('%d %b')} |
            <span style='color:{red if market_status == "CLOSED" else primary_color};'>
                {now.strftime('%I:%M:%S %p')} IST
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

with header_theme:
    btn_label = "Light" if st.session_state.theme == "dark" else "Dark"
    if st.button(btn_label, key="theme_btn"):
        st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"
        st.rerun()

st.markdown(
    f"<hr style='border-color:{border_color}; margin: 10px 0 15px 0;'>",
    unsafe_allow_html=True,
)

# ==============================================================================
# 8. MAIN APP
# ==============================================================================
try:
    daily_data = fetch_daily_data_cached()

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        f_nifty = executor.submit(fetch_intraday_cached, "^NSEI")
        f_bn = executor.submit(fetch_intraday_cached, "^NSEBANK")
        f_pcr = executor.submit(get_nse_pcr)

        data = f_nifty.result()
        bn_data = f_bn.result()
        pcr_val = f_pcr.result()

    if data.empty:
        st.error("NIFTY data empty. Check internet/data provider.")
    else:
        df, active_trade = calculate_quant_engine(data, "^NSEI", bn_data, daily_data)

        last = df.iloc[-1]
        curr_p = round(float(df["Close"].iloc[-1]), 2)
        day_open = round(float(df["Open"].iloc[0]), 2)
        pts = round(curr_p - day_open, 2)

        adx = float(last["ADX_14"]) if pd.notna(last["ADX_14"]) else 0.0
        atr = float(last["ATR_14"]) if pd.notna(last["ATR_14"]) else 0.0
        vwap = float(last["Baseline"]) if pd.notna(last["Baseline"]) else curr_p
        vah = float(last["VAH"]) if pd.notna(last["VAH"]) else curr_p
        val = float(last["VAL"]) if pd.notna(last["VAL"]) else curr_p
        pdh, pdl = get_previous_day_levels(daily_data)
        ai_msg = str(last["Msg"])
        atm_strike = int(round(curr_p / 50) * 50)

        bn_bullish, bn_bearish, bn_label = get_banknifty_alignment(bn_data)

        if bn_label == "BULLISH":
            bn_trend = "BULLISH"
        elif bn_label == "BEARISH":
            bn_trend = "BEARISH"
        else:
            bn_trend = "NEUTRAL"

        if active_trade is not None:
            color_cmd = orange
            txt_cmd = f"HOLD: {active_trade['Signal']} active. Entry {active_trade['Entry']}, SL {active_trade['StopLoss']}, Target {active_trade['Target']}."
        elif last["AI_Score"] == 100:
            color_cmd = green
            txt_cmd = f"EXECUTE: {last['Signal']} NOW."
            st.markdown(audio_code, unsafe_allow_html=True)
        elif market_status == "CLOSED":
            color_cmd = metric_label
            txt_cmd = "MARKET CLOSED: AI standby mode."
        else:
            color_cmd = metric_label
            txt_cmd = ai_msg

        st.markdown(
            f"""
            <div class='signal-box' style='border-left:5px solid {color_cmd}; color:{text_color};'>
                {txt_cmd}
            </div>
            """,
            unsafe_allow_html=True,
        )

        m1, m2, m3, m4 = st.columns(4)

        with m1:
            st.metric("NIFTY SPOT", f"₹{curr_p:,}", f"{pts} pts")

        with m2:
            st.metric("BankNifty Alignment", bn_trend)

        with m3:
            st.metric("Options PCR", f"{pcr_val}" if pcr_val else "Error")

        with m4:
            st.metric("VWAP / POC", f"₹{round(vwap, 1)}")

        st.markdown("<br>", unsafe_allow_html=True)

        col_met1, col_met2 = st.columns([1, 2])

        with col_met1:
            cooldown_text = "Inactive"
            if st.session_state.cooldown_until is not None:
                if now < st.session_state.cooldown_until:
                    cooldown_text = st.session_state.cooldown_until.strftime("%I:%M %p")
                else:
                    st.session_state.cooldown_until = None

            st.markdown(
                f"""
                <div class='inst-box' style='color:{text_color};'>
                    <div style='color:{metric_label}; font-size:11px; text-transform:uppercase;'>
                        Institutional Depth Analytics
                    </div>
                    <div style='margin-top:8px;'><b>ADX:</b> <span style='color:{green};'>{round(adx, 1)}</span></div>
                    <div><b>ATR:</b> <span style='color:{secondary_color};'>{round(atr, 1)} pts</span></div>
                    <div><b>VAH:</b> {round(vah, 1)}</div>
                    <div><b>VAL:</b> {round(val, 1)}</div>
                    <div><b>PDH:</b> {round(pdh, 1)}</div>
                    <div><b>PDL:</b> {round(pdl, 1)}</div>
                    <div><b>Cooldown:</b> {cooldown_text}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_met2:
            if active_trade is not None and market_status == "LIVE":
                color_trade = green if active_trade["Direction"] == "LONG" else red

                st.markdown(
                    f"""
                    <div class='ex-card' style='border: 2px solid {color_trade};'>
                        <div style='display:flex; justify-content:space-between;'>
                            <span class='status-badge' style='background:{bg_color}; border: 1px solid {color_trade}; color:{color_trade};'>
                                {active_trade['Direction']} ACTIVE
                            </span>
                            <span style='color:{secondary_color}; font-size: 12px;'>
                                Structure + ATR SL
                            </span>
                        </div>
                        <h2 style='margin:10px 0; color:{text_color};'>SPOT ENTRY: ₹{active_trade['Entry']}</h2>
                        <div style='color:{green}; font-weight:700; font-size:20px;'>TARGET: ₹{active_trade['Target']} ({RR_MULTIPLIER}:1 RR)</div>
                        <div style='color:{red}; font-weight:700; font-size:20px;'>STOP-LOSS: ₹{active_trade['StopLoss']}</div>
                        <div style='color:{metric_label}; font-size:13px;'>Risk: {active_trade.get('Risk', 0)} pts</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["VAH"],
                line=dict(width=0),
                showlegend=False,
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["VAL"],
                line=dict(width=0),
                fill="tonexty",
                fillcolor="rgba(0, 255, 255, 0.07)" if st.session_state.theme == "dark" else "rgba(0, 150, 136, 0.10)",
                name="Institutional Value Area",
            )
        )

        spot_color = "#deff9a" if st.session_state.theme == "dark" else "#004d40"

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["Close"],
                name="Spot Price",
                line=dict(color=spot_color, width=2.5),
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["Baseline"],
                name="VWAP / POC",
                line=dict(color=secondary_color, width=1.5, dash="dash"),
            )
        )

        if pdh > 0:
            fig.add_hline(
                y=pdh,
                line_dash="dot",
                line_color=orange,
                annotation_text="PDH",
                annotation_font_color=text_color,
            )

        if pdl > 0:
            fig.add_hline(
                y=pdl,
                line_dash="dot",
                line_color=orange,
                annotation_text="PDL",
                annotation_font_color=text_color,
            )

        fig.update_layout(
            template="plotly_dark" if st.session_state.theme == "dark" else "plotly_white",
            paper_bgcolor=plot_paper,
            plot_bgcolor=plot_bg,
            height=420,
            margin=dict(l=0, r=0, t=0, b=0),
            xaxis=dict(showgrid=False, tickfont_color=metric_label),
            yaxis=dict(gridcolor=border_color, tickfont_color=metric_label),
            legend_font_color=text_color,
        )

        st.plotly_chart(fig, use_container_width=True)

        st.markdown(
            f"<hr style='border-color:{border_color};'>",
            unsafe_allow_html=True,
        )

        tab_l1, tab_l2, tab_l3 = st.tabs(
            ["TRADING LOG", "SMC PROMPT", "FILTER STATUS"]
        )

        with tab_l1:
            n_hist = load_history()

            if not n_hist.empty:
                needed = n_hist[
                    ["Time (IST)", "Asset", "Action", "Spot Entry", "Spot Exit", "Points", "Result"]
                ]

                st.dataframe(
                    needed.style.applymap(style_results, subset=["Result"]),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No trades executed yet.")

        with tab_l2:
            st.markdown(
                f"<h3 style='color:{primary_color};'>Generate Institutional SMC Chat Prompt</h3>",
                unsafe_allow_html=True,
            )

            if st.button("Generate Master Market Analysis Prompt", key="gen_prompt_btn"):
                current_vwap_pos = "Above" if curr_p > vwap else "Below"
                current_va_pos = "Inside" if val < curr_p < vah else "Outside"

                if not pcr_val:
                    pcr_status = "Unknown"
                elif pcr_val > 1.2:
                    pcr_status = "Very Bullish"
                elif pcr_val > 1.0:
                    pcr_status = "Bullish"
                elif pcr_val < 0.8:
                    pcr_status = "Very Bearish"
                else:
                    pcr_status = "Bearish"

                scalper_chat_prompt = f"""You are an Institutional Quant Trader, SMC Analyst, and high-frequency NIFTY option scalper.

Analyze the live market strictly using this data.

LIVE MARKET DATA
- Nifty Spot Price: ₹{curr_p}
- Day Change: {pts} pts
- Current ATR 1m: {round(atr, 1)}
- ADX Trend Strength: {round(adx, 1)}
- VWAP / POC: ₹{round(vwap, 1)}
- Value Area High: ₹{round(vah, 1)}
- Value Area Low: ₹{round(val, 1)}
- Previous Day High: {round(pdh, 1)}
- Previous Day Low: {round(pdl, 1)}
- Options PCR: {pcr_val} ({pcr_status})
- BankNifty Alignment: {bn_trend}
- AI Context: {ai_msg}
- Price vs VWAP: {current_vwap_pos}
- Value Area Position: {current_va_pos}
- ATM Strike: {atm_strike}

REQUIRED OUTPUT
1. Market Bias
2. Institutional Direction
3. Liquidity Trap Warning
4. Best Trade: BUY CE, BUY PE, or NO TRADE
5. If trade is valid: ATM strike, spot entry, target, stop-loss
6. Confidence score

STRICT RULES
- Be concise.
- No education.
- Speak like a prop-desk scalper.
- Prioritize capital protection.
"""

                st.text_area(
                    "Copy this prompt into your analysis chat:",
                    value=scalper_chat_prompt,
                    height=450,
                )

        with tab_l3:
            last_idx = len(df) - 1

            if last_idx >= 60:
                prev_adx = float(df["ADX_14"].iloc[-2]) if pd.notna(df["ADX_14"].iloc[-2]) else 0.0
                adx_ref = float(df["ADX_14"].iloc[-1 - ADX_LOOKBACK]) if pd.notna(df["ADX_14"].iloc[-1 - ADX_LOOKBACK]) else 0.0
                adx_rising_now = prev_adx > adx_ref

                curr_vol = float(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0.0
                vol_ma20 = float(df["Volume_MA20"].iloc[-1]) if pd.notna(df["Volume_MA20"].iloc[-1]) else 0.0
                vol_ok_now = curr_vol > vol_ma20 * VOLUME_MULTIPLIER if vol_ma20 > 0 else True

                vwap_distance = abs(curr_p - vwap)
                not_overextended_now = vwap_distance < atr * MAX_VWAP_DISTANCE_ATR if atr > 0 else True

                status_df = pd.DataFrame(
                    [
                        ["ADX above minimum", prev_adx >= MIN_ADX, round(prev_adx, 1)],
                        ["ADX rising", adx_rising_now, f"{round(adx_ref, 1)} → {round(prev_adx, 1)}"],
                        ["Volume confirmation", vol_ok_now, f"{int(curr_vol)} / MA20 {int(vol_ma20)}"],
                        ["VWAP not overextended", not_overextended_now, round(vwap_distance, 1)],
                        ["BankNifty aligned", bn_label in ["BULLISH", "BEARISH"], bn_label],
                        ["Trading window", market_status == "LIVE", market_status],
                    ],
                    columns=["Filter", "Pass", "Value"],
                )

                st.dataframe(status_df, use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"Error Nifty: {e}")

time.sleep(8)
st.rerun()
