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

# --- HARD CSS RESET ---
st.set_page_config(page_title="Energy Viz", page_icon=LOGO_URL, layout="wide")
init_db()

st.markdown(f"""
    <style>
    /* 1. Global Background - Clean Neutral */
    .stApp {{ background-color: #ffffff !important; }}
    
    /* 2. Kill the "White Rectangles" & Spacers */
    [data-testid="stMetric"], .stExpander, [data-testid="stVerticalBlock"] > div {{
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
    }}
    
    hr {{ display: none !important; }}
    [data-testid="stVerticalBlock"] {{ gap: 0rem !important; }}
    .block-container {{ padding-top: 2rem !important; }}

    /* 3. Tasteful Section Separators */
    .section-header {{
        font-size: 1.8rem;
        font-weight: 800;
        color: #0f172a;
        margin-top: 60px;
        margin-bottom: 20px;
        padding-left: 20px;
        border-left: 6px solid #636efa;
        line-height: 1;
        letter-spacing: -1px;
    }}

    /* 4. Sidebar Overhaul */
    [data-testid="stSidebar"] {{ background-color: #0f172a !important; }}
    [data-testid="stSidebar"] * {{ color: #ffffff !important; }}
    
    /* 5. Metrics Typography */
    [data-testid="stMetricValue"] {{ font-size: 2.2rem !important; font-weight: 900 !important; }}
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR ---
settings_df = pd.read_sql("SELECT * FROM settings WHERE id=1", engine)
v_mul = 1.09 # 9% VAT

with st.sidebar:
    st.image(LOGO_URL, width=110)
    if not settings_df.empty:
        s = settings_df.iloc[0]
        st.header("⚙️ Rates (€)")
        st.write(f"🟢 **Night:** `{s['night_rate'] * v_mul:.4f}`")
        st.write(f"🟡 **Day:** `{s['day_rate'] * v_mul:.4f}`")
        st.write(f"🔴 **Peak:** `{s['peak_rate'] * v_mul:.4f}`")
        st.write(f"📅 **Standing:** `{s['standing_charge'] * v_mul:.4f}`")
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("Edit Rates", use_container_width=True):
            with engine.begin() as conn: conn.execute(text("DELETE FROM settings WHERE id=1"))
            st.rerun()
        if st.button("Clear All Data", use_container_width=True):
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
    <div style="text-align:center; margin-bottom: 40px;">
        <img src="{LOGO_URL}" width="160">
        <h1 style="font-size: 4.2rem; margin: 5px 0 0 0; letter-spacing: -4px; color: #0f172a;">Energy Viz</h1>
        <p style="color:#94a3b8; font-size: 1.3rem; font-weight: 400; letter-spacing: 0.5px;">Integrated ESB Smart Meter Analytics</p>
    </div>
''', unsafe_allow_html=True)

all_data = load_all_data()
col_l, col_r = st.columns(2, gap="large")

# --- LEFT: CONSUMPTION ---
with col_l:
    st.markdown('<div class="section-header">📊 30-min Consumption (kWh)</div>', unsafe_allow_html=True)
    df1 = all_data[all_data['type'] == "CALC_KWH"].copy()
    
    with st.expander("📥 Browse File", expanded=df1.empty):
        up1 = st.file_uploader("Upload", type="csv", key="u1", label_visibility="collapsed")
        if up1:
            raw = pd.read_csv(up1)
            raw['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'] if 'Read Date and End Time' in raw.columns else raw['Timestamp'], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "CALC_KWH")
            st.rerun()

    if not df1.empty:
        days = max(1, len(df1['timestamp'].dt.date.unique()))
        months = days / 30.44
        total_kwh = df1['value'].sum()
        
        m_c1, m_c2, m_c3 = st.columns(3)
        m_c1.metric("Total", f"{total_kwh:.0f} kWh")
        m_c2.metric("Daily Avg", f"{total_kwh/days:.1f} kWh")
        m_c3.metric("Monthly Avg", f"{total_kwh/months:.0f} kWh")
        
        fig1 = px.bar(df1, x='timestamp', y='value', template="plotly_white", color_discrete_sequence=['#00CC96'], labels={'value':'kWh'})
        fig1.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig1, use_container_width=True, config={'scrollZoom': True})

    # 3. Snapshot
    st.markdown('<div class="section-header">📅 Daily Snapshot (DNP)</div>', unsafe_allow_html=True)
    df3 = all_data[all_data['type'] == "DNP_SNAPSHOT"].copy()
    if not df3.empty:
        df3 = df3.sort_values('timestamp')
        df3['delta'] = df3['value'].diff()
        df3.loc[(df3['delta'] > 500) | (df3['delta'] < 0), 'delta'] = 0
        fig3 = px.bar(df3, x='timestamp', y='delta', template="plotly_white", color_discrete_sequence=['#636EFA'], labels={'delta':'kWh'})
        fig3.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig3, use_container_width=True, config={'scrollZoom': True})

# --- RIGHT: DEMAND ---
with col_r:
    st.markdown('<div class="section-header">📈 30-min Demand (kW)</div>', unsafe_allow_html=True)
    df2 = all_data[all_data['type'] == "READ_KW"].copy()
    
    with st.expander("📥 Browse File", expanded=df2.empty):
        up2 = st.file_uploader("Upload", type="csv", key="u2", label_visibility="collapsed")
        if up2:
            raw = pd.read_csv(up2)
            raw['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'] if 'Read Date and End Time' in raw.columns else raw['Timestamp'], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "READ_KW")
            st.rerun()

    if not df2.empty:
        st.metric("Peak Load", f"{df2['value'].max():.2f} kW")
        fig2 = px.line(df2, x='timestamp', y='value', template="plotly_white", color_discrete_sequence=['#FF4B4B'], labels={'value':'kW'})
        fig2.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig2, use_container_width=True, config={'scrollZoom': True})

    # 4. Total
    st.markdown('<div class="section-header">📜 Daily Total History</div>', unsafe_allow_html=True)
    df4 = all_data[all_data['type'] == "TOTAL_SNAPSHOT"].copy()
    if not df4.empty:
        df4 = df4.sort_values('timestamp')
        df4['delta'] = df4['value'].diff()
        df4.loc[(df4['delta'] > 500) | (df4['delta'] < 0), 'delta'] = 0
        fig4 = px.area(df4, x='timestamp', y='delta', template="plotly_white", color_discrete_sequence=['#7f8c8d'], labels={'delta':'kWh'})
        fig4.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig4, use_container_width=True, config={'scrollZoom': True})

st.caption("Energy Viz | Persistent Historical Analytics")
