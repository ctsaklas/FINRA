import streamlit as st
import pandas as pd
import requests
from io import StringIO
from datetime import datetime, timedelta

# App Configuration
st.set_page_config(page_title="FINRA Dark Pool Analyzer", layout="wide")
st.title("📊 FINRA Dark Pool Buying & Selling Activity")
st.markdown("This app calculates institutional buying (Short Volume) vs. natural selling (Long Volume).")

# Sidebar for Inputs
st.sidebar.header("Settings")
today = datetime.now()
default_start = today - timedelta(days=15)

# Date range selector
date_range = st.sidebar.date_input(
    "Select Date Range",
    value=(default_start, today),
    max_value=today
)

def fetch_finra_data(date_str):
    """Fetches and parses the FINRA text file for a given date string."""
    url = f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date_str}.txt"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(StringIO(response.text), sep='|')
            # Remove the footer row (usually contains the date)
            df = df.dropna(subset=['Symbol'])
            return df
    except Exception:
        return None
    return None

if len(date_range) == 2:
    start_date, end_date = date_range
    
    if st.sidebar.button("Run Analysis"):
        all_dfs = []
        current_date = start_date
        
        progress_bar = st.progress(0)
        days_total = (end_date - start_date).days + 1
        
        # Data Processing Loop
        for i in range(days_total):
            # Skip weekends (Saturday=5, Sunday=6)
            if current_date.weekday() < 5:
                date_str = current_date.strftime("%Y%m%d")
                df = fetch_finra_data(date_str)
                if df is not None:
                    all_dfs.append(df)
            
            current_date += timedelta(days=1)
            progress_bar.progress((i + 1) / days_total)

        if all_dfs:
            combined_df = pd.concat(all_dfs)
            
            # Aggregate Data
            agg = combined_df.groupby('Symbol').agg({
                'ShortVolume': 'sum',
                'TotalVolume': 'sum'
            }).reset_index()

            # Calculate Buying and Selling Volume
            # Buying = Short Volume (MM fulfilling buy orders)
            # Selling = Total Volume - Short Volume (Natural selling)
            agg['BuyingVolume'] = agg['ShortVolume']
            agg['SellingVolume'] = agg['TotalVolume'] - agg['ShortVolume']
            
            # UI Layout
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("🔥 Top 15 Buying Volume")
                top_buy = agg.sort_values(by='BuyingVolume', ascending=False).head(15)
                st.table(top_buy[['Symbol', 'BuyingVolume']])

            with col2:
                st.subheader("📉 Top 15 Selling Volume")
                top_sell = agg.sort_values(by='SellingVolume', ascending=False).head(15)
                st.table(top_sell[['Symbol', 'SellingVolume']])
                
            st.success(f"Analysis complete for {len(all_dfs)} trading days.")
        else:
            st.error("No data found for the selected range. Markets may have been closed.")
else:
    st.info("Please select a start and end date in the sidebar.")