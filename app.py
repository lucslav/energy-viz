import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, text

# --- DATABASE SETUP ---
DB_PATH = "/app/data/energy_viz.db"
engine = create_engine(f"sqlite:///{DB_PATH}")

def init_db():
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY,
                day_rate REAL, night_rate REAL, peak_rate REAL,
                standing_charge REAL, vat_rate REAL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS consumption (
                timestamp DATETIME PRIMARY KEY,
                value REAL,
                type TEXT
            )
        """))
        conn.commit()

def save_to_db(df, data_type):
    df = df.rename(columns={'Timestamp': 'timestamp', 'Value': 'value'})
    df['type'] = data_type
    # Fixed transaction logic for SQLite persistence
    with engine.begin() as conn:
        df.to_sql('temp_upload', conn, if_exists='replace', index=False)
        conn.execute(text("""
            INSERT OR REPLACE INTO consumption (timestamp, value, type)
            SELECT timestamp, value, type FROM temp_upload
        """))
        conn.execute(text("DROP TABLE IF EXISTS temp_upload"))

# --- UI STYLING ---
LOGO_URL = "https://raw.githubusercontent.com/lucslav/energy-viz/main/img/logo.png"
st.set_page_config(page_title="Energy Viz", page_icon=LOGO_URL, layout="wide")
init_db()

st.markdown("""
    <style>
    [data-testid="stMetric"] { background-color: rgba(240, 242, 246, 0.4); padding: 15px; border-radius: 12px; border: 1px solid #e6e9ef; }
    .main-header { background-color: #ffffff; padding: 20px; border-radius: 15px; border: 1px solid #e6e9ef; box-shadow: 0 2px 4px rgba(0,0,0,0.03); margin-bottom: 20px; display: flex; align-items: center; justify-content: center; gap: 20px; }
    .status-box { background-color: #f8f9fa; padding: 10px 15px; border-radius: 8px; border: 1px solid #dee2e6; margin-bottom: 20px; font-size: 0.9rem; border-left: 5px solid #00CC96; }
    .mode-badge { padding: 5px 15px; border-radius: 20px; font-weight: bold; font-size: 0.8rem; margin-bottom: 10px; display: inline-block; }
    .badge-kwh { background-color: #00CC96; color: white; }
    .badge-kw { background-color: #FF4B4B; color: white; }
    .badge-dnp { background-color: #636EFA; color: white; }
    .badge-basic { background-color: #7f8c8d; color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- SETTINGS LOADING ---
settings_df = pd.read_sql("SELECT * FROM settings WHERE id=1", engine)
if settings_df.empty:
    st.header("⚡ Energy Viz Setup")
    with st.form("init_settings"):
        c1, c2 = st.columns(2)
        with c1:
            dr = st.number_input("Day Rate (€)", value=0.3397, format="%.4f")
            pr = st.number_input("Peak Rate (€)", value=0.3624, format="%.4f")
            nr = st.number_input("Night Rate (€)", value=0.1785, format="%.4f")
        with c2:
            sc = st.number_input("Daily Standing (€)", value=0.6303, format="%.4f")
            vt = st.number_input("VAT Rate (%)", value=9.0)
        if st.form_submit_button("Save Rates"):
            pd.DataFrame([{'id':1,'day_rate':dr,'peak_rate':pr,'night_rate':nr,'standing_charge':sc,'vat_rate':vt}]).to_sql('settings', engine, if_exists='replace', index=False)
            st.rerun()
    st.stop()

s = settings_df.iloc[0]
v_mul = 1 + (s['vat_rate'] / 100)

# --- HEADER ---
st.markdown(f'<div class="main-header"><img src="{LOGO_URL}" width="55"><div style="text-align: left;"><h1 style="margin:0; font-size: 2rem;">Energy Viz</h1><p style="color:gray; margin:0;">Interactive ESB Smart Meter Analytics</p></div></div>', unsafe_allow_html=True)

# --- UPLOAD SECTION ---
with st.expander("📤 Data Upload & Auto-Detection"):
    up = st.file_uploader("Upload ESB CSV file", type="csv", label_visibility="collapsed")
    if up:
        raw = pd.read_csv(up)
        date_col = 'Read Date and End Time' if 'Read Date and End Time' in raw.columns else 'Timestamp'
        raw['Timestamp'] = pd.to_datetime(raw[date_col], dayfirst=True)
        r_types = " ".join(raw['Read Type'].astype(str).unique()).lower() if 'Read Type' in raw.columns else ""
        
        # Mapping to ESB types
        if "interval (kwh)" in r_types: m = "CALC_KWH"
        elif "interval (kw)" in r_types: m = "READ_KW"
        elif "register (kwh)" in r_types: m = "DNP_SNAPSHOT"
        else: m = "TOTAL_SNAPSHOT"
        
        df_save = pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')})
        save_to_db(df_save.dropna(), m)
        st.success(f"File stored as: {m}")
        st.rerun()

# --- CONTENT ---
full_data = pd.read_sql("SELECT * FROM consumption ORDER BY timestamp ASC", engine, parse_dates=['timestamp'])

if not full_data.empty:
    tabs = st.tabs([
        "📊 30-min calculated kWh", 
        "📈 30-min readings in kW", 
        "📅 Daily snapshot DNP", 
        "📜 Daily total & export"
    ])

    def show_status(df_subset, esb_name, badge_class):
        if not df_subset.empty:
            start = df_subset['timestamp'].min().strftime('%Y-%m-%d')
            end = df_subset['timestamp'].max().strftime('%Y-%m-%d')
            st.markdown(f'<div class="mode-badge {badge_class}">ACTIVE: {esb_name}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="status-box">📂 <b>Database Status:</b> Records from <b>{start}</b> to <b>{end}</b> ({len(df_subset)} records).</div>', unsafe_allow_html=True)
            return True
        else:
            st.info(f"Please upload the ESB file: **'{esb_name}'** to see analytics here.")
            return False

    # 1. 30-minute readings in calculated kWh
    with tabs[0]:
        df = full_data[full_data['type'] == "CALC_KWH"].copy()
        if show_status(df, "30-minute readings in calculated kWh", "badge-kwh"):
            def get_tariff(dt):
                h = dt.hour
                if 17 <= h < 19: return 'Peak'
                elif h >= 23 or h < 8: return 'Night'
                else: return 'Day'
            
            df['Tariff'] = df['timestamp'].apply(get_tariff)
            rates = {'Day': s['day_rate'], 'Night': s['night_rate'], 'Peak': s['peak_rate']}
            df['Cost_VAT'] = df.apply(lambda r: r['value'] * rates[r['Tariff']] * v_mul, axis=1)
            
            days = max(1, len(df['timestamp'].dt.date.unique()))
            total_kwh = df['value'].sum()
            total_cost = df['Cost_VAT'].sum() + (days * s['standing_charge'] * v_mul)
            
            # KPIs
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Usage", f"{total_kwh:.1f} kWh")
            c2.metric("Total Cost", f"€{total_cost:.2f}")
            c3.metric("Avg Daily Usage", f"{(total_kwh/days):.2f} kWh")
            c4.metric("Avg Daily Cost", f"€{(total_cost/days):.2f}")
            
            view = st.radio("Display:", ["Usage (kWh)", "Cost (€)"], horizontal=True, key="pro_view")
            y_col = 'value' if "Usage" in view else 'Cost_VAT'
            daily = df.groupby([df['timestamp'].dt.date, 'Tariff'])[y_col].sum().reset_index()
            fig = px.bar(daily, x='timestamp', y=y_col, color='Tariff', 
                         color_discrete_map={'Day': '#00CC96', 'Night': '#636EFA', 'Peak': '#EF553B'},
                         barmode='stack', template="plotly_white")
            fig.update_xaxes(rangeslider_visible=True)
            st.plotly_chart(fig, width="stretch")

    # 2. 30-minute readings in kW
    with tabs[1]:
        df = full_data[full_data['type'] == "READ_KW"].copy()
        if show_status(df, "30-minute readings in kW", "badge-kw"):
            fig_kw = px.line(df, x='timestamp', y='value', line_shape='hv', color_discrete_sequence=['#FF4B4B'], template="plotly_white")
            fig_kw.update_xaxes(rangeslider_visible=True)
            st.plotly_chart(fig_kw, width="stretch")
            st.metric("Max Peak Load", f"{df['value'].max():.2f} kW")

    # 3. Daily snapshot of day/night/peak usage in actual kWh*
    with tabs[2]:
        df = full_data[full_data['type'] == "DNP_SNAPSHOT"].copy()
        if show_status(df, "Daily snapshot of day/night/peak usage in actual kWh*", "badge-dnp"):
            fig_dnp = px.bar(df, x='timestamp', y='value', template="plotly_white")
            fig_dnp.update_xaxes(rangeslider_visible=True)
            st.plotly_chart(fig_dnp, width="stretch")

    # 4. Daily snapshot of total usage and export data
    with tabs[3]:
        df = full_data[full_data['type'] == "TOTAL_SNAPSHOT"].copy()
        if show_status(df, "Daily snapshot of total usage and export data in actual kWh", "badge-basic"):
            fig_total = px.area(df, x='timestamp', y='value', color_discrete_sequence=['#7f
                                                                                       
