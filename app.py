import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

# --- DATABASE ---
DB_PATH = "/app/data/energy_viz.db"
engine = create_engine(f"sqlite:///{DB_PATH}")
LOGO_URL = "https://raw.githubusercontent.com/lucslav/energy-viz/main/img/logo.png"

def init_db():
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, day_rate REAL, night_rate REAL, peak_rate REAL, standing_charge REAL, vat_rate REAL)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS consumption (timestamp DATETIME, value REAL, type TEXT, PRIMARY KEY (timestamp, type))"))
        conn.commit()

@st.cache_data
def load_all_data():
    try:
        return pd.read_sql("SELECT * FROM consumption ORDER BY timestamp ASC", engine, parse_dates=['timestamp'])
    except:
        return pd.DataFrame()

def save_data(df, data_type):
    df = df.rename(columns={'Timestamp': 'timestamp', 'Value': 'value'})
    df['type'] = data_type
    df = df[df['value'] < 100000]
    with engine.begin() as conn:
        df.to_sql('temp_upload', conn, if_exists='replace', index=False)
        conn.execute(text("INSERT OR REPLACE INTO consumption (timestamp, value, type) SELECT timestamp, value, type FROM temp_upload"))
        conn.execute(text("DROP TABLE IF EXISTS temp_upload"))
    st.cache_data.clear()

# --- AGGRESSIVE CSS RESET ---
st.set_page_config(page_title="Energy Viz", page_icon=LOGO_URL, layout="wide")
init_db()

st.markdown(f"""
    <style>
    /* 1. Global Background Reset */
    .stApp {{
        background-color: #ffffff !important;
    }}

    /* 2. Remove Main Container Padding */
    .block-container {{
        padding: 0rem 2rem 2rem 2rem !important;
        max-width: 100% !important;
    }}

    /* 3. Kill all vertical gaps and dividers */
    [data-testid="stVerticalBlock"] > div {{
        gap: 0rem !important;
        padding-top: 0rem !important;
        padding-bottom: 0rem !important;
    }}
    
    hr {{ display: none !important; }}

    /* 4. Flatten Metrics */
    [data-testid="stMetric"] {{
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0px !important;
    }}
    
    [data-testid="stMetricValue"] {{
        font-size: 2.2rem !important;
        font-weight: 800 !important;
        color: #0f172a !important;
    }}

    /* 5. Seamless Section Containers */
    .dashboard-section {{
        background-color: #ffffff;
        padding: 0px !important;
        margin-bottom: 40px !important;
    }}

    .section-title {{
        font-size: 1.8rem;
        font-weight: 900;
        color: #1e293b;
        letter-spacing: -1.5px;
        margin-bottom: 10px;
    }}

    /* 6. Fix Header */
    .main-header {{
        text-align: center;
        padding: 40px 0px;
        margin-bottom: 20px;
    }}
    
    /* Remove Expander Border */
    .streamlit-expanderHeader {{
        border: none !important;
        background-color: #f8fafc !important;
        border-radius: 10px !important;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR & SETTINGS ---
settings_df = pd.read_sql("SELECT * FROM settings WHERE id=1", engine)
v_mul = 1.09 

with st.sidebar:
    st.image(LOGO_URL, width=100)
    if not settings_df.empty:
        s = settings_df.iloc[0]
        st.write(f"🟢 **Night:** `{s['night_rate'] * v_mul:.4f}`")
        st.write(f"🟡 **Day:** `{s['day_rate'] * v_mul:.4f}`")
        st.write(f"🔴 **Peak:** `{s['peak_rate'] * v_mul:.4f}`")
        st.write(f"📅 **Standing:** `{s['standing_charge'] * v_mul:.4f}`")
        if st.button("Reset All", use_container_width=True):
            with engine.begin() as conn: conn.execute(text("DELETE FROM consumption"))
            st.cache_data.clear()
            st.rerun()

if settings_df.empty:
    with st.form("setup"):
        dr, pr, nr, sc = st.number_input("Day", 0.3397), st.number_input("Peak", 0.3624), st.number_input("Night", 0.1785), st.number_input("Standing", 0.6303)
        if st.form_submit_button("Start"):
            pd.DataFrame([{'id':1,'day_rate':dr,'peak_rate':pr,'night_rate':nr,'standing_charge':sc,'vat_rate':9.0}]).to_sql('settings', engine, if_exists='replace', index=False)
            st.rerun()
    st.stop()

# --- HEADER ---
st.markdown(f'''
    <div class="main-header">
        <img src="{LOGO_URL}" width="160">
        <h1 style="font-size: 4rem; margin: 0; letter-spacing: -4px;">Energy Viz</h1>
        <p style="color:#94a3b8; font-size: 1.2rem; font-weight: 400;">Integrated ESB Smart Meter Analytics</p>
    </div>
''', unsafe_allow_html=True)

all_data = load_all_data()
c_left, c_right = st.columns(2, gap="large")

# --- LEFT COLUMN ---
with c_left:
    # 1. calculated kWh
    st.markdown('<div class="section-title">📊 30-min Consumption (kWh)</div>', unsafe_allow_html=True)
    df1 = all_data[all_data['type'] == "CALC_KWH"].copy()
    
    with st.expander("Upload File"):
        up1 = st.file_uploader("CSV", type="csv", key="u1", label_visibility="collapsed")
        if up1:
            raw = pd.read_csv(up1)
            raw['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'] if 'Read Date and End Time' in raw.columns else raw['Timestamp'], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "CALC_KWH")
            st.rerun()

    if not df1.empty:
        s_vals = settings_df.iloc[0]
        days = max(1, len(df1['timestamp'].dt.date.unique()))
        months = days / 30.44
        total_kwh = df1['value'].sum()
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total", f"{total_kwh:.0f}")
        m2.metric("Daily Avg", f"{total_kwh/days:.1f}")
        m3.metric("Monthly Avg", f"{total_kwh/months:.0f}")
        
        fig1 = px.bar(df1, x='timestamp', y='value', template="plotly_white", color_discrete_sequence=['#00CC96'])
        fig1.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=350)
        st.plotly_chart(fig1, use_container_width=True, config={'displayModeBar': False})

    # 3. Daily Snapshot
    st.markdown('<div style="margin-top:50px;" class="section-title">📅 Daily Snapshot (DNP)</div>', unsafe_allow_html=True)
    df3 = all_data[all_data['type'] == "DNP_SNAPSHOT"].copy()
    if not df3.empty:
        df3 = df3.sort_values('timestamp')
        df3['delta'] = df3['value'].diff()
        df3.loc[(df3['delta'] > 500) | (df3['delta'] < 0), 'delta'] = 0
        fig3 = px.bar(df3, x='timestamp', y='delta', template="plotly_white", color_discrete_sequence=['#636EFA'])
        fig3.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=300)
        st.plotly_chart(fig3, use_container_width=True, config={'displayModeBar': False})

# --- RIGHT COLUMN ---
with c_right:
    # 2. readings kW
    st.markdown('<div class="section-title">📈 30-min Demand (kW)</div>', unsafe_allow_html=True)
    df2 = all_data[all_data['type'] == "READ_KW"].copy()
    
    with st.expander("Upload File"):
        up2 = st.file_uploader("CSV", type="csv", key="u2", label_visibility="collapsed")
        if up2:
            raw = pd.read_csv(up2)
            raw['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'] if 'Read Date and End Time' in raw.columns else raw['Timestamp'], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "READ_KW")
            st.rerun()

    if not df2.empty:
        st.metric("Peak Load", f"{df2['value'].max():.2f} kW")
        fig2 = px.line(df2, x='timestamp', y='value', template="plotly_white", color_discrete_sequence=['#FF4B4B'])
        fig2.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=350)
        st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False})

    # 4. Daily Total
    st.markdown('<div style="margin-top:50px;" class="section-title">📜 Daily Total History</div>', unsafe_allow_html=True)
    df4 = all_data[all_data['type'] == "TOTAL_SNAPSHOT"].copy()
    if not df4.empty:
        df4 = df4.sort_values('timestamp')
        df4['delta'] = df4['value'].diff()
        df4.loc[(df4['delta'] > 500) | (df4['delta'] < 0), 'delta'] = 0
        fig4 = px.area(df4, x='timestamp', y='delta', template="plotly_white", color_discrete_sequence=['#7f8c8d'])
        fig4.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=300)
        st.plotly_chart(fig4, use_container_width=True, config={'displayModeBar': False})

st.caption("Energy Viz | Unified Dashboard")
