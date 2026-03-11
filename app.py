import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Energy Viz", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

st.title("⚡ Energy Viz - Smart Meter Dashboard")

# Sidebar - Pricing Settings (Optimized for Ireland)
with st.sidebar:
    st.header("⚙️ Tariff Settings")
    price_day = st.number_input("Day Rate (€)", value=0.3397, format="%.4f")
    price_peak = st.number_input("Peak Rate (€)", value=0.3624, format="%.4f")
    price_night = st.number_input("Night Rate (€)", value=0.1785, format="%.4f")
    standing_ch = st.number_input("Daily Standing Charge (€)", value=0.6303, format="%.4f")

uploaded_file = st.file_uploader("Upload your Smart Meter CSV file", type="csv")

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    
    # Date conversion and sorting
    df['Timestamp'] = pd.to_datetime(df['Read Date and End Time'], format='%d-%m-%Y %H:%M')
    df = df.sort_values('Timestamp')
    
    # Fix outlier in data (e.g., Wh instead of kWh)
    # Based on your file, values > 100k are likely in Wh
    df.loc[df['Read Value'] > 100000, 'Read Value'] = df['Read Value'] / 1000
    
    # Calculate usage between reads
    df['Usage_kWh'] = df['Read Value'].diff().fillna(0)
    
    # Filter out invalid records
    df = df[df['Usage_kWh'] >= 0]
    
    # Tariff logic (Simplified for HDF Daily data)
    def get_tariff(ts):
        h = ts.hour
        if h == 0 and ts.minute == 0: return 'Day' # Default for daily summaries
        if 17 <= h < 19: return 'Peak'
        elif 23 <= h or h < 8: return 'Night'
        return 'Day'
    
    df['Tariff'] = df['Timestamp'].apply(get_tariff)
    prices = {'Day': price_day, 'Peak': price_peak, 'Night': price_night}
    df['Cost_EUR'] = df.apply(lambda r: r['Usage_kWh'] * prices[r['Tariff']], axis=1)

    if not df.empty:
        # Metrics Row
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Total Usage", f"{df['Usage_kWh'].sum():.1f} kWh")
        with c2:
            days = (df['Timestamp'].max() - df['Timestamp'].min()).days
            total_cost = (df['Cost_EUR'].sum() + (max(1, days) * standing_ch)) * 1.09 # +9% VAT
            st.metric("Est. Total Bill", f"€{total_cost:.2f}")
        with c3:
            avg_daily = df['Usage_kWh'].sum() / max(1, days)
            st.metric("Avg. Daily Usage", f"{avg_daily:.2f} kWh")

        # Visualizations
        tab1, tab2 = st.tabs(["📊 Daily Usage", "🗓️ Trends"])
        
        with tab1:
            daily = df.groupby(df['Timestamp'].dt.date)['Usage_kWh'].sum().reset_index()
            fig = px.bar(daily, x='Timestamp', y='Usage_kWh', 
                         title="Daily Consumption (kWh)",
                         labels={'Usage_kWh': 'kWh', 'Timestamp': 'Date'},
                         color_discrete_sequence=['#00CC96'])
            st.plotly_chart(fig, use_container_width=True)
            
        with tab2:
            view = st.radio("Group by:", ["Weekly", "Monthly"], horizontal=True)
            freq = 'W' if view == "Weekly" else 'M'
            agg = df.resample(freq, on='Timestamp')['Usage_kWh'].sum().reset_index()
            fig_trend = px.line(agg, x='Timestamp', y='Usage_kWh', 
                                title=f"{view} Consumption Trend",
                                markers=True,
                                color_discrete_sequence=['#636EFA'])
            st.plotly_chart(fig_trend, use_container_width=True)
            
    else:
        st.error("Could not process data. Please check the CSV format.")
else:
    st.info("👋 Welcome! Please upload your ESB Networks HDF file to begin analysis.")
    
