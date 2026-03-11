import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Energy Viz", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

# --- UI STYLING ---
st.markdown("""
    <style>
    [data-testid="stMetric"] { background-color: rgba(240, 242, 246, 0.4); padding: 15px; border-radius: 12px; border: 1px solid #e6e9ef; }
    .main-header { background-color: #ffffff; padding: 20px; border-radius: 15px; border: 1px solid #e6e9ef; box-shadow: 0 2px 4px rgba(0,0,0,0.03); margin-bottom: 25px; display: flex; align-items: center; justify-content: center; gap: 20px; }
    </style>
    """, unsafe_allow_html=True)

with st.container():
    st.markdown(f"""
        <div class="main-header">
            <img src="https://raw.githubusercontent.com/lucslav/energy-viz/main/img/logo.png" width="55">
            <div style="text-align: left;">
                <h1 style="margin:0; font-size: 2rem; letter-spacing: -1px;">Energy Viz</h1>
                <p style="color:gray; margin:0;">ESB Smart Meter Analysis</p>
            </div>
        </div>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Tariff Settings")
    p_day = st.number_input("Day Rate (€)", value=0.3397, format="%.4f")
    p_peak = st.number_input("Peak Rate (€) (17-19)", value=0.3624, format="%.4f")
    p_night = st.number_input("Night Rate (€) (23-08)", value=0.1785, format="%.4f")
    standing_ch = st.number_input("Daily Standing (€)", value=0.6303, format="%.4f")
    st.divider()
    st.info("Prices include 9% VAT.")

with st.expander("ℹ️ How to get the correct data file?"):
    st.markdown("""
    To see full **Day/Night/Peak** breakdown:
    1. Log in to **ESB Networks Online Store**.
    2. Select: **"HDF Half-hourly energy consumption data"** (2nd option).
    3. Download and upload the CSV here.
    """)

uploaded_file = st.file_uploader("Upload ESB CSV file", type="csv")

def get_tariff(dt):
    h = dt.hour
    if 17 <= h < 19: return 'Peak'
    elif h >= 23 or h < 8: return 'Night'
    else: return 'Day'

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    df['Timestamp'] = pd.to_datetime(df['Read Date and End Time'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Timestamp']).sort_values('Timestamp')
    
    # --- AUTO-DETECT DATA TYPE (Cumulative vs Interval) ---
    read_type = str(df['Read Type'].iloc[0]).lower()
    
    if "interval" in read_type:
        # If HDF Half-hourly, Read Value is likely the actual usage for that 30min
        df['Usage_kWh'] = df['Read Value']
    else:
        # If Daily or Register, it's cumulative and needs differentiation
        df.loc[df['Read Value'] > 100000, 'Read Value'] = df['Read Value'] / 1000
        df['Usage_kWh'] = df['Read Value'].diff().fillna(0)
    
    df = df[df['Usage_kWh'] >= 0]
    df['Tariff'] = df['Timestamp'].apply(get_tariff)
    
    def calc_cost(row):
        rate = p_peak if row['Tariff'] == 'Peak' else (p_night if row['Tariff'] == 'Night' else p_day)
        return row['Usage_kWh'] * rate * 1.09

    df['Cost_VAT'] = df.apply(calc_cost, axis=1)

    # Stats
    days_count = max(1, (df['Timestamp'].max() - df['Timestamp'].min()).days)
    months_count = max(1, days_count / 30.44)
    total_usage = df['Usage_kWh'].sum()
    total_cost_full = df['Cost_VAT'].sum() + (days_count * standing_ch * 1.09)

    # Metrics
    st.subheader("Key Performance Indicators")
    c1, c2 = st.columns(2)
    c1.metric("Total Usage", f"{total_usage:.1f} kWh")
    c2.metric("Total Cost", f"€{total_cost_full:.2f}")

    c3, c4, c5, c6 = st.columns(4)
    c3.metric("Avg Monthly Usage", f"{(total_usage/months_count):.1f} kWh")
    c4.metric("Avg Monthly Cost", f"€{(total_cost_full/months_count):.2f}")
    c5.metric("Avg Daily Usage", f"{(total_usage/days_count):.2f} kWh")
    c6.metric("Avg Daily Cost", f"€{(total_cost_full/days_count):.2f}")

    st.divider()

    # Pie Chart
    st.subheader("Tariff Usage Distribution")
    if df['Timestamp'].dt.hour.nunique() == 1:
        st.error("🚨 This file only contains daily totals. Use 'Half-hourly' file for breakdown.")
    else:
        tariff_sum = df.groupby('Tariff')['Usage_kWh'].sum().reset_index()
        fig_pie = px.pie(tariff_sum, values='Usage_kWh', names='Tariff', hole=0.5,
                        color='Tariff', color_discrete_map={'Day': '#00CC96', 'Night': '#636EFA', 'Peak': '#EF553B'})
        st.plotly_chart(fig_pie, use_container_width=True)

    st.divider()

    # Historical Charts
    view_mode = st.radio("Chart Metric:", ["kWh", "Euro (€)"], horizontal=True)
    target_col = 'Usage_kWh' if view_mode == "kWh" else 'Cost_VAT'
    chart_color = '#00CC96' if view_mode == "kWh" else '#FF4B4B'
    
    tab1, tab2 = st.tabs(["📊 Daily History", "📈 Trends"])
    with tab1:
        daily_df = df.groupby(df['Timestamp'].dt.date)[target_col].sum().reset_index()
        fig_main = px.bar(daily_df, x='Timestamp', y=target_col, template="plotly_white", color_discrete_sequence=[chart_color])
        fig_main.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig_main, use_container_width=True)
            
    with tab2:
        freq_opt = st.radio("Group By:", ["Weekly", "Monthly"], horizontal=True)
        agg_df = df.resample('W' if freq_opt == "Weekly" else 'M', on='Timestamp')[target_col].sum().reset_index()
        fig_trend = px.area(agg_df, x='Timestamp', y=target_col, template="plotly_white", markers=True, color_discrete_sequence=[chart_color])
        fig_trend.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig_trend, use_container_width=True)
else:
    st.info("👋 Please upload your ESB HDF CSV file.")
    
