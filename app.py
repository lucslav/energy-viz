import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Energy Viz", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

# --- MODERN STYLING ---
st.markdown("""
    <style>
    [data-testid="stMetric"] {
        background-color: rgba(240, 242, 246, 0.4);
        padding: 20px;
        border-radius: 15px;
        border: 1px solid #e6e9ef;
    }
    .main-header {
        padding: 20px;
        border-radius: 15px;
        border: 1px solid #e6e9ef;
        background-color: #ffffff;
        margin-bottom: 25px;
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

# --- HEADER IN A BOX ---
with st.container():
    st.markdown("""
        <div class="main-header">
            <h1 style='margin:0;'>⚡ Energy Viz</h1>
            <p style='color:gray; margin:0;'>Smart Meter Analytics</p>
        </div>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Tariff Settings")
    price_day = st.number_input("Day Rate (€)", value=0.3397, format="%.4f")
    price_peak = st.number_input("Peak Rate (€)", value=0.3624, format="%.4f")
    price_night = st.number_input("Night Rate (€)", value=0.1785, format="%.4f")
    standing_ch = st.number_input("Daily Standing Charge (€)", value=0.6303, format="%.4f")
    st.divider()
    st.info("9% VAT included in cost calculations.")

uploaded_file = st.file_uploader("Upload your ESB HDF file", type="csv")

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    df['Timestamp'] = pd.to_datetime(df['Read Date and End Time'], format='%d-%m-%Y %H:%M')
    df = df.sort_values('Timestamp')
    
    # Data correction
    df.loc[df['Read Value'] > 100000, 'Read Value'] = df['Read Value'] / 1000
    df['Usage_kWh'] = df['Read Value'].diff().fillna(0)
    df = df[df['Usage_kWh'] >= 0]
    
    # Cost calculation
    df['Cost_VAT'] = df['Usage_kWh'] * price_day * 1.09

    # --- METRICS ---
    days = (df['Timestamp'].max() - df['Timestamp'].min()).days
    total_bill = (df['Cost_VAT'].sum() + (max(1, days) * standing_ch * 1.09))
    avg_daily = df['Usage_kWh'].sum() / max(1, days)

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Usage", f"{df['Usage_kWh'].sum():.1f} kWh")
    m2.metric("Estimated Bill", f"€{total_bill:.2f}")
    m3.metric("Avg. Daily", f"{avg_daily:.2f} kWh")

    st.divider()
    view_mode = st.radio("Select View Mode:", ["kWh", "Euro (€)"], horizontal=True)
    target_col = 'Usage_kWh' if view_mode == "kWh" else 'Cost_VAT'
    color_hex = '#00CC96' if view_mode == "kWh" else '#FF4B4B'

    tab1, tab2 = st.tabs(["📊 Daily Data", "📈 Trends"])

    with tab1:
        with st.container(border=True):
            daily = df.groupby(df['Timestamp'].dt.date)[target_col].sum().reset_index()
            fig = px.bar(daily, x='Timestamp', y=target_col, 
                         template="plotly_white",
                         color_discrete_sequence=[color_hex])
            # ADDING RANGE SLIDER FOR EASIER NAVIGATION
            fig.update_xaxes(rangeslider_visible=True)
            fig.update_layout(height=500, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)
            
    with tab2:
        with st.container(border=True):
            view = st.radio("Grouping:", ["Weekly", "Monthly"], horizontal=True)
            freq = 'W' if view == "Weekly" else 'M'
            agg = df.resample(freq, on='Timestamp')[target_col].sum().reset_index()
            fig_trend = px.area(agg, x='Timestamp', y=target_col, 
                                template="plotly_white", markers=True,
                                color_discrete_sequence=[color_hex])
            fig_trend.update_xaxes(rangeslider_visible=True)
            fig_trend.update_layout(height=500, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_trend, use_container_width=True)

else:
    st.info("👋 Upload CSV to begin.")
  
