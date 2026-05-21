import datetime as dt
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytz
import requests
import streamlit as st
import yfinance as yf


APP_NAME = "QuantScalper AI Pro"
APP_VERSION = "v20.0"
IST = pytz.timezone("Asia/Kolkata")
DATA_DIR = Path("data")
TRADE_BOOK = DATA_DIR / "trade_book.csv"
SIGNAL_BOOK = DATA_DIR / "signal_book.csv"
SETTINGS_FILE = DATA_DIR / "settings.json"

BASE_SETTINGS = {
    "min_confidence": 82,
    "min_adx": 24,
    "volume_multiplier": 1.20,
    "max_vwap_distance_atr": 1.20,
    "breakout_atr_buffer": 0.25,
    "min_sl_points": 18.0,
    "atr_sl_multiplier": 1.50,
    "rr_multiplier": 2.00,
    "cooldown_after_loss_min": 20,
    "max_trades_per_day": 4,
    "first_trade_after": "09:45",
    "last_trade_before": "14:45",
}

TRADE_COLUMNS = [
    "id",
    "date",
    "time",
    "side",
    "strike",
    "entry",
    "target",
    "stoploss",
    "exit",
    "points",
    "result",
    "confidence",
    "reason",
    "mistake_tag",
]

SIGNAL_COLUMNS = [
    "id",
    "date",
    "time",
    "side",
    "strike",
    "entry",
    "target",
    "stoploss",
    "confidence",
    "status",
    "reason",
    "blocked_by",
]


st.set_page_config(
    page_title=f"{APP_NAME} {APP_VERSION}",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def ensure_files():
    DATA_DIR.mkdir(exist_ok=True)
    if not TRADE_BOOK.exists():
        pd.DataFrame(columns=TRADE_COLUMNS).to_csv(TRADE_BOOK, index=False)
    if not SIGNAL_BOOK.exists():
        pd.DataFrame(columns=SIGNAL_COLUMNS).to_csv(SIGNAL_BOOK, index=False)
    if not SETTINGS_FILE.exists():
        SETTINGS_FILE.write_text(json.dumps(BASE_SETTINGS, indent=2), encoding="utf-8")


def load_settings():
    ensure_files()
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return {**BASE_SETTINGS, **saved}
    except Exception:
        return BASE_SETTINGS.copy()


def save_settings(settings):
    ensure_files()
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def read_csv(path, columns):
    ensure_files()
    try:
        df = pd.read_csv(path)
        for col in columns:
            if col not in df.columns:
                df[col] = np.nan
        return df[columns]
    except Exception:
        return pd.DataFrame(columns=columns)


def append_row(path, columns, row):
    df = read_csv(path, columns)
    row = {col: row.get(col, "") for col in columns}
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(path, index=False)


def now_ist():
    return dt.datetime.now(IST)


def parse_hhmm(value):
    hour, minute = value.split(":")
    return int(hour), int(minute)


def in_time_window(ts, settings):
    start_h, start_m = parse_hhmm(settings["first_trade_after"])
    end_h, end_m = parse_hhmm(settings["last_trade_before"])
    start = ts.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = ts.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    return start <= ts <= end


def market_status(ts):
    open_time = ts.replace(hour=9, minute=15, second=0, microsecond=0)
    close_time = ts.replace(hour=15, minute=30, second=0, microsecond=0)
    if ts.weekday() >= 5:
        return "CLOSED"
    return "LIVE" if open_time <= ts <= close_time else "CLOSED"


@st.cache_data(ttl=20)
def fetch_intraday(symbol):
    df = yf.download(symbol, period="1d", interval="1m", progress=False, auto_adjust=False)
    return normalize_yf(df)


@st.cache_data(ttl=1800)
def fetch_daily(symbol):
    df = yf.download(symbol, period="7d", interval="1d", progress=False, auto_adjust=False)
    return normalize_yf(df)


@st.cache_data(ttl=60)
def fetch_pcr():
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
        ce = data["filtered"]["CE"]["totOI"]
        pe = data["filtered"]["PE"]["totOI"]
        return round(pe / ce, 2) if ce else None
    except Exception:
        return None


def normalize_yf(df):
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(IST)
    else:
        df.index = df.index.tz_convert(IST)
    return df


def safe_series(df, col):
    value = df[col]
    if isinstance(value, pd.DataFrame):
        return value.iloc[:, 0]
    return value


def add_indicators(df):
    df = df.copy()
    high = safe_series(df, "High")
    low = safe_series(df, "Low")
    close = safe_series(df, "Close")
    volume = safe_series(df, "Volume") if "Volume" in df.columns else pd.Series(0, index=df.index)

    tp = (high + low + close) / 3
    if volume.sum() > 0:
        cum_vol = volume.cumsum() + 1e-10
        df["VWAP"] = (tp * volume).cumsum() / cum_vol
        df["VWAP_VAR"] = (((close - df["VWAP"]) ** 2) * volume).cumsum() / cum_vol
        df["VWAP_STD"] = np.sqrt(df["VWAP_VAR"])
        df["VAH"] = df["VWAP"] + df["VWAP_STD"]
        df["VAL"] = df["VWAP"] - df["VWAP_STD"]
        df["VOL_MA20"] = volume.rolling(20).mean()
    else:
        df["VWAP"] = close.ewm(span=50, adjust=False).mean()
        df["VAH"] = df["VWAP"] * 1.001
        df["VAL"] = df["VWAP"] * 0.999
        df["VOL_MA20"] = 0

    plus_dm = high.diff()
    minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0

    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(14).mean()
    df["ATR"] = atr
    df["+DI"] = 100 * plus_dm.rolling(14).mean() / (atr + 1e-10)
    df["-DI"] = 100 * abs(minus_dm).rolling(14).mean() / (atr + 1e-10)
    df["ADX"] = (abs(df["+DI"] - df["-DI"]) / (df["+DI"] + df["-DI"] + 1e-10) * 100).rolling(14).mean()
    df["EMA20"] = close.ewm(span=20, adjust=False).mean()
    df["EMA50"] = close.ewm(span=50, adjust=False).mean()
    df["RANGE20_HIGH"] = high.rolling(20).max().shift(1)
    df["RANGE20_LOW"] = low.rolling(20).min().shift(1)
    return df


def previous_day_levels(daily):
    if daily.empty or len(daily) < 2:
        return 0.0, 0.0
    return float(daily["High"].iloc[-2]), float(daily["Low"].iloc[-2])


def pcr_bias(pcr):
    if pcr is None:
        return "UNKNOWN"
    if pcr >= 1.20:
        return "BULLISH"
    if pcr <= 0.80:
        return "BEARISH"
    return "NEUTRAL"


def banknifty_bias(bn):
    if bn.empty or len(bn) < 60:
        return "UNKNOWN"
    bn = add_indicators(bn)
    close = safe_series(bn, "Close")
    last = bn.iloc[-1]
    if close.iloc[-1] > last["VWAP"] and close.iloc[-1] > last["EMA50"] and close.iloc[-1] > close.iloc[-2]:
        return "BULLISH"
    if close.iloc[-1] < last["VWAP"] and close.iloc[-1] < last["EMA50"] and close.iloc[-1] < close.iloc[-2]:
        return "BEARISH"
    return "NEUTRAL"


def trade_stats():
    book = read_csv(TRADE_BOOK, TRADE_COLUMNS)
    if book.empty:
        return {
            "today_count": 0,
            "loss_streak": 0,
            "win_rate": 0,
            "net_points": 0,
            "last_result": "",
        }
    today = now_ist().strftime("%Y-%m-%d")
    today_book = book[book["date"].astype(str) == today]
    results = book["result"].dropna().astype(str).tolist()
    loss_streak = 0
    for result in reversed(results):
        if "LOSS" in result or "SL" in result:
            loss_streak += 1
        elif "TARGET" in result or "PROFIT" in result:
            break
    wins = book["result"].astype(str).str.contains("TARGET|PROFIT", regex=True).sum()
    closed = book["result"].astype(str).str.contains("TARGET|PROFIT|SL|LOSS|EXIT", regex=True).sum()
    points = pd.to_numeric(book["points"], errors="coerce").fillna(0).sum()
    return {
        "today_count": len(today_book),
        "loss_streak": loss_streak,
        "win_rate": round((wins / closed * 100), 1) if closed else 0,
        "net_points": round(points, 1),
        "last_result": results[-1] if results else "",
    }


def adaptive_settings(settings, stats):
    adjusted = settings.copy()
    warnings = []
    if stats["loss_streak"] >= 2:
        adjusted["min_confidence"] = max(adjusted["min_confidence"], 90)
        adjusted["min_adx"] = max(adjusted["min_adx"], 28)
        adjusted["volume_multiplier"] = max(adjusted["volume_multiplier"], 1.35)
        warnings.append("Loss streak guard active: only elite setups allowed.")
    if stats["today_count"] >= settings["max_trades_per_day"]:
        warnings.append("Daily trade limit reached.")
    return adjusted, warnings


def build_signal(nifty, banknifty, daily, pcr, settings):
    stats = trade_stats()
    active_settings, guard_warnings = adaptive_settings(settings, stats)

    if nifty.empty or len(nifty) < 80:
        return None, {"status": "BLOCKED", "reason": "Not enough NIFTY data.", "checks": []}

    df = add_indicators(nifty)
    last = df.iloc[-1]
    prev = df.iloc[-2]
    ts = df.index[-1].to_pydatetime()
    curr = float(last["Close"])
    atr = float(last["ATR"]) if pd.notna(last["ATR"]) else 0
    adx = float(last["ADX"]) if pd.notna(last["ADX"]) else 0
    vwap = float(last["VWAP"])
    pdh, pdl = previous_day_levels(daily)
    bn_bias = banknifty_bias(banknifty)
    pcr_state = pcr_bias(pcr)

    adx_ref = float(df["ADX"].iloc[-6]) if pd.notna(df["ADX"].iloc[-6]) else 0
    adx_rising = adx > adx_ref
    volume = float(last["Volume"]) if "Volume" in df.columns else 0
    vol_ma = float(last["VOL_MA20"]) if pd.notna(last["VOL_MA20"]) else 0
    vol_ok = volume > vol_ma * active_settings["volume_multiplier"] if vol_ma > 0 else True
    vwap_distance_ok = abs(curr - vwap) <= atr * active_settings["max_vwap_distance_atr"] if atr > 0 else False
    chop_zone = abs(curr - vwap) < max(atr * 0.15, 3) if atr > 0 else True
    time_ok = in_time_window(ts, active_settings)
    market_ok = market_status(now_ist()) == "LIVE"
    daily_limit_ok = stats["today_count"] < settings["max_trades_per_day"]

    bullish_break = (
        curr > float(prev["High"])
        and curr > float(last["RANGE20_HIGH"])
        and (curr - float(prev["High"])) > atr * active_settings["breakout_atr_buffer"]
    )
    bearish_break = (
        curr < float(prev["Low"])
        and curr < float(last["RANGE20_LOW"])
        and (float(prev["Low"]) - curr) > atr * active_settings["breakout_atr_buffer"]
    )

    ce_context = curr > vwap and curr > float(last["EMA50"]) and bn_bias == "BULLISH"
    pe_context = curr < vwap and curr < float(last["EMA50"]) and bn_bias == "BEARISH"

    checks = [
        ("Market live", market_ok),
        ("Trading window", time_ok),
        ("Daily trade limit", daily_limit_ok),
        ("ADX strong", adx >= active_settings["min_adx"]),
        ("ADX rising", adx_rising),
        ("Volume confirmed", vol_ok),
        ("Not overextended", vwap_distance_ok),
        ("Not in VWAP chop", not chop_zone),
        ("BankNifty aligned", bn_bias in ["BULLISH", "BEARISH"]),
    ]

    blocked_by = [name for name, ok in checks if not ok]
    side = "NO TRADE"
    if ce_context and bullish_break:
        side = "CE"
    elif pe_context and bearish_break:
        side = "PE"
    else:
        blocked_by.append("No confirmed CE/PE breakout")

    confluence = sum(1 for _, ok in checks if ok)
    confidence = min(99, int((confluence / len(checks)) * 78))
    if side != "NO TRADE":
        confidence += 12
    if pcr_state == "BULLISH" and side == "CE":
        confidence += 5
    if pcr_state == "BEARISH" and side == "PE":
        confidence += 5
    if (curr > pdh and side == "CE") or (curr < pdl and side == "PE"):
        confidence += 4
    confidence = min(confidence, 99)

    if confidence < active_settings["min_confidence"]:
        blocked_by.append(f"Confidence below {active_settings['min_confidence']}%")

    status = "READY" if side != "NO TRADE" and not blocked_by else "BLOCKED"
    strike = int(round(curr / 50) * 50)
    risk = max(active_settings["min_sl_points"], atr * active_settings["atr_sl_multiplier"])

    if side == "CE":
        entry = max(curr, float(prev["High"]))
        stoploss = min(entry - risk, float(last["Low"]))
        target = entry + (entry - stoploss) * active_settings["rr_multiplier"]
        reason = "CE only after close above prior high, range high, VWAP and BankNifty alignment."
    elif side == "PE":
        entry = min(curr, float(prev["Low"]))
        stoploss = max(entry + risk, float(last["High"]))
        target = entry - (stoploss - entry) * active_settings["rr_multiplier"]
        reason = "PE only after close below prior low, range low, VWAP and BankNifty alignment."
    else:
        entry = curr
        stoploss = 0
        target = 0
        reason = "No high-probability setup."

    signal = {
        "id": ts.strftime("%Y%m%d%H%M"),
        "date": ts.strftime("%Y-%m-%d"),
        "time": ts.strftime("%H:%M"),
        "side": side,
        "strike": strike,
        "entry": round(entry, 1),
        "target": round(target, 1),
        "stoploss": round(stoploss, 1),
        "confidence": confidence,
        "status": status,
        "reason": reason,
        "blocked_by": ", ".join(dict.fromkeys(blocked_by)),
        "price": round(curr, 2),
        "vwap": round(vwap, 1),
        "adx": round(adx, 1),
        "atr": round(atr, 1),
        "pdh": round(pdh, 1),
        "pdl": round(pdl, 1),
        "bn_bias": bn_bias,
        "pcr": pcr,
        "pcr_state": pcr_state,
        "guard_warnings": guard_warnings,
    }

    return signal, {"status": status, "reason": reason, "checks": checks, "df": df}


def save_signal_once(signal):
    book = read_csv(SIGNAL_BOOK, SIGNAL_COLUMNS)
    if signal["id"] not in book["id"].astype(str).tolist():
        append_row(SIGNAL_BOOK, SIGNAL_COLUMNS, signal)


def record_trade(signal, result, exit_price, mistake_tag=""):
    entry = float(signal["entry"])
    side = signal["side"]
    points = exit_price - entry if side == "CE" else entry - exit_price
    row = {
        "id": f'{signal["id"]}-{result}',
        "date": now_ist().strftime("%Y-%m-%d"),
        "time": now_ist().strftime("%H:%M:%S"),
        "side": side,
        "strike": signal["strike"],
        "entry": entry,
        "target": signal["target"],
        "stoploss": signal["stoploss"],
        "exit": round(exit_price, 1),
        "points": round(points, 1),
        "result": result,
        "confidence": signal["confidence"],
        "reason": signal["reason"],
        "mistake_tag": mistake_tag,
    }
    append_row(TRADE_BOOK, TRADE_COLUMNS, row)


def css():
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.3rem; padding-left: 1.5rem; padding-right: 1.5rem; max-width: 100%;}
        header, footer, #MainMenu {visibility: hidden;}
        .stApp {background: #080b0f; color: #e6edf3;}
        .topbar {display:flex; justify-content:space-between; align-items:center; border:1px solid #263241; border-radius:12px; padding:16px 18px; background:#10151d;}
        .brand {font-size:28px; font-weight:900; color:#e6edf3;}
        .accent {color:#deff9a;}
        .subtle {color:#8b949e; font-size:12px; font-weight:700;}
        .pill {display:inline-block; padding:5px 10px; border-radius:999px; border:1px solid #263241; font-size:12px; font-weight:900;}
        .card {background:#10151d; border:1px solid #263241; border-radius:12px; padding:16px; min-height:104px;}
        .label {font-size:11px; color:#8b949e; text-transform:uppercase; font-weight:900;}
        .value {font-size:27px; color:#deff9a; font-weight:900; margin-top:5px;}
        .small {font-size:12px; color:#8b949e; font-weight:700;}
        .command {border-radius:12px; padding:18px; border:1px solid #263241; background:#10151d; margin:14px 0;}
        .command-ready {border-left:6px solid #00ff66;}
        .command-blocked {border-left:6px solid #ff4d4d;}
        .command-title {font-size:12px; color:#8b949e; font-weight:900; text-transform:uppercase;}
        .command-main {font-size:26px; color:#e6edf3; font-weight:900; margin-top:6px;}
        .ok {color:#00ff66; font-weight:900;}
        .bad {color:#ff4d4d; font-weight:900;}
        .warn {color:#ffaa00; font-weight:900;}
        div[data-testid="stDataFrame"] {border:1px solid #263241; border-radius:10px;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(status):
    ts = now_ist()
    color = "#00ff66" if status == "LIVE" else "#ff4d4d"
    st.markdown(
        f"""
        <div class="topbar">
            <div>
                <div class="brand">QUANT<span class="accent">SCALPER AI</span> PRO <span class="subtle">{APP_VERSION}</span></div>
                <div class="subtle">Manual execution terminal | Data, rules, journal and mistake control</div>
            </div>
            <div style="text-align:right">
                <span class="pill" style="color:{color};">{status}</span>
                <div class="subtle" style="margin-top:8px;">{ts.strftime("%d %b %Y | %I:%M:%S %p IST")}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_card(label, value, sub="", color="#deff9a"):
    st.markdown(
        f"""
        <div class="card">
            <div class="label">{label}</div>
            <div class="value" style="color:{color};">{value}</div>
            <div class="small">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_chart(df, signal):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["VAH"], line=dict(width=0), showlegend=False))
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["VAL"],
            line=dict(width=0),
            fill="tonexty",
            fillcolor="rgba(0,255,255,0.06)",
            name="Value Area",
        )
    )
    fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="NIFTY", line=dict(color="#deff9a", width=2.4)))
    fig.add_trace(go.Scatter(x=df.index, y=df["VWAP"], name="VWAP", line=dict(color="#00ffff", width=1.5, dash="dash")))
    fig.add_hline(y=signal["price"], line_color="#ffffff", line_width=1, annotation_text="LTP")
    if signal["status"] == "READY":
        fig.add_hline(y=signal["entry"], line_color="#00ffff", line_dash="dash", annotation_text="ENTRY")
        fig.add_hline(y=signal["target"], line_color="#00ff66", line_dash="dot", annotation_text="TARGET")
        fig.add_hline(y=signal["stoploss"], line_color="#ff4d4d", line_dash="dot", annotation_text="SL")
    if signal["pdh"] > 0:
        fig.add_hline(y=signal["pdh"], line_color="#ffaa00", line_dash="dot", annotation_text="PDH")
    if signal["pdl"] > 0:
        fig.add_hline(y=signal["pdl"], line_color="#ffaa00", line_dash="dot", annotation_text="PDL")
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#080b0f",
        plot_bgcolor="#080b0f",
        height=430,
        margin=dict(l=8, r=8, t=12, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor="#263241"),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_settings(settings):
    with st.expander("Risk Engine Settings", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        settings["min_confidence"] = c1.slider("Minimum confidence", 70, 95, int(settings["min_confidence"]))
        settings["min_adx"] = c2.slider("Minimum ADX", 18, 35, int(settings["min_adx"]))
        settings["volume_multiplier"] = c3.slider("Volume multiplier", 1.0, 2.0, float(settings["volume_multiplier"]), 0.05)
        settings["max_trades_per_day"] = c4.slider("Max trades per day", 1, 8, int(settings["max_trades_per_day"]))
        c5, c6, c7, c8 = st.columns(4)
        settings["rr_multiplier"] = c5.slider("Reward risk", 1.0, 3.0, float(settings["rr_multiplier"]), 0.25)
        settings["atr_sl_multiplier"] = c6.slider("ATR SL multiplier", 1.0, 2.5, float(settings["atr_sl_multiplier"]), 0.1)
        settings["first_trade_after"] = c7.text_input("First trade after", settings["first_trade_after"])
        settings["last_trade_before"] = c8.text_input("Last trade before", settings["last_trade_before"])
        if st.button("Save Settings"):
            save_settings(settings)
            st.success("Settings saved.")


def render_manual_trade_panel(signal):
    st.subheader("Manual Shoonya Execution Plan")
    if signal["status"] != "READY":
        st.error("Trade blocked. Do not take manual trade.")
        st.caption(signal["blocked_by"])
        return

    side = signal["side"]
    option_name = f'NIFTY {signal["strike"]} {side}'
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Option", option_name)
    c2.metric("Spot Entry", signal["entry"])
    c3.metric("Spot Target", signal["target"])
    c4.metric("Spot SL", signal["stoploss"])

    st.warning("Take this trade manually in Shoonya only if the live Shoonya price still matches this setup.")
    confirm = st.checkbox("I checked Shoonya app price, spread, quantity and risk before entering.")
    if confirm:
        save_signal_once(signal)
        st.success("Signal saved. After exit, record result below.")

    with st.form("record_result"):
        exit_price = st.number_input("Spot exit price", value=float(signal["target"]), step=0.5)
        result = st.selectbox("Result", ["TARGET HIT (+PROFIT)", "SL HIT (-LOSS)", "MANUAL EXIT", "SKIPPED"])
        mistake = st.selectbox(
            "Mistake tag",
            ["None", "Late entry", "Chasing", "Ignored spread", "News spike", "Against trend", "Manual override"],
        )
        submitted = st.form_submit_button("Save Trade Result")
        if submitted:
            record_trade(signal, result, float(exit_price), mistake)
            st.success("Trade saved in journal.")


def style_result(val):
    text = str(val)
    if "TARGET" in text or "PROFIT" in text:
        return "color:#00ff66; font-weight:900;"
    if "SL" in text or "LOSS" in text:
        return "color:#ff4d4d; font-weight:900;"
    return "color:#ffaa00; font-weight:900;"


def main():
    ensure_files()
    css()
    settings = load_settings()
    status = market_status(now_ist())
    render_header(status)
    render_settings(settings)

    try:
        nifty = fetch_intraday("^NSEI")
        banknifty = fetch_intraday("^NSEBANK")
        daily = fetch_daily("^NSEI")
        pcr = fetch_pcr()
    except Exception as exc:
        st.error(f"Data fetch error: {exc}")
        time.sleep(8)
        st.rerun()

    signal, context = build_signal(nifty, banknifty, daily, pcr, settings)
    if signal is None:
        st.error(context["reason"])
        time.sleep(8)
        st.rerun()

    command_class = "command-ready" if signal["status"] == "READY" else "command-blocked"
    command = (
        f'BUY NIFTY {signal["strike"]} {signal["side"]} | Confidence {signal["confidence"]}%'
        if signal["status"] == "READY"
        else f'NO TRADE | {signal["blocked_by"]}'
    )
    st.markdown(
        f"""
        <div class="command {command_class}">
            <div class="command-title">AI Trade Command</div>
            <div class="command-main">{command}</div>
            <div class="small">{signal["reason"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if signal["guard_warnings"]:
        for warning in signal["guard_warnings"]:
            st.warning(warning)

    stats = trade_stats()
    c1, c2, c3, c4, c5 = st.columns(5)
    render_card("NIFTY Spot", f'Rs {signal["price"]}', f'VWAP Rs {signal["vwap"]}')
    with c2:
        color = "#00ff66" if signal["bn_bias"] == "BULLISH" else "#ff4d4d" if signal["bn_bias"] == "BEARISH" else "#ffaa00"
        render_card("BankNifty", signal["bn_bias"], "Alignment filter", color)
    with c3:
        render_card("ADX / ATR", f'{signal["adx"]} / {signal["atr"]}', "Trend and risk")
    with c4:
        render_card("PCR", signal["pcr"] if signal["pcr"] else "Error", signal["pcr_state"])
    with c5:
        color = "#00ff66" if stats["net_points"] >= 0 else "#ff4d4d"
        render_card("Journal P/L", f'{stats["net_points"]} pts', f'Win rate {stats["win_rate"]}%', color)

    left, right = st.columns([2.2, 1])
    with left:
        render_chart(context["df"], signal)
    with right:
        st.subheader("Filter Checklist")
        checks_df = pd.DataFrame(
            [{"Check": name, "Status": "PASS" if ok else "FAIL"} for name, ok in context["checks"]]
        )
        st.dataframe(checks_df, use_container_width=True, hide_index=True)
        st.caption(f'Blocked by: {signal["blocked_by"] or "None"}')

    tab1, tab2, tab3, tab4 = st.tabs(["Execution", "Trade Journal", "Signal Log", "Mistake Analysis"])
    with tab1:
        render_manual_trade_panel(signal)

    with tab2:
        book = read_csv(TRADE_BOOK, TRADE_COLUMNS).sort_index(ascending=False)
        if book.empty:
            st.info("No trades saved yet.")
        else:
            st.dataframe(book.style.map(style_result, subset=["result"]), use_container_width=True, hide_index=True)

    with tab3:
        signals = read_csv(SIGNAL_BOOK, SIGNAL_COLUMNS).sort_index(ascending=False)
        st.dataframe(signals, use_container_width=True, hide_index=True)

    with tab4:
        book = read_csv(TRADE_BOOK, TRADE_COLUMNS)
        if book.empty:
            st.info("Mistake analysis will appear after saved trades.")
        else:
            result_summary = book["result"].value_counts().reset_index()
            result_summary.columns = ["Result", "Count"]
            mistake_summary = book["mistake_tag"].replace("", "None").value_counts().reset_index()
            mistake_summary.columns = ["Mistake", "Count"]
            a, b = st.columns(2)
            a.dataframe(result_summary, use_container_width=True, hide_index=True)
            b.dataframe(mistake_summary, use_container_width=True, hide_index=True)
            if stats["loss_streak"] >= 2:
                st.error("Self-correction active: confidence, ADX and volume filters are tightened.")
            elif stats["win_rate"] < 45 and len(book) >= 10:
                st.warning("Win rate is weak. Reduce trade count and take only READY signals above 90% confidence.")
            else:
                st.success("Risk engine normal.")

    time.sleep(8)
    st.rerun()


if __name__ == "__main__":
    main()
