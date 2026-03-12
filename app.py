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
    df = df[df['value'] < 100000] # ESB glitch filter
    with engine.begin() as conn:
        df.to_sql('temp_upload', conn, if_exists='replace', index=False)
        conn.execute(text("INSERT OR REPLACE INTO consumption (timestamp, value, type) SELECT timestamp, value, type FROM temp_upload"))
        conn.execute(text("DROP TABLE IF EXISTS temp_upload"))
    st.cache_data.clear()

# --- UI & CSS OVERHAUL ---
st.set_page_config(page_title="Energy Viz", page_icon=LOGO_URL, layout="wide")
init_db()

st.markdown(f"""
    <style>
    /* 1. Background & Global Reset */
    .stApp {{ background-color: #f8fafc !important; }}
    [data-testid="stVerticalBlock"] {{ gap: 0rem !important; }}
    hr {{ display: none !important; }}

    /* 2. Seamless Header */
    .main-header {{
        text-align: center;
        padding: 50px 0px;
        background-color: #ffffff;
        border-radius: 0 0 40px 40px;
        margin-bottom: 30px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }}

    /* 3. Integrated Dashboard Cards */
    .dashboard-card {{
        background-color: #ffffff;
        padding: 25px;
        border-radius: 20px;
        margin: 15px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.04);
    }}

    /* 4. Elegant Section Separators (Vertical Accent) */
    .section-header {{
        font-size: 1.6rem;
        font-weight: 800;
        color: #1e293b;
        margin-bottom: 20px;
        padding-left: 15px;
        border-left: 6px solid #636efa;
        line-height: 1.2;
    }}

    /* 5. Metrics Fix */
    [data-testid="stMetric"] {{
        background-color: #f1f5f9;
        border-radius: 12px;
        padding: 15px;
        border: 1px solid #e2e8f0;
    }}
    
    /* 6. Sidebar Styling */
    [data-testid="stSidebar"] {{
        background-color: #1e293b !important;
    }}
    [data-testid="stSidebar"] * {{
        color: #f8fafc !important;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR & RATES ---
settings_df = pd.read_sql("SELECT * FROM settings WHERE id=1", engine)
v_mul = 1.09 # 9% VAT

with st.sidebar:
    st.image(LOGO_URL, width=100)
    if not settings_df.empty:
        s = settings_df.iloc[0]
        st.markdown("### ⚙️ Unit Rates")
        st.markdown(f"🟢 **Night:** `€{s['night_rate'] * v_mul:.4f}`")
        st.markdown(f"🟡 **Day:** `€{s['day_rate'] * v_mul:.4f}`")
        st.markdown(f"🔴 **Peak:** `€{s['peak_rate'] * v_mul:.4f}`")
        st.markdown(f"📅 **Standing:** `€{s['standing_charge'] * v_mul:.4f}`")
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("Edit Rates", use_container_width=True):
            with engine.begin() as conn: conn.execute(text("DELETE FROM settings WHERE id=1"))
            st.rerun()
        if st.button("Full Reset", use_container_width=True):
            with engine.begin() as conn: conn.execute(text("DELETE FROM consumption"))
            st.cache_data.clear()
            st.rerun()

if settings_df.empty:
    with st.form("setup"):
        c1, c2 = st.columns(2)
        dr = c1.number_input("Day", 0.3397, format="%.4f")
        pr = c1.number_input("Peak", 0.3624, format="%.4f")
        nr = c2.number_input("Night", 0.1785, format="%.4f")
        sc = c2.number_input("Standing", 0.6303, format="%.4f")
        if st.form_submit_button("Start System"):
            pd.DataFrame([{'id':1,'day_rate':dr,'peak_rate':pr,'night_rate':nr,'standing_charge':sc,'vat_rate':9.0}]).to_sql('settings', engine, if_exists='replace', index=False)
            st.rerun()
    st.stop()

# --- HEADER ---
st.markdown(f'''
    <div class="main-header">
        <img src="{LOGO_URL}" width="160">
        <h1 style="font-size: 4rem; margin: 5px 0 0 0; letter-spacing: -3px; color: #0f172a;">Energy Viz</h1>
        <p style="color:#64748b; font-size: 1.2rem; font-weight: 400; letter-spacing: 0.5px;">Integrated ESB Smart Meter Analytics</p>
    </div>
''', unsafe_allow_html=True)

all_data = load_all_data()
col_l, col_r = st.columns(2)

# --- LEFT COLUMN ---
with col_l:
    # BLOCK 1: calculated kWh
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-header">📊 30-min Consumption (kWh)</div>', unsafe_allow_html=True)
    df1 = all_data[all_data['type'] == "CALC_KWH"].copy()
    
    with st.expander("📥 Upload ESB File", expanded=df1.empty):
        up1 = st.file_uploader("Select CSV", type="csv", key="u1", label_visibility="collapsed")
        if up1:
            raw = pd.read_csv(up1)
            raw['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'] if 'Read Date and End Time' in raw.columns else raw['Timestamp'], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "CALC_KWH")
            st.rerun()

    if not df1.empty:
        days = max(1, len(df1['timestamp'].dt.date.unique()))
        total_kwh = df1['value'].sum()
        m1, m2, m3 = st.columns(3)
        m1.metric("Total", f"{total_kwh:.0f} kWh")
        m2.metric("Daily Avg", f"{total_kwh/days:.1f} kWh")
        m3.metric("Records", f"{len(df1)}")
        
        fig1 = px.bar(df1, x='timestamp', y='value', template="plotly_white", color_discrete_sequence=['#00CC96'], labels={'value':'kWh'})
        fig1.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig1, use_container_width=True, config={'scrollZoom': True})
    st.markdown('</div>', unsafe_allow_html=True)

    # BLOCK 3: Daily Snapshot
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-header">📅 Daily Snapshot (DNP)</div>', unsafe_allow_html=True)
    df3 = all_data[all_data['type'] == "DNP_SNAPSHOT"].copy()
    if not df3.empty:
        df3 = df3.sort_values('timestamp')
        df3['delta'] = df3['value'].diff()
        df3.loc[(df3['delta'] > 500) | (df3['delta'] < 0), 'delta'] = 0
        fig3 = px.bar(df3, x='timestamp', y='delta', template="plotly_white", color_discrete_sequence=['#636EFA'], labels={'delta':'Daily kWh'})
        fig3.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig3, use_container_width=True, config={'scrollZoom': True})
    st.markdown('</div>', unsafe_allow_html=True)

# --- RIGHT COLUMN ---
with col_r:
    # BLOCK 2: Readings kW
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-header">📈 30-min Demand (kW)</div>', unsafe_allow_html=True)
    df2 = all_data[all_data['type'] == "READ_KW"].copy()
    
    with st.expander("📥 Upload ESB File", expanded=df2.empty):
        up2 = st.file_uploader("Select CSV", type="csv", key="u2", label_visibility="collapsed")
        if up2:
            raw = pd.read_csv(up2)
            raw['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'] if 'Read Date and End Time' in raw.columns else raw['Timestamp'], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "READ_KW")
            st.rerun()

    if not df2.empty:
        st.metric("Peak Load Detected", f"{df2['value'].max():.2f} kW")
        fig2 = px.line(df2, x='timestamp', y='value', template="plotly_white", color_discrete_sequence=['#FF4B4B'], labels={'value':'kW'})
        fig2.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig2, use_container_width=True, config={'scrollZoom': True})
    st.markdown('</div>', unsafe_allow_html=True)

    # BLOCK 4: Daily Total
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-header">📜 Daily Total History</div>', unsafe_allow_html=True)
    df4 = all_data[all_data['type'] == "TOTAL_SNAPSHOT"].copy()
    if not df4.empty:
        df4 = df4.sort_values('timestamp')
        df4['delta'] = df4['value'].diff()
        df4.loc[(df4['delta'] > 500) | (df4['delta'] < 0), 'delta'] = 0
        fig4 = px.area(df4, x='timestamp', y='delta', template="plotly_white", color_discrete_sequence=['#7f8c8d'], labels={'delta':'Daily kWh'})
        fig4.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig4, use_container_width=True, config={'scrollZoom': True})
    st.markdown('</div>', unsafe_allow_html=True)

st.caption("Energy Viz | Unified ESB Historical Analytics")
