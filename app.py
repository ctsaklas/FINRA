import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from io import StringIO
from datetime import datetime, timedelta

# App Configuration
st.set_page_config(page_title="Dark Pool Flow Analyzer", layout="wide")

# --- ORIGINAL DESCRIPTIVE TEXT RESTORED ---
st.title("📊 Dark Pool Institutional Flow Analyzer")
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
# When date_range changes, Streamlit reruns the whole script automatically
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
    """Fetches FINRA Aggregated data and formats the Date column."""
    url = f"https://cdn.finra.org/equity/regsho/daily/FNYRAshvol{date_str}.txt"
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(StringIO(response.text), sep='|')
            df = df.dropna(subset=['Symbol'])
            df['ShortVolume'] = pd.to_numeric(df['ShortVolume'], errors='coerce').fillna(0)
            df['TotalVolume'] = pd.to_numeric(df['TotalVolume'], errors='coerce').fillna(0)
            # Store date as string to prevent Unix Epoch (1970) chart issues
            df['Date_Label'] = pd.to_datetime(date_str, format='%Y%m%d').strftime('%Y-%m-%d')
            return df[['Date_Label', 'Symbol', 'ShortVolume', 'TotalVolume']]
    except: return None
    return None

# --- MAIN EXECUTION (REACTIVE) ---
if len(date_range) == 2:
    start_date, end_date = date_range
    all_dfs = []
    
    # Calculate days to fetch
    current_date = start_date
    days_diff = (end_date - start_date).days + 1
    
    # Data Retrieval loop (Outside of a button for automatic recalculation)
    with st.spinner('Updating analysis...'):
        for i in range(days_diff):
            if current_date.weekday() < 5:
                df = fetch_finra_data(current_date.strftime("%Y%m%d"))
                if df is not None: all_dfs.append(df)
            current_date += timedelta(days=1)
        
    if all_dfs:
        full_data = pd.concat(all_dfs)
        
        # Aggregate logic for Top 15 Tables
        agg = full_data.groupby('Symbol').agg({'ShortVolume':'sum', 'TotalVolume':'sum'}).reset_index()
        agg = agg[agg['TotalVolume'] >= vol_threshold]
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
                st.data_editor(buy_list[display_cols].style.format({'Buy/Sell Ratio': '{:.2f}', 'TotalVolume': '{:,.0f}', 'Buy Vol': '{:,.0f}', 'Sell Vol': '{:,.0f}'}), hide_index=True, key="buy_table")
            else:
                st.info("No stocks found with >60% consolidated Buying pressure.")
            
        with col2:
            st.subheader("📉 Top 15 Selling Volume (>60%)")
            sell_list = agg[agg['SellPct'] > 0.60].sort_values('Sell Vol', ascending=False).head(15)
            if not sell_list.empty:
                st.data_editor(sell_list[display_cols].style.format({'Buy/Sell Ratio': '{:.2f}', 'TotalVolume': '{:,.0f}', 'Buy Vol': '{:,.0f}', 'Sell Vol': '{:,.0f}'}), hide_index=True, key="sell_table")
            else:
                st.info("No stocks found with >60% consolidated Selling pressure.")

        # --- CHARTING SECTION ---
        # Allow selection from the current aggregated list
        st.divider()
        selected_symbol = st.selectbox("Select a Symbol to View Historical Chart:", options=sorted(agg['Symbol'].unique()))

        if selected_symbol:
            symbol_data = full_data[full_data['Symbol'] == selected_symbol].copy().sort_values('Date_Label')
            symbol_data['Buy'] = symbol_data['ShortVolume']
            symbol_data['Sell'] = symbol_data['TotalVolume'] - symbol_data['ShortVolume']
            symbol_data['Ratio'] = (symbol_data['Buy'] / symbol_data['Sell'].replace(0, 0.0001)).replace([float('inf')], 100.0)

            st.subheader(f"Detailed Analysis: {selected_symbol} ({len(symbol_data)} Trading Days)")
            
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            # Primary Bars: Buying and Selling side-by-side above 0
            fig.add_trace(go.Bar(x=symbol_data['Date_Label'], y=symbol_data['Buy'], name="Buying (Short)", marker_color='green'))
            fig.add_trace(go.Bar(x=symbol_data['Date_Label'], y=symbol_data['Sell'], name="Selling (Long)", marker_color='red'))
            
            # Trend Line
            fig.add_trace(go.Scatter(x=symbol_data['Date_Label'], y=symbol_data['Ratio'], name="Buy/Sell Trend", line=dict(color='orange', width=3)), secondary_y=True)
            
            fig.update_layout(
                barmode='group', 
                height=600, 
                xaxis_title="Trading Date", 
                yaxis_title="Volume", 
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            
            # Use 'category' type to explicitly prevent 1970 date scaling
            fig.update_xaxes(type='category', categoryorder='category ascending')
            fig.update_yaxes(title_text="Volume (Shares)", secondary_y=False)
            fig.update_yaxes(title_text="Buy/Sell Ratio", secondary_y=True)
            
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No data retrieved for the selected range. Please ensure markets were open.")
else:
    st.info("Select a full date range in the sidebar to begin analysis.")