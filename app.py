import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Energy Viz", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

# --- MODERN STYLING ---
st.markdown("""
    <style>
    /* Styling for the metric cards */
    [data-testid="stMetric"] {
        background-color: rgba(240, 242, 246, 0.4);
        padding: 20px;
        border-radius: 15px;
        border: 1px solid #e6e9ef;
    }
    /* Adjusting title size */
    h1 {
        font-weight: 800 !important;
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
    st.divider()
    st.info("9% VAT is automatically added to all cost calculations.")

uploaded_file = st.file_uploader("Upload your ESB HDF file", type="csv")

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    
    # Process data
    df['Timestamp'] = pd.to_datetime(df['Read Date and End Time'], format='%d-%m-%Y %H:%M')
    df = df.sort_values('Timestamp')
    
    # Outlier correction
    df.loc[df['Read Value'] > 100000, 'Read Value'] = df['Read Value'] / 1000
    df['Usage_kWh'] = df['Read Value'].diff().fillna(0)
    df = df[df['Usage_kWh'] >= 0]
    
    # Cost calculation (including VAT)
    df['Cost_VAT'] = df['Usage_kWh'] * price_day * 1.09 # Simplified for daily reads

    # --- TOP METRICS IN FRAMES ---
    days = (df['Timestamp'].max() - df['Timestamp'].min()).days
    total_bill = (df['Cost_VAT'].sum() + (max(1, days) * standing_ch * 1.09))
    avg_daily = df['Usage_kWh'].sum() / max(1, days)

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Usage", f"{df['Usage_kWh'].sum():.1f} kWh")
    m2.metric("Estimated Bill", f"€{total_bill:.2f}")
    m3.metric("Avg. Daily", f"{avg_daily:.2f} kWh")

    st.divider()

    # --- CHART CONTROL ---
    view_mode = st.radio("Select View Mode:", ["Energy (kWh)", "Cost (€ inc. VAT)"], horizontal=True)
    
    target_col = 'Usage_kWh' if view_mode == "Energy (kWh)" else 'Cost_VAT'
    y_label = 'kWh' if view_mode == "Energy (kWh)" else 'Euro (€)'
    color_hex = '#00CC96' if view_mode == "Energy (kWh)" else '#FF4B4B'

    # --- CHARTS IN CONTAINERS WITH BORDERS ---
    tab1, tab2 = st.tabs(["📊 Daily Data", "📈 Trends"])

    with tab1:
        st.subheader(f"Daily {view_mode}")
        with st.container(border=True):
            daily = df.groupby(df['Timestamp'].dt.date)[target_col].sum().reset_index()
            fig = px.bar(daily, x='Timestamp', y=target_col, 
                         template="plotly_white",
                         labels={target_col: y_label, 'Timestamp': 'Date'},
                         color_discrete_sequence=[color_hex])
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
            
    with tab2:
        st.subheader("Consumption Trends")
        with st.container(border=True):
            view = st.radio("Grouping:", ["Weekly", "Monthly"], horizontal=True)
            freq = 'W' if view == "Weekly" else 'M'
            agg = df.resample(freq, on='Timestamp')[target_col].sum().reset_index()
            fig_trend = px.area(agg, x='Timestamp', y=target_col, 
                                template="plotly_white",
                                labels={target_col: y_label, 'Timestamp': 'Date'},
                                markers=True,
                                color_discrete_sequence=[color_hex])
            fig_trend.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_trend, use_container_width=True)

else:
    st.info("👋 To get started, please upload your ESB Networks CSV file.")
    
