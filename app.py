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
    /* 1. Global App Background */
    .stApp {{ background-color: #f8fafc !important; }}
    
    /* 2. Remove default Streamlit boxes & white rectangles */
    [data-testid="stMetric"], .stExpander, [data-testid="stVerticalBlock"] > div {{
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
    }}
    
    hr {{ display: none !important; }}
    [data-testid="stVerticalBlock"] {{ gap: 0rem !important; }}
    .block-container {{ padding-top: 1.5rem !important; }}

    /* 3. Branded Dashboard Header */
    .main-header {{
        text-align: center;
        padding: 40px 0;
        background-color: white;
        border-radius: 0 0 40px 40px;
        margin-bottom: 30px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }}

    /* 4. Section Titles with Vertical Accent */
    .section-title {{
        font-size: 1.8rem;
        font-weight: 800;
        color: #0f172a;
        margin-top: 40px;
        margin-bottom: 15px;
        padding-left: 15px;
        border-left: 6px solid #636efa;
        letter-spacing: -1px;
    }}

    /* 5. Sidebar - Fixed Visibility (Dark Navy) */
    [data-testid="stSidebar"] {{
        background-color: #0f172a !important;
    }}
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p, 
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{
        color: #ffffff !important;
    }}
    
    /* 6. Metric Styling */
    [data-testid="stMetricValue"] {{
        font-size: 2.2rem !important;
        font-weight: 900 !important;
        color: #1e293b !important;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR ---
settings_df = pd.read_sql("SELECT * FROM settings WHERE id=1", engine)
v_mul = 1.09 # 9% VAT

with st.sidebar:
    st.image(LOGO_URL, width=120)
    if not settings_df.empty:
        s = settings_df.iloc[0]
        st.header("⚙️ Active Rates")
        st.markdown(f"🟢 **Night:** `€{s['night_rate'] * v_mul:.4f}`")
        st.markdown(f"🟡 **Day:** `€{s['day_rate'] * v_mul:.4f}`")
        st.markdown(f"🔴 **Peak:** `€{s['peak_rate'] * v_mul:.4f}`")
        st.markdown(f"📅 **Standing:** `€{s['standing_charge'] * v_mul:.4f}`")
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Edit Rates", use_container_width=True):
            with engine.begin() as conn: conn.execute(text("DELETE FROM settings WHERE id=1"))
            st.rerun()
        if st.button("Reset Data", use_container_width=True):
            with engine.begin() as conn: conn.execute(text("DELETE FROM consumption"))
            st.cache_data.clear()
            st.rerun()

if settings_df.empty:
    with st.form("setup"):
        dr, pr, nr, sc = st.number_input("Day Rate", 0.3397, format="%.4f"), st.number_input("Peak Rate", 0.3624, format="%.4f"), st.number_input("Night Rate", 0.1785, format="%.4f"), st.number_input("Standing Charge", 0.6303, format="%.4f")
        if st.form_submit_button("Start"):
            pd.DataFrame([{'id':1,'day_rate':dr,'peak_rate':pr,'night_rate':nr,'standing_charge':sc,'vat_rate':9.0}]).to_sql('settings', engine, if_exists='replace', index=False)
            st.rerun()
    st.stop()

# --- HEADER ---
st.markdown(f'''
    <div class="main-header">
        <img src="{LOGO_URL}" width="160">
        <h1 style="font-size: 4rem; margin: 5px 0 0 0; letter-spacing: -4px; color: #0f172a;">Energy Viz</h1>
        <p style="color:#94a3b8; font-size: 1.2rem; font-weight: 400; letter-spacing: 0.5px;">Integrated ESB Smart Meter Analytics</p>
    </div>
''', unsafe_allow_html=True)

all_data = load_all_data()
col_left, col_right = st.columns(2, gap="large")

# --- COLUMN LEFT ---
with col_left:
    # BLOCK 1: 30-min Consumption (kWh)
    st.markdown('<div class="section-title">📊 30-min Consumption (kWh)</div>', unsafe_allow_html=True)
    df1 = all_data[all_data['type'] == "CALC_KWH"].copy()
    
    with st.expander("📥 Browse ESB File", expanded=df1.empty):
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
        
        m_c1, m_c2 = st.columns(2)
        m_c1.metric("Total Usage", f"{total_kwh:.1f} kWh")
        m_c2.metric("Daily Avg", f"{total_kwh/days:.2f} kWh")
        
        m_c3, m_c4 = st.columns(2)
        m_c3.metric("Monthly Avg", f"{total_kwh/months:.1f} kWh" if months > 0.1 else "N/A")
        
        fig1 = px.bar(df1.groupby([df1['timestamp'].dt.date])['value'].sum().reset_index(), x='timestamp', y='value', template="plotly_white", color_discrete_sequence=['#00CC96'], labels={'value':'kWh'})
        fig1.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig1, use_container_width=True, config={'scrollZoom': True})

    # BLOCK 3: Daily Snapshot (DNP)
    st.markdown('<div class="section-title">📅 Daily Snapshot (DNP)</div>', unsafe_allow_html=True)
    df3 = all_data[all_data['type'] == "DNP_SNAPSHOT"].copy()
    if not df3.empty:
        df3 = df3.sort_values('timestamp')
        df3['delta'] = df3['value'].diff()
        df3.loc[(df3['delta'] > 500) | (df3['delta'] < 0), 'delta'] = 0
        fig3 = px.bar(df3, x='timestamp', y='delta', template="plotly_white", color_discrete_sequence=['#636EFA'], labels={'delta':'Daily kWh'})
        fig3.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig3, use_container_width=True, config={'scrollZoom': True})

# --- COLUMN RIGHT ---
with col_right:
    # BLOCK 2: 30-min Demand (kW)
    st.markdown('<div class="section-title">📈 30-min Demand (kW)</div>', unsafe_allow_html=True)
    df2 = all_data[all_data['type'] == "READ_KW"].copy()
    
    with st.expander("📥 Browse ESB File", expanded=df2.empty):
        up2 = st.file_uploader("Upload", type="csv", key="u2", label_visibility="collapsed")
        if up2:
            raw = pd.read_csv(up2)
            raw['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'] if 'Read Date and End Time' in raw.columns else raw['Timestamp'], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "READ_KW")
            st.rerun()

    if not df2.empty:
        st.metric("Max Peak Load", f"{df2['value'].max():.2f} kW")
        fig2 = px.line(df2, x='timestamp', y='value', template="plotly_white", color_discrete_sequence=['#FF4B4B'], labels={'value':'kW'})
        fig2.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig2, use_container_width=True, config={'scrollZoom': True})

    # BLOCK 4: Daily Total History
    st.markdown('<div class="section-header" style="font-size: 1.8rem; font-weight: 800; color: #0f172a; margin-top: 40px; margin-bottom: 15px; padding-left: 15px; border-left: 6px solid #636efa; letter-spacing: -1px;">📜 Daily Total History</div>', unsafe_allow_html=True)
    df4 = all_data[all_data['type'] == "TOTAL_SNAPSHOT"].copy()
    if not df4.empty:
        df4 = df4.sort_values('timestamp')
        df4['delta'] = df
        
