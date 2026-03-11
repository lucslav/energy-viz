import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Energy Viz", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

# --- CUSTOM CSS FOR MODERN LOOK ---
st.markdown("""
    <style>
    .stMetric {
        background-color: rgba(240, 242, 246, 0.5);
        padding: 15px;
        border-radius: 15px;
        border: 1px solid #e6e9ef;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
    }
    .chart-container {
        border: 1px solid #e6e9ef;
        padding: 10px;
        border-radius: 15px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("⚡ Energy Viz")
st.caption("Smart Meter Analytics | Limerick, IE")

with st.sidebar:
    st.header("⚙️ Tariff Settings")
    price_day = st.number_input("Day Rate (€)", value=0.3397, format="%.4f")
    price_peak = st.number_input("Peak Rate (€)", value=0.3624, format="%.4f")
    price_night = st.number_input("Night Rate (€)", value=0.1785, format="%.4f")
    standing_ch = st.number_input("Daily Standing Charge (€)", value=0.6303, format="%.4f")
    st.info("9% VAT included in cost charts.")

uploaded_file = st.file_uploader("Upload your ESB HDF file", type="csv")

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    df['Timestamp'] = pd.to_datetime(df['Read Date and End Time'], format='%d-%m-%Y %H:%M')
    df = df.sort_values('Timestamp')
    
    # Data correction (Wh to kWh)
    df.loc[df['Read Value'] > 100000, 'Read Value'] = df['Read Value'] / 1000
    df['Usage_kWh'] = df['Read Value'].diff().fillna(0)
    df = df[df['Usage_kWh'] >= 0]
    
    # Prices and VAT
    prices = {'Day': price_day, 'Peak': price_peak, 'Night': price_night}
    df['Cost_VAT'] = df.apply(lambda r: r['Usage_kWh'] * prices['Day'], axis=1) * 1.09 # Default to Day for Daily HDF

    # --- METRICS SECTION ---
    days = (df['Timestamp'].max() - df['Timestamp'].min()).days
    total_bill = (df['Cost_VAT'].sum() + (max(1, days) * standing_ch * 1.09))
    avg_daily = df['Usage_kWh'].sum() / max(1, days)

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Usage", f"{df['Usage_kWh'].sum():.1f} kWh")
    m2.metric("Est. Bill", f"€{total_bill:.2f}")
    m3.metric("Avg. Daily", f"{avg_daily:.2f} kWh")

    st.markdown("---")

    # --- CHART CONTROLS ---
    c1, c2 = st.columns([1, 2])
    with c1:
        view_mode = st.segmented_control("View Unit:", ["kWh", "Euro (€)"], default="kWh")
    
    target_col = 'Usage_kWh' if view_mode == "kWh" else 'Cost_VAT'
    color_hex = '#00CC96' if view_mode == "kWh" else '#FF4B4B'

    # --- TABS FOR CHARTS ---
    tab1, tab2 = st.tabs(["📊 Daily Charts", "📈 Long-term Trends"])

    with tab1:
        daily = df.groupby(df['Timestamp'].dt.date)[target_col].sum().reset_index()
        fig = px.bar(daily, x='Timestamp', y=target_col, 
                     template="plotly_white",
                     color_discrete_sequence=[color_hex])
        fig.update_layout(margin=dict(l=20, r=20, t=30, b=20), bordercolor="#eee")
        st.plotly_chart(fig, use_container_width=True)
            
    with tab2:
        view = st.radio("Group by:", ["Weekly", "Monthly"], horizontal=True)
        freq = 'W' if view == "Weekly" else 'M'
        agg = df.resample(freq, on='Timestamp')[target_col].sum().reset_index()
        fig_trend = px.area(agg, x='Timestamp', y=target_col, 
                            template="plotly_white",
                            color_discrete_sequence=[color_hex])
        st.plotly_chart(fig_trend, use_container_width=True)

else:
    st.info("👋 Drop your CSV file here to start.")
    
