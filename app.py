import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Energy Viz", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

st.title("⚡ Energy Viz - Smart Meter Dashboard")

# Sidebar - Pricing Settings
with st.sidebar:
    st.header("⚙️ Tariff Settings")
    price_day = st.number_input("Day Rate (€)", value=0.3397, format="%.4f")
    price_peak = st.number_input("Peak Rate (€)", value=0.3624, format="%.4f")
    price_night = st.number_input("Night Rate (€)", value=0.1785, format="%.4f")
    standing_ch = st.number_input("Daily Standing Charge (€)", value=0.6303, format="%.4f")
    st.info("Note: 9% VAT is added to cost visualizations.")

uploaded_file = st.file_uploader("Upload your Smart Meter CSV file", type="csv")

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    
    # Date conversion and sorting
    df['Timestamp'] = pd.to_datetime(df['Read Date and End Time'], format='%d-%m-%Y %H:%M')
    df = df.sort_values('Timestamp')
    
    # Fix outlier in data (Wh to kWh conversion for values > 100k)
    df.loc[df['Read Value'] > 100000, 'Read Value'] = df['Read Value'] / 1000
    
    # Calculate usage between reads
    df['Usage_kWh'] = df['Read Value'].diff().fillna(0)
    df = df[df['Usage_kWh'] >= 0]
    
    # Tariff logic
    def get_tariff(ts):
        h = ts.hour
        if h == 0 and ts.minute == 0: return 'Day'
        if 17 <= h < 19: return 'Peak'
        elif 23 <= h or h < 8: return 'Night'
        return 'Day'
    
    df['Tariff'] = df['Timestamp'].apply(get_tariff)
    prices = {'Day': price_day, 'Peak': price_peak, 'Night': price_night}
    
    # Calculate costs (Net and with 9% VAT)
    df['Cost_Net'] = df.apply(lambda r: r['Usage_kWh'] * prices[r['Tariff']], axis=1)
    df['Cost_VAT'] = df['Cost_Net'] * 1.09

    if not df.empty:
        # Metrics Row
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Total Usage", f"{df['Usage_kWh'].sum():.1f} kWh")
        with c2:
            days = (df['Timestamp'].max() - df['Timestamp'].min()).days
            total_bill = (df['Cost_Net'].sum() + (max(1, days) * standing_ch)) * 1.09
            st.metric("Est. Total Bill", f"€{total_bill:.2f}")
        with c3:
            avg_daily = df['Usage_kWh'].sum() / max(1, days)
            st.metric("Avg. Daily Usage", f"{avg_daily:.2f} kWh")

        st.divider()

        # UNIT SELECTOR
        view_mode = st.radio("Select View:", ["Energy (kWh)", "Cost (€ inc. VAT)"], horizontal=True)
        
        target_col = 'Usage_kWh' if view_mode == "Energy (kWh)" else 'Cost_VAT'
        y_label = 'kWh' if view_mode == "Energy (kWh)" else 'Euro (€)'
        color_hex = '#00CC96' if view_mode == "Energy (kWh)" else '#EF553B'

        # Visualizations
        tab1, tab2 = st.tabs(["📊 Daily Data", "🗓️ Trends"])
        
        with tab1:
            daily = df.groupby(df['Timestamp'].dt.date)[target_col].sum().reset_index()
            fig = px.bar(daily, x='Timestamp', y=target_col, 
                         title=f"Daily {view_mode}",
                         labels={target_col: y_label, 'Timestamp': 'Date'},
                         color_discrete_sequence=[color_hex])
            st.plotly_chart(fig, use_container_width=True)
            
        with tab2:
            view = st.radio("Group by:", ["Weekly", "Monthly"], horizontal=True)
            freq = 'W' if view == "Weekly" else 'M'
            agg = df.resample(freq, on='Timestamp')[target_col].sum().reset_index()
            fig_trend = px.line(agg, x='Timestamp', y=target_col, 
                                title=f"{view} {view_mode} Trend",
                                markers=True,
                                color_discrete_sequence=[color_hex])
            st.plotly_chart(fig_trend, use_container_width=True)
            
    else:
        st.error("Could not process data. Please check the CSV format.")
else:
    st.info("👋 Welcome! Please upload your Smart Meter HDF file to begin analysis.")
    
