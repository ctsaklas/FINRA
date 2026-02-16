import streamlit as st
import pandas as pd
import requests
from io import StringIO
from datetime import datetime, timedelta

# App Configuration
st.set_page_config(page_title="Institutional Flow Analyzer", layout="wide")

st.title("📊 Institutional Flow: Buy vs. Sell Analysis")
st.markdown("""
**Methodology:**
* **Buying Activity (Buy Vol):** Short Volume (Market makers filling immediate buy orders).
* **Selling Activity (Sell Vol):** Total Volume minus Short Volume (Natural long sellers).
* **Consolidated Threshold:** Only symbols where Buy or Sell volume is >60% of the total range volume are displayed.
""")

# --- SIDEBAR PARAMETERS ---
st.sidebar.header("Parameters")
st.sidebar.info("📡 **Data Source:** FINRA Aggregated (All TRFs)")

today = datetime.now()
default_start = today - timedelta(days=15)
date_range = st.sidebar.date_input("Select Date Range", value=(default_start, today), max_value=today)

vol_threshold = st.sidebar.number_input(
    "Minimum Total Volume Filter", 
    min_value=0, 
    value=1000000, 
    step=100000,
    help="Excludes symbols with total consolidated volume below this number."
)

@st.cache_data(ttl=3600)
def fetch_finra_data(date_str):
    url = f"https://cdn.finra.org/equity/regsho/daily/FNYRAshvol{date_str}.txt"
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if response.status_code == 200:
            content = response.text
            # Try reading with default headers first
            try:
                df = pd.read_csv(StringIO(content), sep='|')
                # If 'Symbol' is missing, it means the file lacks headers -> Reload with names
                if 'Symbol' not in df.columns:
                     df = pd.read_csv(StringIO(content), sep='|', names=['Date', 'Symbol', 'ShortVolume', 'ShortExemptVolume', 'TotalVolume', 'Market'])
            except:
                # Fallback: Assume no header
                df = pd.read_csv(StringIO(content), sep='|', names=['Date', 'Symbol', 'ShortVolume', 'ShortExemptVolume', 'TotalVolume', 'Market'])

            df = df.dropna(subset=['Symbol'])
            df['ShortVolume'] = pd.to_numeric(df['ShortVolume'], errors='coerce').fillna(0)
            df['TotalVolume'] = pd.to_numeric(df['TotalVolume'], errors='coerce').fillna(0)
            return df[['Symbol', 'ShortVolume', 'TotalVolume']]
    except: return None
    return None

# --- MAIN EXECUTION ---
if len(date_range) == 2:
    start_date, end_date = date_range
    
    if st.sidebar.button("Execute Analysis"):
        all_dfs = []
        current_date = start_date
        days_diff = (end_date - start_date).days + 1
        progress_bar = st.progress(0)
        
        for i in range(days_diff):
            if current_date.weekday() < 5:
                date_str = current_date.strftime("%Y%m%d")
                df = fetch_finra_data(date_str)
                if df is not None and not df.empty:
                    all_dfs.append(df)
            current_date += timedelta(days=1)
            progress_bar.progress((i + 1) / days_diff)
        
        if all_dfs:
            full_data = pd.concat(all_dfs)
            
            # Aggregate logic
            agg = full_data.groupby('Symbol').agg({'ShortVolume':'sum', 'TotalVolume':'sum'}).reset_index()
            # Apply Volume Filter
            agg = agg[agg['TotalVolume'] >= vol_threshold]
            
            # Logic: Buy (Short) vs Sell (Total - Short)
            agg['Buy Vol'] = agg['ShortVolume']
            agg['Sell Vol'] = agg['TotalVolume'] - agg['ShortVolume']
            agg['Buy/Sell Ratio'] = (agg['Buy Vol'] / agg['Sell Vol'].replace(0, 0.0001)).replace([float('inf')], 100.0).fillna(0)
            agg['BuyPct'] = agg['Buy Vol'] / agg['TotalVolume']
            agg['SellPct'] = agg['Sell Vol'] / agg['TotalVolume']

            # --- TABLES PANEL ---
            col1, col2 = st.columns(2)
            display_cols = ['Symbol', 'TotalVolume', 'Buy Vol', 'Sell Vol', 'Buy/Sell Ratio']
            
            with col1:
                st.subheader("🔥 Top 15 Buying Volume (>60%)")
                buy_list = agg[agg['BuyPct'] > 0.60].sort_values('Buy Vol', ascending=False).head(15)
                if not buy_list.empty:
                    st.dataframe(buy_list[display_cols].style.format({'Buy/Sell Ratio': '{:.2f}', 'TotalVolume': '{:,.0f}', 'Buy Vol': '{:,.0f}', 'Sell Vol': '{:,.0f}'}))
                else:
                    st.info("No stocks found with >60% consolidated Buying pressure.")
                
            with col2:
                st.subheader("📉 Top 15 Selling Volume (>60%)")
                sell_list = agg[agg['SellPct'] > 0.60].sort_values('Sell Vol', ascending=False).head(15)
                if not sell_list.empty:
                    st.dataframe(sell_list[display_cols].style.format({'Buy/Sell Ratio': '{:.2f}', 'TotalVolume': '{:,.0f}', 'Buy Vol': '{:,.0f}', 'Sell Vol': '{:,.0f}'}))
                else:
                    st.info("No stocks found with >60% consolidated Selling pressure.")
        else:
            st.error("No data retrieved. Verify the dates are valid trading days.")
else:
    st.info("Select a start and end date to begin.")