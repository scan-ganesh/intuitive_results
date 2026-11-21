import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os, math

# ==============================================================================
# 1. PAGE LAYOUT & STYLING CONFIGURATION
# ==============================================================================
st.set_page_config(
    page_title="Options What-If Strategy Studio",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for polished layout presentation
st.markdown("""
    <style>
    .metric-card {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #008080;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    div[data-testid="stMetricValue"] {
        font-size: 24px !important;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. SIDEBAR OPTIONS / PARAMETER ENGINE
# ==============================================================================
st.sidebar.header("⚙️ Strategy Configuration")

underlying = st.sidebar.selectbox(
    "Select Underlying Index",
    options=["NIFTY", "SENSEX", "CNXBAN"],
    index=1
)

# Filename Mapping Logic
if underlying == "SENSEX":
    FILENAME = "intuitive_BSESEN_results.csv"
    LOT_SIZE = 20
    EXPIRY_WEEKDAY = 3  # SENSEX regular weekly expiry is Friday
elif underlying == "CNXBAN":
    FILENAME = "intuitive_CNXBAN_results.csv"
    LOT_SIZE = 30
    EXPIRY_WEEKDAY = 3  # CNXBAN regular weekly expiry is Friday
else:
    FILENAME = "intuitive_NIFTY_results.csv"
    LOT_SIZE = 65
    EXPIRY_WEEKDAY = 1  # NIFTY regular weekly expiry is Thursday

# Advanced Backtest Overrides
st.sidebar.markdown("---")
st.sidebar.subheader("🎯 Optimizations & Friction")

slippage_input = st.sidebar.slider(
    "Round-Trip Slippage (%)", 
    min_value=0.0, max_value=2.0, value=0.5, step=0.1,
    help="Applies a combined slip penalty on both entry and exit premium values."
)

enable_sl = st.sidebar.checkbox("Apply Hard Stop-Loss (Points)", value=False)
stop_loss_value = None
if enable_sl:
    stop_loss_value = st.sidebar.number_input(
        "Max Allowed Points Loss per Trade", 
        min_value=5, max_value=100, value=35, step=5
    )

# Extract unique hours available if the file is loaded
if os.path.exists(FILENAME):
    temp_df = pd.read_csv(FILENAME)
    temp_df['Entry Time'] = pd.to_datetime(temp_df['Entry Time'])
    available_hours = sorted(temp_df['Entry Time'].dt.hour.unique().tolist())
else:
    available_hours = [9, 10, 11, 12, 13, 14, 15]

skip_hours = st.sidebar.multiselect(
    "Exclude Entry Hours (Slump Filters)",
    options=available_hours,
    default=[],
    help="Select specific session hours to filter out from entry considerations."
)

# Structural Financial Assumptions
st.sidebar.markdown("---")
st.sidebar.subheader("💰 Capital & Cost Structures")
brokerage_fee = st.sidebar.number_input("Brokerage per Complete Trade (₹)", value=40.0)
govt_charges = st.sidebar.number_input("Govt Charges per Lot (₹)", value=32.0)
capital_per_lot = st.sidebar.number_input("Capital Margin Required per Lot (₹)", value=25000.0)

# Dynamic Compounding Engine Feature Toggle
st.sidebar.markdown("---")
st.sidebar.subheader("🔄 Compounding Engine")
position_sizing_mode = st.sidebar.radio(
    "Position Sizing Engine",
    options=["Fixed Baseline (2 Lots)", "Dynamic Compounding / Reverse Sizing"],
    index=0,
    help="Dynamic Mode scales lots up/down step-wise every time equity moves by the single lot capital requirement."
)

# ==============================================================================
# 3. CORE DATA PROCESSING PIPELINE
# ==============================================================================
@st.cache_data
def load_and_process_data(file_path, slip_pct, sl_pts, filter_hours, expiry_day):
    if not os.path.exists(file_path):
        return None
    
    raw_df = pd.read_csv(file_path)
    raw_df['Entry Time'] = pd.to_datetime(raw_df['Entry Time'])
    raw_df['Exit Time'] = pd.to_datetime(raw_df['Exit Time'])
    raw_df['PnL'] = pd.to_numeric(raw_df['PnL'], errors='coerce')
    raw_df['Entry Price'] = pd.to_numeric(raw_df['Entry Price'], errors='coerce')
    raw_df['Exit Price'] = pd.to_numeric(raw_df['Exit Price'], errors='coerce')
    
    # Process DTE Engine Feature
    raw_df['DTE'] = raw_df['Entry Time'].apply(lambda x: x.strftime("%A"))
    
    # 1. Process Slippage
    raw_df['Slippage_Points'] = (slip_pct / 100.0) * (raw_df['Entry Price'] + raw_df['Exit Price'])
    raw_df['Adjusted_PnL'] = raw_df['PnL'] - raw_df['Slippage_Points']
    
    # 2. Process Stop-Loss
    if sl_pts is not None:
        raw_df['Adjusted_PnL'] = np.where(
            raw_df['PnL'] < -sl_pts, 
            -sl_pts - raw_df['Slippage_Points'], 
            raw_df['Adjusted_PnL']
        )
        
    # 3. Process Hour Exclusions
    raw_df['Entry_Hour'] = raw_df['Entry Time'].dt.hour
    if filter_hours:
        raw_df = raw_df[~raw_df['Entry_Hour'].isin(filter_hours)].copy()
        
    raw_df['Month'] = raw_df['Exit Time'].dt.to_period('M').astype(str)
    return raw_df.sort_values('Exit Time').reset_index(drop=True)

df = load_and_process_data(FILENAME, slippage_input, stop_loss_value, skip_hours, EXPIRY_WEEKDAY)

# ==============================================================================
# 4. MAIN DASHBOARD INTERFACE PRESENTATION
# ==============================================================================
st.title("📈 Advanced Options Strategy Studio")
st.markdown(f"**Exploring Market Dynamics:** Engine tracking *{underlying}* contract sequences inside `{FILENAME}`.")

if df is None:
    st.error(f"❌ Target context file `{FILENAME}` could not be located in your local working directory.")
else:
    # --- PROCESS RUNTIME POSITION SIZING SYSTEM ---
    initial_units = 2
    initial_capital = capital_per_lot * initial_units
    
    if position_sizing_mode == "Fixed Baseline (2 Lots)":
        df['Allocated_Lots'] = initial_units
        # Net Rupee P&L = (Points * Lot_Size * Lots) - Friction (Brokerage + Govt_Charges * Lots)
        df['Net_Rupee_PnL'] = (df['Adjusted_PnL'] * LOT_SIZE * df['Allocated_Lots']) - (brokerage_fee + (govt_charges * df['Allocated_Lots']))
        df['Account_Equity'] = initial_capital + df['Net_Rupee_PnL'].cumsum()
    else:
        # Dynamic Compounding Simulation Loop
        run_equity = [initial_capital]
        allocated_lots = []
        rupee_pnl_series = []
        
        for idx, row in df.iterrows():
            # Factor in the floor rule based on the milestone allocation boundary
            current_lots = max(1, math.floor(run_equity[-1] / capital_per_lot))
            allocated_lots.append(current_lots)
            
            # Compute trade friction under the active lot scaling tier
            trade_rupee_pnl = (row['Adjusted_PnL'] * LOT_SIZE * current_lots) - (brokerage_fee + (govt_charges * current_lots))
            rupee_pnl_series.append(trade_rupee_pnl)
            
            new_equity = run_equity[-1] + trade_rupee_pnl
            run_equity.append(new_equity)
            
        df['Allocated_Lots'] = allocated_lots
        df['Net_Rupee_PnL'] = rupee_pnl_series
        df['Account_Equity'] = run_equity[1:]

    # Calculate Performance Summary Metrics
    total_trades = len(df)
    net_points = df['Adjusted_PnL'].sum()
    win_rate = (df['Net_Rupee_PnL'] > 0).sum() / total_trades * 100 if total_trades > 0 else 0
    
    total_rupee_profit = df['Net_Rupee_PnL'].sum()
    gross_profits = df[df['Net_Rupee_PnL'] > 0]['Net_Rupee_PnL'].sum()
    gross_losses = abs(df[df['Net_Rupee_PnL'] <= 0]['Net_Rupee_PnL'].sum())
    profit_factor = gross_profits / gross_losses if gross_losses > 0 else float('inf')
    
    # Absolute Peak and Max Drawdown tracking on cumulative account curve
    peak_equity = df['Account_Equity'].cummax()
    df['Drawdown_Rupees'] = peak_equity - df['Account_Equity']
    max_dd_rupees = df['Drawdown_Rupees'].max()

    # --- ROW 1: CORE RISK METRICS ---
    m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
    with m_col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Total Trades", f"{total_trades}")
        st.markdown('</div>', unsafe_allow_html=True)
    with m_col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Net Financial Return", f"₹{total_rupee_profit:,.2f}")
        st.markdown('</div>', unsafe_allow_html=True)
    with m_col3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Win Rate", f"{win_rate:.2f}%")
        st.markdown('</div>', unsafe_allow_html=True)
    with m_col4:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Profit Factor", f"{profit_factor:.2f}")
        st.markdown('</div>', unsafe_allow_html=True)
    with m_col5:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Max Capital Drawdown", f"₹{max_dd_rupees:,.2f}")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("###")

    # --- ROW 2: PRIMARY CUMULATIVE & POSITION SIZING CHARTS ---
    chart_col1, chart_col2 = st.columns([2, 1])
    
    with chart_col1:
        st.subheader("📊 Interactive Capital Growth Curve")
        fig_curve = px.line(
            df, x='Exit Time', y='Account_Equity',
            labels={'Account_Equity': 'Account Capitalization (₹)', 'Exit Time': 'Timeline'},
            color_discrete_sequence=['#008080']
        )
        fig_curve.update_layout(margin=dict(l=20, r=20, t=10, b=20), hovermode="x unified")
        st.plotly_chart(fig_curve, use_container_width=True)
        
    with chart_col2:
        st.subheader("⏳ Lots Allocation & Session DTE")
        if position_sizing_mode == "Dynamic Compounding / Reverse Sizing":
            # Show how the algorithm dynamically altered sizes over time using a step line
            fig_lots = px.line(
                df, x='Exit Time', y='Allocated_Lots',
                labels={'Allocated_Lots': 'Active Sizing Lots', 'Exit Time': 'Timeline'},
                color_discrete_sequence=['#e67e22'],
                line_shape='hv'  # <-- This transforms the line chart into a step chart
            )
            fig_lots.update_layout(margin=dict(l=20, r=20, t=10, b=20))
            st.plotly_chart(fig_lots, use_container_width=True)
        else:
            # Fall back to DTE metrics if sizing is statically uniform
            dte_stats = df.groupby('DTE')['Adjusted_PnL'].agg(['mean']).reset_index()
            fig_dte = px.bar(
                dte_stats, x='DTE', y='mean',
                labels={'DTE': 'Days to Expiry', 'mean': 'Avg Points'},
                color='mean', color_continuous_scale=px.colors.sequential.Viridis,
                text_auto='.1f'
            )
            fig_dte.update_layout(margin=dict(l=20, r=20, t=10, b=20), coloraxis_showscale=False)
            st.plotly_chart(fig_dte, use_container_width=True)

    # --- ROW 3: SCALING & CAPITAL MULTIPLIERS ---
    st.markdown("---")
    st.subheader("📈 Multi-Lot Capital Scalability Matrix")
    
    lot_multipliers = [1, 2, 5, 10, 20, 50]
    scaling_data = []
    
    for lots in lot_multipliers:
        total_costs = (brokerage_fee + (govt_charges * lots)) * total_trades
        net_rupee_profit_static = (df['Adjusted_PnL'] * LOT_SIZE * lots).sum() - total_costs
        allocated_capital = capital_per_lot * lots * 2
        return_pct = (net_rupee_profit_static / allocated_capital) * 100 if allocated_capital > 0 else 0
        
        scaling_data.append({
            "Lots": f"{lots} Lots",
            "Net Profit (₹)": round(net_rupee_profit_static, 2),
            "Total Capital Margin (₹)": round(allocated_capital, 2),
            "Return Profile (%)": round(return_pct, 2)
        })
        
    scale_df = pd.DataFrame(scaling_data)
    
    sc_col1, sc_col2 = st.columns([1, 1])
    with sc_col1:
        st.dataframe(
            scale_df.style.format({
                "Net Profit (₹)": "₹{:,.2f}",
                "Total Capital Margin (₹)": "₹{:,.2f}",
                "Return Profile (%)": "{:.2f}%"
            }), use_container_width=True
        )
    with sc_col2:
        fig_scale = go.Figure()
        fig_scale.add_trace(go.Bar(name='Net Return %', x=scale_df['Lots'], y=scale_df['Return Profile (%)'], marker_color='#e07a5f'))
        fig_scale.update_layout(title_text="Return Efficiency % Across Static Scaling Steps", margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig_scale, use_container_width=True)

    # --- ROW 4: YEAR-WISE RETURNS TABLE MATRIX ---
    st.markdown("---")
    st.subheader("🗓️ Year-wise Returns Matrix (Net ₹)")

    df['Year_Num'] = df['Exit Time'].dt.year
    df['Month_Num'] = df['Exit Time'].dt.month

    matrix_pivot = df.pivot_table(index='Year_Num', columns='Month_Num', values='Net_Rupee_PnL', aggfunc='sum').fillna(0)

    for month_idx in range(1, 13):
        if month_idx not in matrix_pivot.columns:
            matrix_pivot[month_idx] = 0.0

    matrix_pivot = matrix_pivot[list(range(1, 13))]
    matrix_pivot.columns = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    matrix_pivot['Total'] = matrix_pivot.sum(axis=1)
    matrix_pivot['Max Drawdown'] = -max_dd_rupees

    st.dataframe(
        matrix_pivot.style.format(lambda x: f"₹{int(x):,}" if x != 0 else "0")
        .map(lambda x: 'color: #2baf5d; font-weight: bold;' if x > 0 else ('color: #d9534f;' if x < 0 else 'color: #999999;')),
        use_container_width=True
    )

    # --- ROW 5: RAW DATA EXPLORER ---
    st.markdown("---")
    with st.expander("🔍 Inspect Underlying Transaction Logs"):
        st.dataframe(df[['Entry Time', 'Exit Time', 'DTE', 'Body Size', 'Entry Price', 'Exit Price', 'PnL', 'Slippage_Points', 'Adjusted_PnL', 'Allocated_Lots', 'Net_Rupee_PnL', 'Account_Equity']], use_container_width=True)