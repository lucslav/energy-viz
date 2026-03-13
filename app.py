import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

# --- DATABASE SETUP ---
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
    df = df[df['value'] < 100000] # Glitch filter
    with engine.begin() as conn:
        df.to_sql('temp_upload', conn, if_exists='replace', index=False)
        conn.execute(text("INSERT OR REPLACE INTO consumption (timestamp, value, type) SELECT timestamp, value, type FROM temp_upload"))
        conn.execute(text("DROP TABLE IF EXISTS temp_upload"))
    st.cache_data.clear()

# --- CSS: TOTAL WHITE & THIN FONTS ---
st.set_page_config(page_title="Energy Viz", page_icon=LOGO_URL, layout="wide")
init_db()

st.markdown(f"""
    <style>
    /* Global Reset */
    .stApp {{ background-color: #ffffff !important; }}
    [data-testid="stSidebar"] {{ background-color: #ffffff !important; border-right: 1px solid #f1f5f9; }}
    
    /* Font Weight Reduction */
    h1, h2, h3, .section-header {{ font-weight: 400 !important; letter-spacing: -1px; }}
    [data-testid="stMetricValue"] {{ font-weight: 300 !important; font-size: 2rem !important; }}
    [data-testid="stMetricLabel"] {{ font-weight: 400 !important; color: #64748b !important; }}

    /* Seamless Look */
    [data-testid="stMetric"], .stExpander, [data-testid="stVerticalBlock"] > div {{
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
    }}
    
    hr {{ display: none !important; }}
    [data-testid="stVerticalBlock"] {{ gap: 0rem !important; }}

    .section-header {{
        font-size: 1.5rem;
        color: #1e293b;
        margin-top: 40px;
        padding-bottom: 5px;
        border-bottom: 1px solid #f1f5f9;
        margin-bottom: 20px;
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
        st.markdown("### ⚙️ Unit Rates")
        st.write(f"🟢 Night: `€{s['night_rate'] * v_mul:.4f}`")
        st.write(f"🟡 Day: `€{s['day_rate'] * v_mul:.4f}`")
        st.write(f"🔴 Peak: `€{s['peak_rate'] * v_mul:.4f}`")
        st.write(f"📅 Standing: `€{s['standing_charge'] * v_mul:.4f}`")
        if st.button("Edit Rates", use_container_width=True):
            with engine.begin() as conn: conn.execute(text("DELETE FROM settings WHERE id=1"))
            st.rerun()
        if st.button("Reset Data", use_container_width=True):
            with engine.begin() as conn: conn.execute(text("DELETE FROM consumption"))
            st.cache_data.clear()
            st.rerun()

if settings_df.empty:
    with st.form("setup"):
        dr, pr, nr, sc = st.number_input("Day", 0.3397, format="%.4f"), st.number_input("Peak", 0.3624, format="%.4f"), st.number_input("Night", 0.1785, format="%.4f"), st.number_input("Standing Charge", 0.6303, format="%.4f")
        if st.form_submit_button("Initialize"):
            pd.DataFrame([{'id':1,'day_rate':dr,'peak_rate':pr,'night_rate':nr,'standing_charge':sc,'vat_rate':9.0}]).to_sql('settings', engine, if_exists='replace', index=False)
            st.rerun()
    st.stop()

# --- HEADER ---
st.markdown(f'<div style="text-align:center; padding: 30px 0;"><img src="{LOGO_URL}" width="150"><h1 style="font-size: 3rem; margin:0;">Energy Viz</h1><p style="color:#94a3b8; font-size: 1.1rem;">Integrated ESB Smart Meter Analytics</p></div>', unsafe_allow_html=True)

all_data = load_all_data()
col_l, col_r = st.columns(2, gap="large")

# --- LEFT: CONSUMPTION ---
with col_l:
    st.markdown('<div class="section-header">📊 30-min Consumption</div>', unsafe_allow_html=True)
    df1 = all_data[all_data['type'] == "CALC_KWH"].copy()
    
    with st.expander("📥 Browse File", expanded=df1.empty):
        up1 = st.file_uploader("Upload CSV", type="csv", key="u1", label_visibility="collapsed")
        if up1:
            raw = pd.read_csv(up1)
            raw['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'] if 'Read Date and End Time' in raw.columns else raw['Timestamp'], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "CALC_KWH")
            st.rerun()

    if not df1.empty:
        # CALCS
        def get_t(dt):
            h = dt.hour
            if 17 <= h < 19: return 'Peak'
            return 'Night' if (h >= 23 or h < 8) else 'Day'
        df1['Tariff'] = df1['timestamp'].apply(get_t)
        s_v = settings_df.iloc[0]
        r_map = {'Day': s_v['day_rate'], 'Night': s_v['night_rate'], 'Peak': s_v['peak_rate']}
        df1['Cost'] = df1.apply(lambda r: r['value'] * r_map[r['Tariff']] * v_mul, axis=1)
        
        days = max(1, len(df1['timestamp'].dt.date.unique()))
        months = days / 30.44
        tkwh, tcost = df1['value'].sum(), df1['Cost'].sum() + (days * s_v['standing_charge'] * v_mul)

        # ALL 6 METRICS RESTORED
        m1, m2 = st.columns(2)
        m1.metric("Total Usage", f"{tkwh:.1f} kWh")
        m2.metric("Total Cost", f"€{tcost:.2f}")
        m3, m4 = st.columns(2)
        m3.metric("Daily Avg Usage", f"{tkwh/days:.2f} kWh")
        m4.metric("Daily Avg Cost", f"€{tcost/days:.2f}")
        m5, m6 = st.columns(2)
        m5.metric("Monthly Avg Usage", f"{tkwh/months:.1f} kWh")
        m6.metric("Monthly Avg Cost", f"€{tcost/months:.2f}")

        v_opt = st.radio("Metric:", ["kWh", "Euro"], horizontal=True, key="v1")
        y_axis = 'value' if v_opt == "kWh" else 'Cost'
        fig1 = px.bar(df1.groupby([df1['timestamp'].dt.date, 'Tariff'])[y_axis].sum().reset_index(), x='timestamp', y=y_axis, color='Tariff', color_discrete_map={'Day': '#00CC96', 'Night': '#636EFA', 'Peak': '#EF553B'}, barmode='stack', template="plotly_white")
        fig1.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig1, use_container_width=True, config={'scrollZoom': True})

# --- RIGHT: DEMAND ---
with col_r:
    st.markdown('<div class="section-header">📈 30-min Demand (kW)</div>', unsafe_allow_html=True)
    df2 = all_data[all_data['type'] == "READ_KW"].copy()
    if not df2.empty:
        st.metric("Max Peak Load", f"{df2['value'].max():.2f} kW")
        fig2 = px.line(df2, x='timestamp', y='value', line_shape='hv', color_discrete_sequence=['#FF4B4B'], template="plotly_white")
        fig2.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig2, use_container_width=True, config={'scrollZoom': True})

# --- LOWER ROW ---
bl, br = st.columns(2, gap="large")
with bl:
    st.markdown('<div class="section-header">📅 Daily Snapshot (DNP)</div>', unsafe_allow_html=True)
    df3 = all_data[all_data['type'] == "DNP_SNAPSHOT"].copy()
    if not df3.empty:
        df3 = df3.sort_values('timestamp')
        df3['delta'] = df3['value'].diff()
        df3.loc[(df3['delta'] > 500) | (df3['delta'] < 0), 'delta'] = 0
        st.metric("Snapshot Period Usage", f"{df3['delta'].sum():.1f} kWh")
        fig3 = px.bar(df3, x='timestamp', y='delta', template="plotly_white", color_discrete_sequence=['#636EFA'])
        fig3.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig3, use_container_width=True, config={'scrollZoom': True})

with br:
    st.markdown('<div class="section-header">📜 Daily Total History</div>', unsafe_allow_html=True)
    df4 = all_data[all_data['type'] == "TOTAL_SNAPSHOT"].copy()
    if not df4.empty:
        df4 = df4.sort_values('timestamp')
        df4['delta'] = df4['value'].diff() # FIXED NameError
        df4.loc[(df4['delta'] > 500) | (df4['delta'] < 0), 'delta'] = 0
        st.metric("Total Period Usage", f"{df4['delta'].sum():.1f} kWh")
        fig4 = px.area(df4, x='timestamp', y='delta', template="plotly_white", color_discrete_sequence=['#7f8c8d'])
        fig4.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig4, use_container_width=True, config={'scrollZoom': True})
        
