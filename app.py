import streamlit as st
import requests
import time
import pandas as pd
from datetime import datetime, timezone  # Added timezone

# CSV file for persistent history
HISTORY_FILE = "solana_history.csv"

# Session state for in-memory history
if 'history' not in st.session_state:
    st.session_state.history = []
if 'update_count' not in st.session_state:
    st.session_state.update_count = 0

# Load existing history from CSV if exists
def load_history():
    if os.path.exists(HISTORY_FILE):
        df = pd.read_csv(HISTORY_FILE)
        st.session_state.history = df.to_dict('records')
    else:
        st.session_state.history = []

# Save history to CSV
def save_history(new_entry):
    st.session_state.history.append(new_entry)
    df = pd.DataFrame(st.session_state.history)
    df.to_csv(HISTORY_FILE, index=False)

# Function to fetch data from APIs
def fetch_oi_data():
    data = {}
    price = 0.0
    timestamp = datetime.now(timezone.UTC).strftime("%Y-%m-%d %H:%M")  # Updated
    
    # Fetch price from Binance
    try:
        price_resp = requests.get("https://fapi.binance.com/fapi/v1/ticker/price?symbol=SOLUSDT", timeout=10).json()
        price = float(price_resp['price'])
        data['Price'] = price
    except:
        data['Price'] = "Error"

    # Binance OI (in SOL units)
    try:
        binance_resp = requests.get("https://fapi.binance.com/fapi/v1/openInterest?symbol=SOLUSDT", timeout=10).json()
        binance_sol = float(binance_resp['openInterest'])
        binance_usd = binance_sol * price
        data['Binance'] = {'USD': f"${binance_usd:,.2f}", 'SOL': f"{binance_sol:,.0f}"}
    except:
        data['Binance'] = {'USD': "Error", 'SOL': "Error"}

    # Bybit OI (in USD for linear)
    try:
        bybit_resp = requests.get("https://api.bybit.com/v5/market/open-interest?category=linear&symbol=SOLUSDT&intervalTime=5min&limit=1", timeout=10).json()
        bybit_usd = float(bybit_resp['result']['list'][0]['openInterest'])
        bybit_sol = bybit_usd / price if price else 0
        data['Bybit'] = {'USD': f"${bybit_usd:,.2f}", 'SOL': f"{bybit_sol:,.0f}"}
    except:
        data['Bybit'] = {'USD': "Error", 'SOL': "Error"}

    # OKX OI (oiCcy in SOL)
    try:
        okx_resp = requests.get("https://www.okx.com/api/v5/public/open-interest?instType=SWAP&uly=SOL-USDT", timeout=10).json()
        okx_sol = float(okx_resp['data'][0]['oiCcy'])
        okx_usd = okx_sol * price
        data['OKX'] = {'USD': f"${okx_usd:,.2f}", 'SOL': f"{okx_sol:,.0f}"}
    except:
        data['OKX'] = {'USD': "Error", 'SOL': "Error"}

    # Binance Funding Rate (latest)
    try:
        fund_resp = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=SOLUSDT", timeout=10).json()
        funding_rate = float(fund_resp['lastFundingRate']) * 100  # As %
        data['Funding Rate (%)'] = f"{funding_rate:.4f}"
    except:
        data['Funding Rate (%)'] = "Error"

    # Binance Long/Short Ratio (5m)
    try:
        ls_resp = requests.get("https://fapi.binance.com/fapi/v1/globalLongShortAccountRatio?symbol=SOLUSDT&period=5m", timeout=10).json()
        ls_ratio = float(ls_resp[0]['longShortRatio'])  # Take latest
        data['Long/Short Ratio'] = f"{ls_ratio:.2f}"
    except:
        data['Long/Short Ratio'] = "Error"

    # Partial total
    try:
        total_usd = sum(float(d['USD'][1:].replace(',', '')) for d in [data['Binance'], data['Bybit'], data['OKX']] if d['USD'] != "Error")
        total_sol = sum(float(d['SOL'].replace(',', '')) for d in [data['Binance'], data['Bybit'], data['OKX']] if d['SOL'] != "Error")
        data['Partial Total'] = {'USD': f"${total_usd:,.2f}", 'SOL': f"{total_sol:,.0f}"}
        data['Partial Total USD Raw'] = total_usd  # For calculations
    except:
        data['Partial Total'] = {'USD': "Error", 'SOL': "Error"}
        data['Partial Total USD Raw'] = 0

    data['Timestamp'] = timestamp
    return data, price

# Function to calculate health score
def calculate_health(data):
    score = 0
    oi_usd = data['Partial Total USD Raw']
    
    # For trend, compare to previous if available
    if st.session_state.history:
        prev_oi_usd = st.session_state.history[-1].get('Partial Total USD Raw', 0)
        if prev_oi_usd > 0:
            change_pct = (oi_usd - prev_oi_usd) / prev_oi_usd * 100
            if change_pct > 5: score += 30
            elif change_pct > -5: score += 10
    
    # Funding Rate (+30 max)
    try:
        funding = float(data['Funding Rate (%)'])
        if funding > 0.01: score += 30
        elif funding > -0.01: score += 15
    except:
        pass
    
    # Long/Short Ratio (+40 max)
    try:
        ls = float(data['Long/Short Ratio'])
        if ls > 1.1: score += 40
        elif ls > 0.9: score += 20
    except:
        pass
    
    return min(score, 100)

# Function for time analysis
def analyze_history(history_df):
    if history_df.empty:
        return "No history yet—wait for updates."
    
    avg_health = history_df['Health Score'].mean()
    oi_trend = "up" if history_df['Partial Total USD Raw'].iloc[-1] > history_df['Partial Total USD Raw'].iloc[0] else "down"
    insights = [
        f"Average Health Score: {avg_health:.1f}/100 ({'Healthy' if avg_health >= 70 else 'Neutral' if avg_health >= 40 else 'Concerning'})",
        f"OI Trend: {oi_trend.capitalize()} over {len(history_df)} updates",
        f"Max OI: ${history_df['Partial Total USD Raw'].max():,.2f}",
        f"Min Funding Rate: {history_df['Funding Rate (%)'].min():.4f}%",
        f"Average LS Ratio: {history_df['Long/Short Ratio'].mean():.2f}"
    ]
    return "\n".join(insights)

# Load history on start
load_history()

# Streamlit app
st.title("🧠 Solana Futures OI & Health Tracker (with History)")
st.write("Live dashboard + historical analysis. Updates every 60s. Data logged to solana_history.csv.")

tab1, tab2 = st.tabs(["Live Data", "History & Analysis"])

with tab1:
    placeholder = st.empty()
    health_placeholder = st.empty()

while True:
    data, price = fetch_oi_data()
    st.session_state.update_count += 1
    
    # Calculate health
    health_score = calculate_health(data)
    data['Health Score'] = health_score
    
    # Save to history
    new_entry = {
        'Timestamp': data['Timestamp'],
        'Partial Total USD': data['Partial Total']['USD'],
        'Partial Total USD Raw': data['Partial Total USD Raw'],
        'Funding Rate (%)': float(data['Funding Rate (%)']) if data['Funding Rate (%)'] != "Error" else 0,
        'Long/Short Ratio': float(data['Long/Short Ratio']) if data['Long/Short Ratio'] != "Error" else 1.0,
        'Health Score': health_score,
        'Price': price
    }
    save_history(new_entry)
    
    # Health Display
    color = "🟢" if health_score >= 70 else "🟡" if health_score >= 40 else "🔴"
    status = "Healthy" if health_score >= 70 else "Neutral" if health_score >= 40 else "Concerning"
    with health_placeholder.container():
        st.metric("Current Health Score", f"{health_score}/100", delta=None)
        st.write(f"**Status**: {color} {status}")
        st.write(f"**Update #{st.session_state.update_count}** at {data['Timestamp']} UTC | Price: ${price:.2f}" if price else "N/A")
    
    # Live Table
    exchanges = ["Binance", "Bybit", "OKX", "Partial Total"]
    df_data = {
        "Exchange": exchanges,
        "OI in USD": [data.get(ex, {}).get('USD', 'N/A') for ex in exchanges],
        "OI in SOL": [data.get(ex, {}).get('SOL', 'N/A') for ex in exchanges],
        "Current Price": [f"${price:.2f}" if price else "N/A"] * 4
    }
    df_live = pd.DataFrame(df_data)
    
    with placeholder.container():
        st.dataframe(df_live)
    
    # Additional Metrics
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Funding Rate")
        st.write(data.get('Funding Rate (%)', 'N/A'))
    with col2:
        st.subheader("Long/Short Ratio")
        st.write(data.get('Long/Short Ratio', 'N/A'))
    
    # History Tab
    with tab2:
        history_df = pd.DataFrame(st.session_state.history)
        if not history_df.empty:
            st.subheader("Historical Data")
            st.dataframe(history_df[['Timestamp', 'Partial Total USD', 'Funding Rate (%)', 'Long/Short Ratio', 'Health Score', 'Price']])
            
            st.subheader("Time Analysis Insights")
            st.text(analyze_history(history_df))
            
            st.subheader("Charts Over Time")
            st.line_chart(history_df.set_index('Timestamp')['Partial Total USD Raw'], y_label="Partial OI (USD)")
            st.line_chart(history_df.set_index('Timestamp')['Health Score'], y_label="Health Score")
            st.line_chart(history_df.set_index('Timestamp')['Funding Rate (%)'], y_label="Funding Rate (%)")
            st.line_chart(history_df.set_index('Timestamp')['Long/Short Ratio'], y_label="LS Ratio")
        else:
            st.write("No history yet—wait for a few updates.")
    
    # Wait 60 seconds and rerun
    time.sleep(60)
    st.rerun()
