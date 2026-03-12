import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Energy Viz", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

# --- UI STYLING ---
st.markdown("""
    <style>
    [data-testid="stMetric"] { background-color: rgba(240, 242, 246, 0.4); padding: 15px; border-radius: 12px; border: 1px solid #e6e9ef; }
    .main-header { background-color: #ffffff; padding: 20px; border-radius: 15px; border: 1px solid #e6e9ef; box-shadow: 0 2px 4px rgba(0,0,0,0.03); margin-bottom: 25px; display: flex; align-items: center; justify-content: center; gap: 20px; }
    .recommendation-box { background-color: #e1f5fe; padding: 15px; border-radius: 10px; border-left: 5px solid #0288d1; margin-bottom: 20px; }
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

# --- REKOMENDACJA I OPIS PLIKÓW ---
st.markdown("""
<div class="recommendation-box">
    <strong>🎯 Quick Guide: Which file should you upload?</strong><br>
    To get the most accurate cost analysis and see your Day/Night/Peak breakdown, we 
    <strong>strongly recommend</strong> downloading the second option from ESB Networks: 
    <u>30-minute readings in calculated kWh</u>.
</div>
""", unsafe_allow_html=True)

with st.expander("📊 See what each file type offers:"):
    st.markdown("""
    * **30-minute readings in calculated kWh (Recommended):** Full analysis of Day/Night/Peak usage and the most accurate bill estimation.
    * **30-minute readings in kW:** Focuses on power demand. Shows when you had the highest electricity "spikes" (e.g., using many appliances at once).
    * **Daily snapshot of day/night/peak usage:** Provides a daily summary without 30-minute details. Good for a quick overview.
    * **Daily snapshot of total usage and export:** Essential if you have solar panels to track how much energy you send back to the grid.
    """)

with st.sidebar:
    st.header("⚙️ Tariff Settings")
    p_day = st.number_input("Day Rate (€)", value=0.3397, format="%.4f")
    p_peak = st.number_input("Peak Rate (€) (17-19)", value=0.3624, format="%.4f")
    p_night = st.number_input("Night Rate (€) (23-08)", value=0.1785, format="%.4f")
    standing_ch = st.number_input("Daily Standing (€)", value=0.6303, format="%.4f")
    st.divider()
    st.info("Prices include 9% VAT.")

uploaded_file = st.file_uploader("Upload ESB CSV file", type="csv")

def get_tariff(dt):
    h = dt.hour
    if 17 <= h < 19: return 'Peak'
    elif h >= 23 or h < 8: return 'Night'
    else: return 'Day'

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    # Obsługa kolumny Timestamp lub Read Date and End Time
    date_col = 'Read Date and End Time' if 'Read Date and End Time' in df.columns else 'Timestamp'
    df['Timestamp'] = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Timestamp']).sort_values('Timestamp')
    
    # --- AUTOMATYCZNE WYKRYWANIE TRYBU ---
    read_type_sample = " ".join(df['Read Type'].astype(str).unique()).lower() if 'Read Type' in df.columns else ""
    
    if "demand" in read_type_sample or "(kw)" in read_type_sample:
        mode = "kW_POWER"
    elif "export" in read_type_sample:
        mode = "EXPORT_MODE"
    elif df['Timestamp'].dt.hour.nunique() > 1:
        mode = "KWH_INTERVAL"
    else:
        mode = "DAILY_SNAPSHOT"

    # --- WARIANT 1: POMIAR MOCY (kW) ---
    if mode == "kW_POWER":
        st.info("📊 **Current Mode:** 30-minute readings in kW (Power Demand)")
        fig_kw = px.line(df, x='Timestamp', y='Read Value', 
                         title="Power Demand Spikes (kW)",
                         line_shape='hv', color_discrete_sequence=['#FF4B4B'])
        fig_kw.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig_kw, use_container_width=True)
        st.metric("Peak Power Demand", f"{df['Read Value'].max():.2f} kW")

    # --- WARIANT 2: ZUŻYCIE ENERGII (kWh) ---
    elif mode == "KWH_INTERVAL" or mode == "DAILY_SNAPSHOT":
        if "interval" in read_type_sample:
            df['Usage_kWh'] = df['Read Value'] 
        else:
            # Korekta dla starych plików Wh/kWh
            df.loc[df['Read Value'] > 100000, 'Read Value'] = df['Read Value'] / 1000
            df['Usage_kWh'] = df['Read Value'].diff().fillna(0)
            df = df[df['Usage_kWh'] >= 0]
        
        df['Tariff'] = df['Timestamp'].apply(get_tariff)
        df['Cost_VAT'] = df.apply(lambda r: r['Usage_kWh'] * (p_peak if r['Tariff'] == 'Peak' else (p_night if r['Tariff'] == 'Night' else p_day)) * 1.09, axis=1)

        # Statystyki
        days_count = max(1, (df['Timestamp'].max() - df['Timestamp'].min()).days)
        months_count = max(1, days_count / 30.44)
        total_usage = df['Usage_kWh'].sum()
        total_cost = df['Cost_VAT'].sum() + (days_count * standing_ch * 1.09)

        st.subheader("Key Performance Indicators")
        m_col1, m_col2 = st.columns(2)
        m_col1.metric("Total Usage", f"{total_usage:.1f} kWh")
        m_col2.metric("Total Cost", f"€{total_cost:.2f}")

        st.subheader("Daily Snapshot of Tariff Usage")
        daily_tariff = df.groupby([df['Timestamp'].dt.date, 'Tariff'])['Usage_kWh'].sum().reset_index()
        fig_snap = px.bar(daily_tariff, x='Timestamp', y='Usage_kWh', color='Tariff',
                          color_discrete_map={'Day': '#00CC96', 'Night': '#636EFA', 'Peak': '#EF553B'},
                          template="plotly_white", barmode='stack')
        fig_snap.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig_snap, use_container_width=True)

    # --- WARIANT 3: EXPORT / SOLAR ---
    elif mode == "EXPORT_MODE":
        st.success("☀️ **Current Mode:** Solar Export/Import Data")
        pivot_df = df.pivot_table(index=df['Timestamp'].dt.date, columns='Read Type', values='Read Value', aggfunc='sum').reset_index()
        fig_solar = px.bar(pivot_df, x='Timestamp', barmode='group', template="plotly_white",
                           color_discrete_sequence=['#00CC96', '#636EFA'])
        st.plotly_chart(fig_solar, use_container_width=True)

else:
    st.info("👋 Please upload an ESB CSV file to begin your analysis.")
    
