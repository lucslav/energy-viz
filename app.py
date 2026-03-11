import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Energy Viz", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

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
                <p style="color:gray; margin:0;">Professional Analytics</p>
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

uploaded_file = st.file_uploader("Upload ESB CSV file", type="csv")

def get_tariff(dt):
    if 17 <= dt.hour < 19: return 'Peak'
    elif dt.hour >= 23 or dt.hour < 8: return 'Night'
    else: return 'Day'

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    df['Timestamp'] = pd.to_datetime(df['Read Date and End Time'], format='%d-%m-%Y %H:%M')
    df = df.sort_values('Timestamp')
    
    df.loc[df['Read Value'] > 100000, 'Read Value'] = df['Read Value'] / 1000
    df['Usage_kWh'] = df['Read Value'].diff().fillna(0)
    df = df[df['Usage_kWh'] >= 0]
    
    df['Tariff'] = df['Timestamp'].apply(get_tariff)
    
    def calc_cost(row):
        rate = p_peak if row['Tariff'] == 'Peak' else (p_night if row['Tariff'] == 'Night' else p_day)
        return row['Usage_kWh'] * rate * 1.09

    df['Cost_VAT'] = df.apply(calc_cost, axis=1)

    days = max(1, (df['Timestamp'].max() - df['Timestamp'].min()).days)
    total_usage = df['Usage_kWh'].sum()
    total_cost_energy = df['Cost_VAT'].sum()
    total_standing = days * standing_ch * 1.09
    total_bill = total_cost_energy + total_standing

    # --- TOP METRICS ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Usage", f"{total_usage:.1f} kWh")
    m2.metric("Estimated Bill", f"€{total_bill:.2f}")
    m3.metric("Avg. Daily Usage", f"{(total_usage/days):.2f} kWh")
    m4.metric("Avg. Daily Cost", f"€{(total_bill/days):.2f}")

    st.divider()

    st.subheader("Tariff Analysis")
    t_col1, t_col2 = st.columns([2, 1])
    
    with t_col1:
        tariff_daily = df.groupby([df['Timestamp'].dt.date, 'Tariff'])['Usage_kWh'].sum().reset_index()
        fig_tariff = px.bar(tariff_daily, x='Timestamp', y='Usage_kWh', color='Tariff',
                           color_discrete_map={'Day': '#00CC96', 'Night': '#636EFA', 'Peak': '#EF553B'},
                           template="plotly_white", barmode='stack')
        fig_tariff.update_layout(height=400, margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(fig_tariff, use_container_width=True)

    with t_col2:
        tariff_sum = df.groupby('Tariff')['Usage_kWh'].sum().reset_index()
        fig_pie = px.pie(tariff_sum, values='Usage_kWh', names='Tariff', hole=0.5,
                        color='Tariff', color_discrete_map={'Day': '#00CC96', 'Night': '#636EFA', 'Peak': '#EF553B'})
        fig_pie.update_layout(height=400, showlegend=True)
        st.plotly_chart(fig_pie, use_container_width=True)

    st.divider()

    view_mode = st.radio("Chart Unit:", ["kWh", "Euro (€)"], horizontal=True)
    target_col = 'Usage_kWh' if view_mode == "kWh" else 'Cost_VAT'
    
    tab1, tab2 = st.tabs(["📊 Daily History", "📈 Trends"])
    with tab1:
        daily = df.groupby(df['Timestamp'].dt.date)[target_col].sum().reset_index()
        fig_main = px.bar(daily, x='Timestamp', y=target_col, template="plotly_white", color_discrete_sequence=['#00CC96'])
        fig_main.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig_main, use_container_width=True)
            
    with tab2:
        freq_choice = st.radio("Frequency:", ["Weekly", "Monthly"], horizontal=True)
        freq = 'W' if freq_choice == "Weekly" else 'M'
        agg = df.resample(freq, on='Timestamp')[target_col].sum().reset_index()
        fig_trend = px.area(agg, x='Timestamp', y=target_col, template="plotly_white", markers=True)
        fig_trend.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig_trend, use_container_width=True)
else:
    st.info("👋 Upload CSV to begin analysis.")
    
