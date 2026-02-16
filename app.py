import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from io import StringIO
from datetime import datetime, timedelta

# App Configuration
st.set_page_config(page_title="Dark Pool Flow Analyzer", layout="wide")
st.title("📊 Dark Pool Institutional Flow Analyzer")

# --- Dark Pool Explanation & Methodology ---
st.markdown("""
**What are Dark Pools?**
Dark pools are private exchanges where institutional investors (banks, hedge funds) trade large blocks of shares anonymously. Unlike public "lit" exchanges (like the NYSE floor), trades here are not revealed to the market until *after* execution. This allows big players to enter or exit positions without immediately moving the stock price against themselves.

**Methodology:**
* **Total Dark Volume:** Reconstructed by summing **CNMS** (ADF), **NYSE TRF**, **Nasdaq Carteret**, and **Nasdaq Chicago**.
* **Buying Activity:** Short Volume (Market makers filling buy orders).
* **Selling Activity:** Total Volume - Short Volume (Natural long sellers).
""")

# --- SIDEBAR SETTINGS ---
st.sidebar.header("Parameters")
today = datetime.now()
default_start = today - timedelta(days=15)
date_range = st.sidebar.date_input("Select Date Range", value=(default_start, today), max_value=today)

vol_threshold = st.sidebar.number_input("Min Total Volume Filter", min_value=0, value=1000000, step=100000)

@st.cache_data(ttl=3600)
def fetch_daily_components(date_str):
    """
    Fetches and combines data from ALL 4 FINRA facilities to reconstruct total volume.
    """
    base_url = "https://cdn.finra.org/equity/regsho/daily/"
    
    # The 4 "Pipes" of Dark Pool Data
    components = [
        f"CNMSshvol{date_str}.txt",   # ADF / Consolidated NMS
        f"FNYXshvol{date_str}.txt",   # NYSE TRF
        f"FNSQshvol{date_str}.txt",   # Nasdaq TRF Carteret
        f"FNQChshvol{date_str}.txt"   # Nasdaq TRF Chicago
    ]
    
    daily_frames = []
    
    for filename in components:
        url = base_url + filename
        try:
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            if response.status_code == 200:
                # Parse file
                df = pd.read_csv(StringIO(response.text), sep='|')
                
                # Handle missing headers if any (fallback)
                if 'Symbol' not in df.columns:
                     df = pd.read_csv(StringIO(response.text), sep='|', names=['Date', 'Symbol', 'ShortVolume', 'ShortExemptVolume', 'TotalVolume', 'Market'])
                
                df = df.dropna(subset=['Symbol'])
                
                # Normalize columns
                df['ShortVolume'] = pd.to_numeric(df['ShortVolume'], errors='coerce').fillna(0)
                df['TotalVolume'] = pd.to_numeric(df['TotalVolume'], errors='coerce').fillna(0)
                
                # Keep only relevant columns for aggregation
                daily_frames.append(df[['Symbol', 'ShortVolume', 'TotalVolume']])
        except:
            continue # If one facility fails (e.g. Chicago is empty), skip it and keep others
            
    if daily_frames:
        # Concatenate all facilities (NYSE + Nasdaq + CNMS)
        combined = pd.concat(daily_frames)
        # Sum them up by Symbol to get the TRUE daily total
        daily_total = combined.groupby('Symbol').agg({'ShortVolume':'sum', 'TotalVolume':'sum'}).reset_index()
        
        # Add Date column back for the chart
        daily_total['Date'] = pd.to_datetime(date_str, format='%Y%m%d').strftime('%Y-%m-%d')
        return daily_total
    
    return None

if len(date_range) == 2:
    start_date, end_date = date_range
    if st.sidebar.button("Run Analysis"):
        all_daily_totals = []
        current_date = start_date
        
        # Progress Bar setup
        days_diff = (end_date - start_date).days + 1
        progress_bar = st.progress(0)
        day_count = 0

        while current_date <= end_date:
            if current_date.weekday() < 5:
                date_str = current_date.strftime("%Y%m%d")
                # Fetch the combined "Super Frame" for this day
                df = fetch_daily_components(date_str)
                if df is not None: 
                    all_daily_totals.append(df)
            
            current_date += timedelta(days=1)
            day_count += 1
            progress_bar.progress(min(day_count / days_diff, 1.0))
        
        if all_daily_totals:
            full_data = pd.concat(all_daily_totals)
            st.session_state['full_data'] = full_data
            
            # Aggregate for the Summary Table (Summing up the daily totals)
            agg = full_data.groupby('Symbol').agg({'ShortVolume':'sum', 'TotalVolume':'sum'}).reset_index()
            # Note: We keep the raw 'agg' for ETF filtering before applying the threshold
            
            # Apply Volume Filter for Top 15 lists
            filtered_agg = agg[agg['TotalVolume'] >= vol_threshold].copy()
            filtered_agg['Buy Vol'] = filtered_agg['ShortVolume']
            filtered_agg['Sell Vol'] = filtered_agg['TotalVolume'] - filtered_agg['ShortVolume']
            filtered_agg['Buy/Sell Ratio'] = (filtered_agg['Buy Vol'] / filtered_agg['Sell Vol'].replace(0, 0.0001)).replace([float('inf')], 100.0).fillna(0)
            filtered_agg['BuyPct'] = filtered_agg['Buy Vol'] / filtered_agg['TotalVolume']
            filtered_agg['SellPct'] = filtered_agg['Sell Vol'] / filtered_agg['TotalVolume']
            
            st.session_state['agg_data'] = filtered_agg
            
            # Calculate metrics for the FULL dataset (for ETFs that might be below threshold)
            agg['Buy Vol'] = agg['ShortVolume']
            agg['Sell Vol'] = agg['TotalVolume'] - agg['ShortVolume']
            agg['Buy/Sell Ratio'] = (agg['Buy Vol'] / agg['Sell Vol'].replace(0, 0.0001)).replace([float('inf')], 100.0).fillna(0)
            st.session_state['raw_agg'] = agg

    if 'agg_data' in st.session_state:
        agg = st.session_state['agg_data']
        raw_agg = st.session_state.get('raw_agg', agg)
        full_data = st.session_state['full_data']

        # --- SECTION 1: TOP 15 BUY/SELL ---
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🔥 Top Buying (>60%)")
            buy_list = agg[agg['BuyPct'] > 0.60].sort_values('Buy Vol', ascending=False).head(15)
            st.data_editor(buy_list[['Symbol', 'TotalVolume', 'Buy Vol', 'Sell Vol', 'Buy/Sell Ratio']], 
                                     hide_index=True, key="buy_table")
        with col2:
            st.subheader("📉 Top Selling (>60%)")
            sell_list = agg[agg['SellPct'] > 0.60].sort_values('Sell Vol', ascending=False).head(15)
            st.data_editor(sell_list[['Symbol', 'TotalVolume', 'Buy Vol', 'Sell Vol', 'Buy/Sell Ratio']], 
                                      hide_index=True, key="sell_table")

        # --- SECTION 2: ETF TRACKER (NEW) ---
        st.divider()
        st.header("⚡ Leveraged & Inverse ETF Tracker")
        
        # ETF Watchlists
        lev_symbols = ['SSO', 'QLD', 'UPRO', 'TQQQ']
        inv_symbols = ['DOG', 'PSQ', 'SH', 'SDS', 'QID', 'SQQQ', 'SVIX']
        
        # Filter from RAW data (ignoring volume threshold to ensure they appear)
        lev_data = raw_agg[raw_agg['Symbol'].isin(lev_symbols)].sort_values('Buy/Sell Ratio', ascending=False)
        inv_data = raw_agg[raw_agg['Symbol'].isin(inv_symbols)].sort_values('Buy/Sell Ratio', ascending=False)
        
        col_etf1, col_etf2 = st.columns(2)
        
        with col_etf1:
            st.subheader("🚀 Leveraged Long ETFs")
            if not lev_data.empty:
                st.data_editor(lev_data[['Symbol', 'TotalVolume', 'Buy Vol', 'Sell Vol', 'Buy/Sell Ratio']], 
                             hide_index=True, key="lev_table")
            else:
                st.info("No data found for Leveraged ETFs in this range.")

        with col_etf2:
            st.subheader("🐻 Inverse/Short ETFs")
            if not inv_data.empty:
                st.data_editor(inv_data[['Symbol', 'TotalVolume', 'Buy Vol', 'Sell Vol', 'Buy/Sell Ratio']], 
                             hide_index=True, key="inv_table")
            else:
                st.info("No data found for Inverse ETFs in this range.")

        # --- SECTION 3: DETAILED CHARTING ---
        st.divider()
        # Symbol Selection for Charting
        selected_symbol = st.selectbox("Select a Symbol to Chart Details:", options=sorted(agg['Symbol'].unique()))

        if selected_symbol:
            symbol_data = full_data[full_data['Symbol'] == selected_symbol].copy().sort_values('Date')
            symbol_data['Buy'] = symbol_data['ShortVolume']
            symbol_data['Sell'] = symbol_data['TotalVolume'] - symbol_data['ShortVolume']
            symbol_data['Ratio'] = (symbol_data['ShortVolume'] / symbol_data['Sell'].replace(0, 0.0001)).replace([float('inf')], 100.0)

            # --- PLOTLY: BAR CHART + TREND ---
            st.subheader(f"Detailed Analysis: {selected_symbol}")
            
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # Buying (Green)
            fig.add_trace(go.Bar(x=symbol_data['Date'], y=symbol_data['Buy'], name="Buying", marker_color='green'))
            # Selling (Red) - Side-by-Side
            fig.add_trace(go.Bar(x=symbol_data['Date'], y=symbol_data['Sell'], name="Selling", marker_color='red'))
            
            # Ratio Trend (Orange Line)
            fig.add_trace(go.Scatter(x=symbol_data['Date'], y=symbol_data['Ratio'], name="Buy/Sell Trend", line=dict(color='orange', width=3)), secondary_y=True)
            
            fig.update_layout(title="Daily Buy/Sell Volume with Ratio Trend", barmode='group', height=500, hovermode="x unified")
            fig.update_xaxes(type='category')
            fig.update_yaxes(title_text="Volume", secondary_y=False)
            fig.update_yaxes(title_text="Buy/Sell Ratio", secondary_y=True)
            
            st.plotly_chart(fig, use_container_width=True)