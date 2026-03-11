import streamlit as st
import pandas as pd
import plotly.express as px

# Konfiguracja strony
st.set_page_config(page_title="Energy Viz", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

# --- CUSTOM CSS DLA NOWOCZESNEGO WYGLĄDU ---
st.markdown("""
    <style>
    [data-testid="stMetric"] {
        background-color: rgba(240, 242, 246, 0.4);
        padding: 20px;
        border-radius: 15px;
        border: 1px solid #e6e9ef;
    }
    .main-header {
        background-color: #ffffff; 
        padding: 25px; 
        border-radius: 15px; 
        border: 1px solid #e6e9ef; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.03); 
        margin-bottom: 25px; 
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

# --- NAGŁÓWEK W RAMCE ---
with st.container():
    st.markdown("""
        <div class="main-header">
            <h1 style="color: #0e1117; font-family: 'Source Sans Pro', sans-serif; margin: 0; font-size: 2.2rem; letter-spacing: -1px;">Energy Viz</h1>
            <p style="color: #606770; font-size: 1rem; margin-top: 5px; font-weight: 400;">Smart Meter Analytics</p>
        </div>
    """, unsafe_allow_html=True)

# --- SIDEBAR - USTAWIENIA TARYF ---
with st.sidebar:
    st.header("⚙️ Tariff Settings")
    price_day = st.number_input("Day Rate (€)", value=0.3397, format="%.4f")
    price_peak = st.number_input("Peak Rate (€)", value=0.3624, format="%.4f")
    price_night = st.number_input("Night Rate (€)", value=0.1785, format="%.4f")
    standing_ch = st.number_input("Daily Standing Charge (€)", value=0.6303, format="%.4f")
    st.divider()
    st.info("9% VAT is included in all cost calculations.")

# --- WGRYWANIE PLIKU ---
uploaded_file = st.file_uploader("Upload your Smart Meter CSV file", type="csv")

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    
    # Konwersja daty i sortowanie chronologiczne
    df['Timestamp'] = pd.to_datetime(df['Read Date and End Time'], format='%d-%m-%Y %H:%M')
    df = df.sort_values('Timestamp')
    
    # KOREKTA DANYCH (Naprawa błędu Wh vs kWh z Twojego pliku)
    # Jeśli wartość skacze nagle powyżej 100k, dzielimy przez 1000
    df.loc[df['Read Value'] > 100000, 'Read Value'] = df['Read Value'] / 1000
    
    # Obliczanie zużycia (różnica między odczytami)
    df['Usage_kWh'] = df['Read Value'].diff().fillna(0)
    
    # Odfiltrowanie błędnych ujemnych wartości
    df = df[df['Usage_kWh'] >= 0]
    
    # Obliczanie kosztów (Cena netto * 1.09 VAT)
    # Dla plików HDF Daily stosujemy stawkę Day jako domyślną dla całego dnia
    df['Cost_VAT'] = df['Usage_kWh'] * price_day * 1.09

    # --- SEKCJA METRYK (PODSUMOWANIE) ---
    days = (df['Timestamp'].max() - df['Timestamp'].min()).days
    if days == 0: days = 1
    
    total_usage = df['Usage_kWh'].sum()
    total_bill = df['Cost_VAT'].sum() + (days * standing_ch * 1.09)
    avg_daily = total_usage / days

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Usage", f"{total_usage:.1f} kWh")
    m2.metric("Estimated Bill", f"€{total_bill:.2f}")
    m3.metric("Avg. Daily", f"{avg_daily:.2f} kWh")

    st.divider()

    # --- WYBÓR JEDNOSTKI WYKRESU ---
    view_mode = st.radio("Select View Mode:", ["Energy (kWh)", "Cost (€ inc. VAT)"], horizontal=True)
    
    target_col = 'Usage_kWh' if view_mode == "Energy (kWh)" else 'Cost_VAT'
    y_label = 'kWh' if view_mode == "Energy (kWh)" else 'Euro (€)'
    color_hex = '#00CC96' if view_mode == "Energy (kWh)" else '#FF4B4B'

    # --- WYKRESY W KONTENERACH Z RAMKĄ ---
    tab1, tab2 = st.tabs(["📊 Daily Data", "📈 Long-term Trends"])

    with tab1:
        st.subheader(f"Daily Consumption in {view_mode}")
        with st.container(border=True):
            daily = df.groupby(df['Timestamp'].dt.date)[target_col].sum().reset_index()
            fig = px.bar(daily, x='Timestamp', y=target_col, 
                         template="plotly_white",
                         labels={target_col: y_label, 'Timestamp': 'Date'},
                         color_discrete_sequence=[color_hex])
            
            # DODANIE SUWAKA DO SKROLOWANIA (Range Slider)
            fig.update_xaxes(rangeslider_visible=True)
            fig.update_layout(height=550, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
            
    with tab2:
        st.subheader("Consumption Trends Over Time")
        with st.container(border=True):
            group_view = st.radio("Grouping:", ["Weekly", "Monthly"], horizontal=True)
            freq = 'W' if group_view == "Weekly" else 'M'
            
            agg = df.resample(freq, on='Timestamp')[target_col].sum().reset_index()
            fig_trend = px.area(agg, x='Timestamp', y=target_col, 
                                template="plotly_white",
                                labels={target_col: y_label, 'Timestamp': 'Date'},
                                markers=True,
                                color_discrete_sequence=[color_hex])
            
            # DODANIE SUWAKA DO SKROLOWANIA (Range Slider)
            fig_trend.update_xaxes(rangeslider_visible=True)
            fig_trend.update_layout(height=550, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_trend, use_container_width=True)

else:
    # Ekran powitalny, gdy nie ma pliku
    st.info("👋 Welcome! Please upload your ESB Networks HDF file to begin the analysis.")
    st.markdown("""
        1. Download your **HDF Daily CSV** from ESB Networks.
        2. Drag and drop it above.
        3. Adjust your tariff rates in the sidebar to see accurate costs.
    """)
    
