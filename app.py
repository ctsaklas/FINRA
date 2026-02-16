import streamlit as st
import pandas as pd
import requests
from io import StringIO
from datetime import datetime, timedelta

# App Configuration
st.set_page_config(page_title="Institutional Buy/Sell Analyzer", layout="wide")

st.title("📊 Dark Pool Institutional Flow Analyzer")
st.markdown("""
**Methodology:**
* **Buying Activity (Buy Vol):** Short Volume (Market makers filling immediate buy orders).
* **Selling Activity (Sell Vol):** Total Volume minus Short Volume (Natural long sellers).
* **Consolidated Threshold:** Only symbols where Buy or Sell volume is >60% of the total range volume are displayed.
""")

# --- SIDEBAR SETTINGS ---
st.sidebar.header("Parameters")

# Date range selector
today = datetime.now()
default_start = today - timedelta(days=15)
date_range = st.sidebar.date_input(
    "Select Date Range",
    value=(default_start, today),
    max_value=today
)

# Dynamic Volume Filter
vol_threshold = st.sidebar.number_input(
    "Minimum Total Volume Filter", 
    min_value=0, 
    value=1000000, 
    step=100000,
    help="Excludes symbols with total consolidated volume below this number."
)

@st.cache_data(ttl=3600)
def fetch_finra_data(date_str):
    """Fetches and processes FINRA text files with error handling."""
    url = f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date_str}.txt"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(StringIO(response.text), sep='|')
            df = df.dropna(subset=['Symbol'])
            # Ensure core columns are numeric
            df['ShortVolume'] = pd.to_numeric(df['ShortVolume'], errors='coerce').fillna(0)
            df['TotalVolume'] = pd.to_numeric(df['TotalVolume'], errors='coerce').fillna(0)
            return df[['Symbol', 'ShortVolume', 'TotalVolume']]
    except:
        return None
    return None

# --- MAIN EXECUTION ---
if len(date_range) == 2:
    start_date, end_date = date_range
    
    if st.sidebar.button("Run Analysis"):
        all_dfs = []
        current_date = start_date
        days_diff = (end_date - start_date).days + 1
        
        status_text = st.empty()
        progress_bar = st.progress(0)
        
        for i in range(days_diff):
            # Process only weekdays
            if current_date.weekday() < 5:
                date_str = current_date.strftime("%Y%m%d")
                status_text.text(f"Fetching data for {date_str}...")
                df = fetch_finra_data(date_str)
                if df is not None:
                    all_dfs.append(df)
            
            current_date += timedelta(days=1)
            progress_bar.progress((i + 1) / days_diff)

        if all_dfs:
            # Consolidate Data
            combined = pd.concat(all_dfs)
            final_df = combined.groupby('Symbol').agg({
                'ShortVolume': 'sum',
                'TotalVolume': 'sum'
            }).reset_index()

            # Apply Volume Filter
            final_df = final_df[final_df['TotalVolume'] >= vol_threshold]

            # Calculate Buying and Selling
            final_df['Buy Vol'] = final_df['ShortVolume']
            final_df['Sell Vol'] = final_df['TotalVolume'] - final_df['ShortVolume']
            
            # Calculate Buy/Sell Ratio (Handle Div by Zero with 100.0)
            final_df['Buy/Sell Ratio'] = (final_df['Buy Vol'] / final_df['Sell Vol']).replace([float('inf')], 100.0).fillna(0)
            
            # Percentages for Filtering
            final_df['BuyPct'] = final_df['Buy Vol'] / final_df['TotalVolume']
            final_df['SellPct'] = final_df['Sell Vol'] / final_df['TotalVolume']

            # Separate Panels
            col1, col2 = st.columns(2)

            with col1:
                st.header("🔥 High Buying Pressure")
                st.caption("Consolidated Buying > 60% of Total Volume")
                buy_df = final_df[final_df['BuyPct'] > 0.60].sort_values(by='Buy Vol', ascending=False).head(15)
                
                display_cols = ['Symbol', 'TotalVolume', 'Buy Vol', 'Sell Vol', 'Buy/Sell Ratio']
                if not buy_df.empty:
                    st.dataframe(buy_df[display_cols].style.format({'Buy/Sell Ratio': '{:.2f}', 'TotalVolume': '{:,.0f}', 'Buy Vol': '{:,.0f}', 'Sell Vol': '{:,.0f}'}))
                else:
                    st.warning("No symbols met the >60% Buy threshold.")

            with col2:
                st.header("📉 High Selling Pressure")
                st.caption("Consolidated Selling > 60% of Total Volume")
                sell_df = final_df[final_df['SellPct'] > 0.60].sort_values(by='Sell Vol', ascending=False).head(15)
                
                if not sell_df.empty:
                    st.dataframe(sell_df[display_cols].style.format({'Buy/Sell Ratio': '{:.2f}', 'TotalVolume': '{:,.0f}', 'Buy Vol': '{:,.0f}', 'Sell Vol': '{:,.0f}'}))
                else:
                    st.warning("No symbols met the >60% Sell threshold.")

            status_text.text("Analysis Complete.")
            st.success(f"Aggregated data across {len(all_dfs)} trading days.")
        else:
            st.error("Could not retrieve data. Ensure the dates selected are valid market trading days.")
else:
    st.info("Please select both a start and end date in the sidebar.")