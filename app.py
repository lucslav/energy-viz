import streamlit as st
import pandas as pd
import plotly.express as px

# Page configuration
st.set_page_config(page_title="Energy Viz", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

# --- UI STYLING ---
st.markdown("""
    <style>
    [data-testid="stMetric"] { background-color: rgba(240, 242, 246, 0.4); padding: 15px; border-radius: 12px; border: 1px solid #e6e9ef; }
    .main-header { background-color: #ffffff; padding: 20px; border-radius: 15px; border: 1px solid #e6e9ef; box-shadow: 0 2px 4px rgba(0,0,0,0.03); margin-bottom: 20px; display: flex; align-items: center; justify-content: center; gap: 20px; }
    .recommendation-box { background-color: #e1f5fe; padding: 15px; border-radius: 10px; border-left: 5px solid #0288d1; margin-bottom: 15px; }
    .mode-badge { padding: 5px 15px; border-radius: 20px; font-weight: bold; font-size: 0.9rem; margin-bottom: 20px; display: inline-block; }
    .badge-kwh { background-color: #00CC96; color: white; }
    .badge-kw { background-color: #FF4B4B; color: white; }
    .badge-dnp { background-color: #636EFA; color: white; }
    .badge-basic { background-color: #7f8c8d; color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- HEADER ---
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

# --- QUICK GUIDE (IMPERSONAL VERSION) ---
st.markdown("""
<div class="recommendation-box">
    <strong>🎯 Quick Guide:</strong> It is strongly recommended to upload: 
    <u>30-minute readings in calculated kWh</u> for the best experience.
</div>
""", unsafe_allow_html=True)

with st.expander("📊 Available File Modes & Features"):
    st.markdown("""
    - **30-minute readings in calculated kWh:** Full professional analytics & tariff costs.
    - **30-minute readings in kW:** Detailed power demand spikes analysis.
    - **Daily snapshot of day/night/peak usage:** Quick daily tariff overview.
    - **Daily snapshot of total usage:** Basic consumption history.
    """)

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Tariff Settings")
    p_day = st.number_input("Day Rate (€)", value=0.3397, format="%.4f")
    p_peak = st.number_input("Peak Rate (€) (17-19)", value=0.3624, format="%.4f")
    p_night = st.number_input("Night Rate (€) (23-08)", value=0.1785, format="%.4f")
    standing_ch = st.number_input("Daily Standing (€)", value=0.6303, format="%.4f")
    st.divider()
    st.info("Calculations include 9% VAT.")

uploaded_file = st.file_uploader("Upload ESB CSV file", type="csv")

def get_tariff(dt):
    h = dt.hour
    if 17 <= h < 19: return 'Peak'
    elif h >= 23 or h < 8: return 'Night'
    else: return 'Day'

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    date_col = 'Read Date and End Time' if 'Read Date and End Time' in df.columns else 'Timestamp'
    df['Timestamp'] = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Timestamp']).sort_values('Timestamp')
    
    # --- MODE DETECTION ---
    r_types = " ".join(df['Read Type'].astype(str).unique()).lower() if 'Read Type' in df.columns else ""
    
    if "interval (kwh)" in r_types:
        mode, label, css = "KWH_INTERVAL", "Professional Analytics (30-min kWh)", "badge-kwh"
    elif "interval (kw)" in r_types:
        mode, label, css = "KW_DEMAND", "Power Demand Study (30-min kW)", "badge-kw"
    elif "register (kwh)" in r_types and any(x in r_types for x in ["night", "peak"]):
        mode, label, css = "DAILY_DNP", "Daily Tariff Summary (DNP)", "badge-dnp"
    else:
        mode, label, css = "DAILY_TOTAL", "Basic History (Daily Total)", "badge-basic"

    st.markdown(f'<div class="mode-badge {css}">CURRENT MODE: {label}</div>', unsafe_allow_html=True)

    # --- DATA PROCESSING ---
    if mode == "KW_DEMAND":
        st.subheader("Power Demand Spikes")
        fig_kw = px.line(df, x='Timestamp', y='Read Value', title="Power Demand (kW) over Time",
                         line_shape='hv', color_discrete_sequence=['#FF4B4B'], template="plotly_white")
        
        # Rangeslider configuration with mini-graph
        fig_kw.update_xaxes(
            rangeslider_visible=True,
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1d", step="day", stepmode="backward"),
                    dict(count=7, label="1w", step="day", stepmode="backward"),
                    dict(step="all")
                ])
            )
        )
        fig_kw.update_layout(xaxis_title="Time", yaxis_title="Load (kW)", margin=dict(b=100), height=600)
        
        st.plotly_chart(fig_kw, use_container_width=True)
        st.metric("Peak Power Recorded", f"{df['Read Value'].max():.2f} kW")

    else:
        # kWh Variants
        if mode == "KWH_INTERVAL":
            df['Usage_kWh'] = df['Read Value']
            df['Tariff'] = df['Timestamp'].apply(get_tariff)
        elif mode == "DAILY_DNP":
            def map_dnp(t):
                t = t.lower()
                if 'night' in t: return 'Night'
                if 'peak' in t and 'off' not in t: return 'Peak'
                return 'Day'
            df['Tariff'] = df['Read Type'].apply(map_dnp)
            df['Usage_kWh'] = df.groupby('Read Type')['Read Value'].diff().fillna(0)
        else: # DAILY_TOTAL
            df.loc[df['Read Value'] > 100000, 'Read Value'] = df['Read Value'] / 1000
            df['Usage_kWh'] = df['Read Value'].diff().fillna(0)
            df['Tariff'] = 'Day'

        df = df[df['Usage_kWh'] >= 0]
        
        def calc_cost(r):
            rate = p_peak if r['Tariff'] == 'Peak' else (p_night if r['Tariff'] == 'Night' else p_day)
            return r['Usage_kWh'] * rate * 1.09
        df['Cost_VAT'] = df.apply(calc_cost, axis=1)

        days = max(1, (df['Timestamp'].max() - df['Timestamp'].min()).days)
        months = max(1, days / 30.44)
        total_usage = df['Usage_kWh'].sum()
        total_cost = df['Cost_VAT'].sum() + (days * standing_ch * 1.09)

        st.subheader("Key Performance Indicators")
        c1, c2 = st.columns(2)
        c1.metric("Total Usage", f"{total_usage:.1f} kWh")
        c2.metric("Total Cost", f"€{total_cost:.2f}")

        c3, c4, c5, c6 = st.columns(4)
        c3.metric("Avg Monthly Usage", f"{(total_usage/months):.1f} kWh")
        c4.metric("Avg Monthly Cost", f"€{(total_cost/months):.2f}")
        c5.metric("Avg Daily Usage", f"{(total_usage/days):.2f} kWh")
        c6.metric("Avg Daily Cost", f"€{(total_cost/days):.2f}")

        st.divider()

        view_mode = st.radio("Chart Metric:", ["kWh", "Euro (€)"], horizontal=True)
        target_col = 'Usage_kWh' if view_mode == "kWh" else 'Cost_VAT'
        chart_color = '#00CC96' if view_mode == "kWh" else '#FF4B4B'

        tab1, tab2 = st.tabs(["📊 Daily Snapshot", "📈 Long-term Trends"])
        
        with tab1:
            st.write(f"Daily {view_mode} Breakdown")
            daily = df.groupby([df['Timestamp'].dt.date, 'Tariff'])[target_col].sum().reset_index()
            fig_bar = px.bar(daily, x='Timestamp', y=target_col, color='Tariff',
                             color_discrete_map={'Day': '#00CC96', 'Night': '#636EFA', 'Peak': '#EF553B'},
                             template="plotly_white", barmode='stack')
            fig_bar.update_xaxes(rangeslider_visible=True)
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with tab2:
            st.write(f"Accumulated {view_mode} Trend")
            freq = st.radio("Frequency:", ["Weekly", "Monthly"], horizontal=True)
            agg = df.resample('W' if freq == "Weekly" else 'M', on='Timestamp')[target_col].sum().reset_index()
            fig_trend = px.area(agg, x='Timestamp', y=target_col, markers=True,
                                color_discrete_sequence=[chart_color], template="plotly_white")
            fig_trend.update_xaxes(rangeslider_visible=True)
            st.plotly_chart(fig_trend, use_container_width=True)
else:
    st.info("👋 Welcome! Please upload any ESB HDF file to start the analysis.")
    
