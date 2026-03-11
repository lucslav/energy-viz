import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Limerick Energy", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

st.title("⚡ My Energy - Limerick")

with st.sidebar:
    st.header("⚙️ Ustawienia Cen")
    price_day = st.number_input("Day Rate (€)", value=0.3397, format="%.4f")
    price_peak = st.number_input("Peak Rate (€)", value=0.3624, format="%.4f")
    price_night = st.number_input("Night Rate (€)", value=0.1785, format="%.4f")
    standing_ch = st.number_input("Daily Standing (€)", value=0.6303, format="%.4f")

uploaded_file = st.file_uploader("Dodaj plik CSV z licznika", type="csv")

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    df['Timestamp'] = pd.to_datetime(df['Read Date and End Time'], format='%d-%m-%Y %H:%M')
    df['Usage_kWh'] = df['Read Value'].diff().fillna(0)
    df = df[(df['Usage_kWh'] >= 0) & (df['Usage_kWh'] < 100)]
    
    def get_tariff(ts):
        h = ts.hour
        if 17 <= h < 19: return 'Peak'
        elif 23 <= h or h < 8: return 'Night'
        return 'Day'
    
    df['Tariff'] = df['Timestamp'].apply(get_tariff)
    prices = {'Day': price_day, 'Peak': price_peak, 'Night': price_night}
    df['Cost_EUR'] = df.apply(lambda r: r['Usage_kWh'] * prices[r['Tariff']], axis=1)

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Suma kWh", f"{df['Usage_kWh'].sum():.1f}")
    with c2:
        days = (df['Timestamp'].max() - df['Timestamp'].min()).days
        total_cost = (df['Cost_EUR'].sum() + (max(1, days) * standing_ch)) * 1.09
        st.metric("Est. Bill (inc. VAT)", f"€{total_cost:.2f}")

    tab1, tab2, tab3 = st.tabs(["📊 Dzień", "🗓️ Tyg/Mies", "💰 Taryfy"])
    with tab1:
        daily = df.groupby(df['Timestamp'].dt.date)['Usage_kWh'].sum().reset_index()
        st.plotly_chart(px.bar(daily, x='Timestamp', y='Usage_kWh'), use_container_width=True)
    with tab2:
        freq = st.radio("Widok:", ["Tygodniowy", "Miesięczny"], horizontal=True)
        agg = df.resample('W' if freq=="Tygodniowy" else 'M', on='Timestamp')['Usage_kWh'].sum().reset_index()
        st.plotly_chart(px.bar(agg, x='Timestamp', y='Usage_kWh'), use_container_width=True)
    with tab3:
        tariff_sum = df.groupby('Tariff')['Usage_kWh'].sum().reset_index()
        st.plotly_chart(px.pie(tariff_sum, values='Usage_kWh', names='Tariff', hole=.4), use_container_width=True)
else:
    st.info("👋 Wrzuć plik CSV, aby zobaczyć statystyki.")
  
