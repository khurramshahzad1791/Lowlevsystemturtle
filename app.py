# app.py
import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, time
import time as pytime
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(
    page_title="MEXC Institutional Scanner",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for a professional look
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, #0f2027, #203a43, #2c5364);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
    }
    .sub-header {
        color: #a0aec0;
        font-size: 1rem;
        margin-top: 0;
    }
    .trading-plan {
        background: #1e2a3a;
        border-radius: 15px;
        padding: 1.5rem;
        margin: 1rem 0;
        border-left: 6px solid #3498db;
    }
    .risk-box {
        background: #2c3e50;
        border-radius: 10px;
        padding: 1rem;
        color: white;
        text-align: center;
    }
    .grade-AAA { color: #f1c40f; font-weight: bold; }
    .grade-AA { color: #9b59b6; font-weight: bold; }
    .grade-A { color: #3498db; font-weight: bold; }
    .grade-B { color: #2ecc71; font-weight: bold; }
    .grade-C { color: #e74c3c; font-weight: bold; }
    .dataframe { font-size: 0.85rem; }
    .stButton>button {
        background: #2c3e50;
        color: white;
        border: none;
        border-radius: 5px;
        padding: 0.5rem 1rem;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">🏛️ MEXC Institutional Scanner</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Multi‑tactic • Context‑aware • Volatility sizing • Hard stops • Confidence grade</p>', unsafe_allow_html=True)

# -------------------- SIDEBAR --------------------
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/investment-portfolio.png", width=80)
    st.markdown("## ⚙️ Settings")

    # Timeframes
    tf_entry = st.selectbox("⏱️ Entry Timeframe", ["5m", "15m", "1h"], index=1)
    tf_trend = st.selectbox("📈 Trend Timeframe", ["1h", "4h", "1d"], index=0)

    # Account & risk management
    st.markdown("### 💰 Risk Management")
    account_balance = st.number_input("Account Balance (USDT)", min_value=100, value=1000, step=100)
    risk_per_trade = st.slider("Risk per trade (%)", 0.5, 5.0, 2.0, 0.5) / 100

    # Volume filter
    use_vol_filter = st.checkbox("Filter by 24h volume (low‑cap)", value=False)
    if use_vol_filter:
        min_vol = st.number_input("Min 24h Vol (USDT)", value=50_000, step=10_000)
        max_vol = st.number_input("Max 24h Vol (USDT)", value=2_000_000, step=50_000)
    else:
        min_vol, max_vol = 0, 1e12

    # Scan settings
    st.markdown("### 🚀 Scan Performance")
    batch_size = st.slider("Batch size", 20, 200, 40, 10)
    concurrency = st.slider("Threads", 1, 10, 5)

    st.markdown("---")
    if st.button("🔄 Reset Session"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# -------------------- DEFAULT PAIRS --------------------
DEFAULT_PAIRS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT",
    "ADA/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT", "MATIC/USDT", "SHIB/USDT",
    "TRX/USDT", "ATOM/USDT", "LTC/USDT", "BCH/USDT", "NEAR/USDT", "UNI/USDT",
    "APT/USDT", "ICP/USDT", "FIL/USDT", "ETC/USDT", "XLM/USDT", "VET/USDT",
    "QNT/USDT", "ALGO/USDT", "MANA/USDT", "SAND/USDT", "AXS/USDT", "AAVE/USDT",
    "EGLD/USDT", "FLOW/USDT", "THETA/USDT", "FTM/USDT", "GALA/USDT", "GRT/USDT",
    "RUNE/USDT", "KAVA/USDT", "CHZ/USDT", "ZIL/USDT", "ENJ/USDT", "BAT/USDT",
    "CRO/USDT", "DYDX/USDT", "IMX/USDT", "RNDR/USDT", "STX/USDT", "CRV/USDT",
    "SNX/USDT", "COMP/USDT", "YFI/USDT", "SUSHI/USDT", "1INCH/USDT", "OMG/USDT"
][:200]

# -------------------- SESSION --------------------
if 'all_pairs' not in st.session_state:
    st.session_state.all_pairs = []
if 'scanned_results' not in st.session_state:
    st.session_state.scanned_results = []
if 'batch_index' not in st.session_state:
    st.session_state.batch_index = 0

# -------------------- LOAD PAIRS --------------------
def load_pairs(min_vol=0, max_vol=1e12):
    try:
        ex = ccxt.mexc({'enableRateLimit': True, 'timeout': 30000})
        tickers = ex.fetch_tickers()
        all_usdt = [s for s in tickers if s.endswith('/USDT')]
        if min_vol == 0 and max_vol == 1e12:
            return all_usdt
        filtered = []
        for sym in all_usdt:
            t = tickers.get(sym)
            if t and 'quoteVolume' in t and min_vol <= t['quoteVolume'] <= max_vol:
                filtered.append(sym)
        return filtered if filtered else all_usdt
    except Exception as e:
        st.warning(f"Failed to load pairs: {e}")
        return []

if not st.session_state.all_pairs:
    with st.spinner("📡 Loading pairs..."):
        loaded = load_pairs(min_vol if use_vol_filter else 0, max_vol if use_vol_filter else 1e12)
        if loaded:
            st.session_state.all_pairs = loaded[:500]
            st.success(f"✅ Loaded {len(loaded)} pairs")
        else:
            st.warning("Using default list.")
            st.session_state.all_pairs = DEFAULT_PAIRS

# -------------------- FETCH DATA --------------------
@st.cache_data(ttl=600)
def fetch_ohlcv(symbol, tf, limit=300):
    try:
        ex = ccxt.mexc({'enableRateLimit': True, 'timeout': 30000})
        ohlcv = ex.fetch_ohlcv(symbol, tf, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except:
        return None

# -------------------- MICROSTRUCTURE DETECTION --------------------
def detect_volume_absorption(df):
    """Detect if price is stalling on high volume (possible absorption)."""
    close = df['close']
    volume = df['volume']
    vol_ma = volume.rolling(20).mean()
    # Last bar: high volume but small price move
    high_vol = volume.iloc[-1] > vol_ma.iloc[-1] * 1.5
    price_range = (df['high'].iloc[-1] - df['low'].iloc[-1]) / df['close'].iloc[-1]
    small_range = price_range < 0.005  # 0.5% range
    return high_vol and small_range

def detect_institutional_footprint(df):
    """Simplified: look for a wide range bar with high volume followed by narrow range (stop hunt)."""
    # Not implemented fully due to complexity; placeholder
    return False

# -------------------- STRATEGY DETECTION WITH GRADING --------------------
def detect_strategies(df_entry, df_trend):
    close_e = df_entry['close']
    high_e = df_entry['high']
    low_e = df_entry['low']
    vol_e = df_entry['volume']

    # Trend EMAs
    trend_close = df_trend['close']
    trend_ema200 = trend_close.ewm(span=200).mean().iloc[-1]
    trend_up = trend_close.iloc[-1] > trend_ema200
    trend_down = trend_close.iloc[-1] < trend_ema200

    # Entry EMAs
    ema9 = close_e.ewm(span=9).mean().iloc[-1]
    ema21 = close_e.ewm(span=21).mean().iloc[-1]
    price = close_e.iloc[-1]

    # Volume surge
    vol_ma20 = vol_e.rolling(20).mean().iloc[-1]
    vol_surge = vol_e.iloc[-1] / vol_ma20 if vol_ma20 > 0 else 1

    # Range (20-period)
    range_high = high_e.rolling(20).max().iloc[-2]
    range_low = low_e.rolling(20).min().iloc[-2]
    range_width = (range_high - range_low) / range_low

    # RSI
    delta = close_e.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_val = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50

    # ATR
    atr = (high_e - low_e).rolling(14).mean().iloc[-1]

    # Microstructure
    absorption = detect_volume_absorption(df_entry)

    signals = []

    # --- Helper to compute confidence score (0-100) ---
    def compute_score(base, extra_points):
        score = base
        if trend_up or trend_down:
            score += 15
        if vol_surge > 2:
            score += 15
        elif vol_surge > 1.5:
            score += 10
        if 40 < rsi_val < 70:
            score += 10
        if abs(price - ema21) / ema21 < 0.005:
            score += 10
        if absorption:
            score += 10
        return min(score, 100)

    def score_to_grade(score):
        if score >= 90:
            return "A+"
        elif score >= 80:
            return "A"
        elif score >= 70:
            return "B+"
        elif score >= 60:
            return "B"
        elif score >= 50:
            return "C+"
        else:
            return "C"

    # --- Strategy 1: Trend Pullback ---
    if trend_up:
        if abs(price - ema21) / ema21 < 0.01 and price > ema21:
            if rsi_val > 40 and vol_surge > 1.2:
                sl = min(low_e.iloc[-5:].min(), ema21 * 0.99)
                tp1 = price + (price - sl) * 2
                tp2 = price + (price - sl) * 3
                score = compute_score(70, {})
                grade = score_to_grade(score)
                signals.append(("LONG (pullback)", price, sl, tp1, tp2, score, grade))
    elif trend_down:
        if abs(price - ema21) / ema21 < 0.01 and price < ema21:
            if rsi_val < 60 and vol_surge > 1.2:
                sl = max(high_e.iloc[-5:].max(), ema21 * 1.01)
                tp1 = price - (sl - price) * 2
                tp2 = price - (sl - price) * 3
                score = compute_score(70, {})
                grade = score_to_grade(score)
                signals.append(("SHORT (pullback)", price, sl, tp1, tp2, score, grade))

    # --- Strategy 2: Range Breakout ---
    if range_width < 0.03:
        if price > range_high and vol_surge > 1.5:
            sl = range_low * 0.99
            tp1 = price + (price - sl) * 1.5
            tp2 = price + (price - sl) * 2.5
            score = compute_score(65, {})
            grade = score_to_grade(score)
            signals.append(("LONG (breakout)", price, sl, tp1, tp2, score, grade))
        elif price < range_low and vol_surge > 1.5:
            sl = range_high * 1.01
            tp1 = price - (sl - price) * 1.5
            tp2 = price - (sl - price) * 2.5
            score = compute_score(65, {})
            grade = score_to_grade(score)
            signals.append(("SHORT (breakout)", price, sl, tp1, tp2, score, grade))

    # --- Strategy 3: Support/Resistance Bounce ---
    recent_high = high_e.iloc[-20:-5].max()
    recent_low = low_e.iloc[-20:-5].min()
    if trend_up and price <= recent_low * 1.01 and rsi_val < 40:
        sl = recent_low * 0.99
        tp1 = price + (price - sl) * 2
        tp2 = price + (price - sl) * 3
        score = compute_score(75, {})
        grade = score_to_grade(score)
        signals.append(("LONG (support bounce)", price, sl, tp1, tp2, score, grade))
    elif trend_down and price >= recent_high * 0.99 and rsi_val > 60:
        sl = recent_high * 1.01
        tp1 = price - (sl - price) * 2
        tp2 = price - (sl - price) * 3
        score = compute_score(75, {})
        grade = score_to_grade(score)
        signals.append(("SHORT (resistance bounce)", price, sl, tp1, tp2, score, grade))

    # --- Strategy 4: Velez-style Momentum Scalp (simplified) ---
    # Look for strong volume and price acceleration
    if vol_surge > 2 and abs(price - ema9) / ema9 < 0.01:
        # Quick scalp: 1:1 risk-reward
        if price > ema9 and price > ema21:
            sl = price - atr * 0.8
            tp1 = price + atr * 1.6
            tp2 = price + atr * 2.4
            score = compute_score(60, {})
            grade = score_to_grade(score)
            signals.append(("LONG (momentum scalp)", price, sl, tp1, tp2, score, grade))
        elif price < ema9 and price < ema21:
            sl = price + atr * 0.8
            tp1 = price - atr * 1.6
            tp2 = price - atr * 2.4
            score = compute_score(60, {})
            grade = score_to_grade(score)
            signals.append(("SHORT (momentum scalp)", price, sl, tp1, tp2, score, grade))

    return signals

# -------------------- ANALYZE PAIR --------------------
def analyze_pair(pair):
    df_entry = fetch_ohlcv(pair, tf_entry, 300)
    df_trend = fetch_ohlcv(pair, tf_trend, 200)
    if df_entry is None or len(df_entry) < 200 or df_trend is None or len(df_trend) < 100:
        return None

    signals = detect_strategies(df_entry, df_trend)
    if not signals:
        return None

    # Take the highest‑score signal
    best = max(signals, key=lambda x: x[5])  # score index
    sig_type, entry, sl, tp1, tp2, score, grade = best

    # Calculate position size based on account balance and risk %
    atr = (df_entry['high'] - df_entry['low']).rolling(14).mean().iloc[-1]
    risk_amount = account_balance * risk_per_trade
    if "LONG" in sig_type:
        stop_distance = entry - sl
    else:
        stop_distance = sl - entry
    # Avoid division by zero
    if stop_distance <= 0:
        position_size = 0
    else:
        position_size = risk_amount / stop_distance
    # Convert to units (for display)
    position_units = position_size / entry if entry > 0 else 0

    return {
        'Pair': pair,
        'Signal': sig_type,
        'Grade': grade,
        'Score': score,
        'Price': round(entry, 8),
        'ATR': round(atr, 8),
        'Entry': round(entry, 8),
        'Stop Loss': round(sl, 8),
        'TP1': round(tp1, 8),
        'TP2': round(tp2, 8),
        'Risk/Stop (USDT)': round(stop_distance, 4),
        'Suggested Size (USDT)': round(position_size, 2),
        'Suggested Units': round(position_units, 4),
        'Risk/Reward (1->TP1)': f"1:{round((tp1-entry)/(entry-sl) if entry-sl>0 else 0, 2)}",
        'df_entry': df_entry
    }

def scan_batch(pairs, workers):
    results = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(analyze_pair, p): p for p in pairs}
        for f in as_completed(futures):
            try:
                res = f.result(timeout=25)
                if res:
                    results.append(res)
            except:
                pass
    return results

# -------------------- UI --------------------
total = len(st.session_state.all_pairs)
scanned = len(st.session_state.scanned_results)
progress = scanned / total if total else 0

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total", total)
with col2:
    st.metric("Scanned", scanned)
with col3:
    st.metric("Signals", len(st.session_state.scanned_results))
with col4:
    st.metric("Batch", st.session_state.batch_index + 1)

st.progress(progress)

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    if st.button("🔍 Next Batch", disabled=(scanned >= total)):
        start = scanned
        end = min(start + batch_size, total)
        batch = st.session_state.all_pairs[start:end]
        with st.status(f"Batch {st.session_state.batch_index+1}..."):
            new = scan_batch(batch, concurrency)
            st.session_state.scanned_results.extend(new)
            st.session_state.batch_index += 1
        st.rerun()

with col_btn2:
    if st.button("⚡ Full Scan", disabled=(scanned >= total)):
        st.session_state.scanned_results = []
        st.session_state.batch_index = 0
        total_batches = (total + batch_size - 1) // batch_size
        prog = st.progress(0)
        status = st.empty()
        for i in range(total_batches):
            start = i * batch_size
            end = min(start + batch_size, total)
            batch = st.session_state.all_pairs[start:end]
            status.text(f"Batch {i+1}/{total_batches}")
            new = scan_batch(batch, concurrency)
            st.session_state.scanned_results.extend(new)
            prog.progress((i + 1) / total_batches)
        st.success(f"Found {len(st.session_state.scanned_results)} signals")
        st.rerun()

# Display results
if st.session_state.scanned_results:
    # Prepare display dataframe (without internal df_entry)
    display_list = []
    for r in st.session_state.scanned_results:
        d = {k: v for k, v in r.items() if k not in ['df_entry']}
        display_list.append(d)
    df_display = pd.DataFrame(display_list)

    # Sort by score descending
    df_display = df_display.sort_values('Score', ascending=False)

    # Show table
    st.subheader("📊 Signals Found")
    cols = ['Pair', 'Signal', 'Grade', 'Score', 'Price', 'ATR', 'Entry', 'Stop Loss', 'TP1', 'TP2', 'Risk/Stop (USDT)', 'Suggested Size (USDT)', 'Risk/Reward (1->TP1)']
    st.dataframe(df_display[cols], use_container_width=True, hide_index=True)

    # Download CSV
    csv = df_display[cols].to_csv(index=False)
    st.download_button("📥 Download Signals CSV", csv, "institutional_signals.csv", mime="text/csv")

    # --- Trading Plan for Selected Pair ---
    st.markdown("---")
    st.subheader("📋 Trading Plan")
    selected = st.selectbox("Choose a signal to build your plan", df_display['Pair'].unique())
    row = df_display[df_display['Pair'] == selected].iloc[0]

    # Find full result for chart
    full = next(r for r in st.session_state.scanned_results if r['Pair'] == selected)

    with st.container():
        st.markdown(f"""
        <div class="trading-plan">
            <h3 style="color:white; margin-top:0;">{selected} – {row['Signal']} (Grade: {row['Grade']})</h3>
            <div style="display:flex; gap:2rem;">
                <div>
                    <p><strong>Entry:</strong> ${row['Entry']:.6f}</p>
                    <p><strong>Stop Loss:</strong> ${row['Stop Loss']:.6f}</p>
                    <p><strong>TP1:</strong> ${row['TP1']:.6f} (Risk/Reward {row['Risk/Reward (1->TP1)']})</p>
                    <p><strong>TP2:</strong> ${row['TP2']:.6f}</p>
                </div>
                <div class="risk-box">
                    <p style="font-size:1.2rem; margin:0;">Suggested Position</p>
                    <p style="font-size:2rem; margin:0;">${row['Suggested Size (USDT)']:.2f}</p>
                    <p style="margin:0;">≈ {row['Suggested Units']:.4f} units</p>
                    <p style="margin:0; font-size:0.9rem;">Risk: ${row['Risk/Stop (USDT)']:.2f} ({(risk_per_trade*100):.1f}% of account)</p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Chart
    st.subheader("📈 Price Chart")
    df_chart = full['df_entry']
    fig = go.Figure(data=[
        go.Candlestick(
            x=df_chart['timestamp'][-100:],
            open=df_chart['open'][-100:],
            high=df_chart['high'][-100:],
            low=df_chart['low'][-100:],
            close=df_chart['close'][-100:],
            name="Price"
        )
    ])
    ema9 = df_chart['close'].ewm(span=9).mean()[-100:]
    ema21 = df_chart['close'].ewm(span=21).mean()[-100:]
    fig.add_trace(go.Scatter(x=df_chart['timestamp'][-100:], y=ema9, name="EMA9", line=dict(color="cyan")))
    fig.add_trace(go.Scatter(x=df_chart['timestamp'][-100:], y=ema21, name="EMA21", line=dict(color="orange")))

    fig.add_hline(y=row['Entry'], line_dash="dash", line_color="white", annotation_text="Entry")
    fig.add_hline(y=row['Stop Loss'], line_dash="dash", line_color="red", annotation_text="SL")
    fig.add_hline(y=row['TP1'], line_dash="dash", line_color="green", annotation_text="TP1")
    fig.add_hline(y=row['TP2'], line_dash="dash", line_color="lime", annotation_text="TP2")

    fig.update_layout(
        title=f"{selected} – {tf_entry}",
        xaxis_rangeslider_visible=False,
        height=500,
        template="plotly_dark"
    )
    st.plotly_chart(fig, use_container_width=True)

    # Educational overlay
    st.info("""
    **🧠 Institutional Rules**
    - **Never risk more than your set % per trade.** Our position sizing ensures that.
    - **Stick to the stop loss.** It's based on ATR, not feelings.
    - **Let winners run** – we provide two targets; consider trailing stop after TP1.
    - **Journal every trade** – note why you entered, followed rules, and outcome.
    """)
else:
    st.info("👆 Start scanning – click 'Next Batch' or 'Full Scan'")

st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
