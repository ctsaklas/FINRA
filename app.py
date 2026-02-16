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

# --- SIDEBAR SETTINGS ---
st.sidebar.header("Parameters")
today = datetime.now()
default_start = today - timedelta(days=15)
date_range = st.sidebar.date_input("Select Date Range", value=(default_start, today), max_value=today)

vol_threshold = st.sidebar.number_input("Min Total Volume Filter", min_value=0, value=1000000, step=100000)

@st.cache_data(ttl=3600)
def fetch_finra_data(date_str):
    url = f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date_str}.txt"
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(StringIO(response.text), sep='|')
            df = df.dropna(subset=['Symbol'])
            df['ShortVolume'] = pd.to_numeric(df['ShortVolume'], errors='coerce').fillna(0)
            df['TotalVolume'] = pd.to_numeric(df['TotalVolume'], errors='coerce').fillna(0)
            df['Date'] = date_str
            return df[['Date', 'Symbol', 'ShortVolume', 'TotalVolume']]
    except: return None
    return None

if len(date_range) == 2:
    start_date, end_date = date_range
    if st.sidebar.button("Run Analysis"):
        all_dfs = []
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() < 5:
                df = fetch_finra_data(current_date.strftime("%Y%m%d"))
                if df is not None: all_dfs.append(df)
            current_date += timedelta(days=1)
        
        if all_dfs:
            full_data = pd.concat(all_dfs)
            st.session_state['full_data'] = full_data
            
            # Aggregate for Table
            agg = full_data.groupby('Symbol').agg({'ShortVolume':'sum', 'TotalVolume':'sum'}).reset_index()
            agg = agg[agg['TotalVolume'] >= vol_threshold]
            agg['Buy Vol'] = agg['ShortVolume']
            agg['Sell Vol'] = agg['TotalVolume'] - agg['ShortVolume']
            agg['Buy/Sell Ratio'] = (agg['Buy Vol'] / agg['Sell Vol']).replace([float('inf')], 100.0).fillna(0)
            agg['BuyPct'] = agg['Buy Vol'] / agg['TotalVolume']
            agg['SellPct'] = agg['Sell Vol'] / agg['TotalVolume']
            
            st.session_state['agg_data'] = agg

    if 'agg_data' in st.session_state:
        agg = st.session_state['agg_data']
        full_data = st.session_state['full_data']

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🔥 Top Buying (>60%)")
            buy_list = agg[agg['BuyPct'] > 0.60].sort_values('Buy Vol', ascending=False).head(15)
            # Using Data Editor for selection
            buy_edit = st.data_editor(buy_list[['Symbol', 'TotalVolume', 'Buy Vol', 'Sell Vol', 'Buy/Sell Ratio']], 
                                     hide_index=True, key="buy_table", on_change=None)
        with col2:
            st.subheader("📉 Top Selling (>60%)")
            sell_list = agg[agg['SellPct'] > 0.60].sort_values('Sell Vol', ascending=False).head(15)
            sell_edit = st.data_editor(sell_list[['Symbol', 'TotalVolume', 'Buy Vol', 'Sell Vol', 'Buy/Sell Ratio']], 
                                      hide_index=True, key="sell_table")

        # Symbol Selection for Charting
        selected_symbol = st.selectbox("Select a Symbol to Chart Details:", options=agg['Symbol'].unique())

        if selected_symbol:
            symbol_data = full_data[full_data['Symbol'] == selected_symbol].copy()
            symbol_data['Buy'] = symbol_data['ShortVolume']
            symbol_data['Sell'] = (symbol_data['TotalVolume'] - symbol_data['ShortVolume']) * -1
            symbol_data['Ratio'] = (symbol_data['ShortVolume'] / (symbol_data['TotalVolume'] - symbol_data['ShortVolume']).replace(0,1)).replace([float('inf')], 100.0)

            # --- PLOTLY: BAR CHART + TREND ---
            st.divider()
            st.subheader(f"Detailed Analysis: {selected_symbol}")
            
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=symbol_data['Date'], y=symbol_data['Buy'], name="Buying", marker_color='green'))
            fig.add_trace(go.Bar(x=symbol_data['Date'], y=symbol_data['Sell'], name="Selling", marker_color='red'))
            fig.add_trace(go.Scatter(x=symbol_data['Date'], y=symbol_data['Ratio'], name="Buy/Sell Trend", line=dict(color='orange', width=3)), secondary_y=True)
            fig.update_layout(title="Daily Buy/Sell Volume with Ratio Trend", barmode='relative', height=500)
            st.plotly_chart(fig, use_container_width=True)

            # --- OPTION A & B DISPLAY ---
            tab1, tab2 = st.tabs(["Option A: Cumulative Pressure", "Option B: Intensity Ratio (%)"])
            
            with tab1:
                fig_a = go.Figure()
                fig_a.add_trace(go.Scatter(x=symbol_data['Date'], y=symbol_data['Buy'].cumsum(), fill='tozeroy', name="Cumul. Buying", line_color='green'))
                fig_a.add_trace(go.Scatter(x=symbol_data['Date'], y=symbol_data['Sell'].abs().cumsum(), fill='tozeroy', name="Cumul. Selling", line_color='red'))
                fig_a.update_layout(title="Cumulative Buying vs Selling Buildup", height=400)
                st.plotly_chart(fig_a, use_container_width=True)

            with tab2:
                symbol_data['Buy%'] = (symbol_data['ShortVolume'] / symbol_data['TotalVolume']) * 100
                symbol_data['Sell%'] = 100 - symbol_data['Buy%']
                fig_b = go.Figure()
                fig_b.add_trace(go.Bar(x=symbol_data['Date'], y=symbol_data['Buy%'], name="Buy %", marker_color='green'))
                fig_b.add_trace(go.Bar(x=symbol_data['Date'], y=symbol_data['Sell%'], name="Sell %", marker_color='red'))
                fig_b.update_layout(barmode='stack', title="Daily Buy/Sell Percentage Intensity", height=400)
                st.plotly_chart(fig_b, use_container_width=True)