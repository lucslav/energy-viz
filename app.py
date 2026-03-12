import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

# --- DATABASE CONFIG ---
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
    # Robust filter for ESB data glitches
    df = df[df['value'] < 100000]
    with engine.begin() as conn:
        df.to_sql('temp_upload', conn, if_exists='replace', index=False)
        conn.execute(text("INSERT OR REPLACE INTO consumption (timestamp, value, type) SELECT timestamp, value, type FROM temp_upload"))
        conn.execute(text("DROP TABLE IF EXISTS temp_upload"))
    st.cache_data.clear()

# --- UI & CUSTOM CSS ---
st.set_page_config(page_title="Energy Viz", page_icon=LOGO_URL, layout="wide")
init_db()

st.markdown(f"""
    <style>
    .stApp {{ background-color: #f1f4f8; }}
    [data-testid="stMetric"] {{
        background-color: #ffffff;
        padding: 15px;
        border-radius: 15px;
        border: 1px solid #dee2e6;
    }}
    .dashboard-card {{
        background-color: #ffffff;
        padding: 25px;
        border-radius: 20px;
        margin-bottom: 30px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        border: 1px solid #e9ecef;
    }}
    .card-title {{
        font-size: 1.4rem;
        font-weight: 700;
        color: #1a1c1e;
        margin-bottom: 20px;
        padding-left: 10px;
        border-left: 5px solid #636efa;
    }}
    .main-header {{
        text-align: center;
        padding: 50px 20px;
        background: white;
        border-radius: 0 0 40px 40px;
        margin-bottom: 40px;
        box-shadow: 0 2px 15px rgba(0,0,0,0.05);
    }}
    /* Remove default Streamlit divider lines */
    hr {{ display: none; }}
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR ---
settings_df = pd.read_sql("SELECT * FROM settings WHERE id=1", engine)
v_mul = 1.09 # 9% VAT

with st.sidebar:
    st.image(LOGO_URL, width=120)
    if not settings_df.empty:
        s = settings_df.iloc[0]
        st.header("⚙️ Unit Rates")
        st.markdown(f"🟢 **Night:** `€{s['night_rate'] * v_mul:.4f}`")
        st.markdown(f"🟡 **Day:** `€{s['day_rate'] * v_mul:.4f}`")
        st.markdown(f"🔴 **Peak:** `€{s['peak_rate'] * v_mul:.4f}`")
        st.markdown(f"📅 **Standing:** `€{s['standing_charge'] * v_mul:.4f}`")
        
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("Edit Rates", use_container_width=True):
            with engine.begin() as conn: conn.execute(text("DELETE FROM settings WHERE id=1"))
            st.rerun()
        if st.button("Reset Database", use_container_width=True, type="secondary"):
            with engine.begin() as conn: conn.execute(text("DELETE FROM consumption"))
            st.cache_data.clear()
            st.rerun()

if settings_df.empty:
    st.header("⚡ System Setup")
    with st.form("setup"):
        dr, pr, nr = st.number_input("Day Rate", 0.3397, format="%.4f"), st.number_input("Peak Rate", 0.3624, format="%.4f"), st.number_input("Night Rate", 0.1785, format="%.4f")
        sc = st.number_input("Standing Charge", 0.6303, format="%.4f")
        if st.form_submit_button("Save Rates"):
            pd.DataFrame([{'id':1,'day_rate':dr,'peak_rate':pr,'night_rate':nr,'standing_charge':sc,'vat_rate':9.0}]).to_sql('settings', engine, if_exists='replace', index=False)
            st.rerun()
    st.stop()

# --- HEADER ---
st.markdown(f'''
    <div class="main-header">
        <img src="{LOGO_URL}" width="180">
        <h1 style="font-size: 3.5rem; margin: 10px 0 0 0; letter-spacing: -2px;">Energy Viz</h1>
        <p style="color:#6c757d; font-size: 1.2rem; margin-top: 5px;">Comprehensive ESB Smart Meter Analytics</p>
    </div>
''', unsafe_allow_html=True)

all_data = load_all_data()
col1, col2 = st.columns(2)

# --- BLOCK 1: 30-min kWh ---
with col1:
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">📊 30-min Calculated kWh</div>', unsafe_allow_html=True)
    df = all_data[all_data['type'] == "CALC_KWH"].copy()
    
    with st.expander("📥 Upload ESB File"):
        up = st.file_uploader("Select CSV", type="csv", key="u1")
        if up:
            raw = pd.read_csv(up)
            d_col = 'Read Date and End Time' if 'Read Date and End Time' in raw.columns else 'Timestamp'
            raw['Timestamp'] = pd.to_datetime(raw[d_col], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "CALC_KWH")
            st.rerun()

    if not df.empty:
        def get_t(dt):
            h = dt.hour
            if 17 <= h < 19: return 'Peak'
            return 'Night' if (h >= 23 or h < 8) else 'Day'
        
        df['Tariff'] = df['timestamp'].apply(get_t)
        s_vals = settings_df.iloc[0]
        r_map = {'Day': s_vals['day_rate'], 'Night': s_vals['night_rate'], 'Peak': s_vals['peak_rate']}
        df['Cost'] = df.apply(lambda r: r['value'] * r_map[r['Tariff']] * v_mul, axis=1)
        
        days = max(1, len(df['timestamp'].dt.date.unique()))
        months = days / 30.44
        total_kwh, total_cost = df['value'].sum(), df['Cost'].sum() + (days * s_vals['standing_charge'] * v_mul)
        
        m1, m2 = st.columns(2)
        m1.metric("Total Usage", f"{total_kwh:.1f} kWh")
        m2.metric("Total Bill", f"€{total_cost:.2f}")
        m3, m4 = st.columns(2)
        m3.metric("Avg Daily Usage", f"{total_kwh/days:.2f} kWh")
        m4.metric("Avg Monthly Usage", f"{total_kwh/months:.1f} kWh" if months > 0.1 else "N/A")
        
        v = st.radio("Display Unit:", ["Usage (kWh)", "Cost (€)"], horizontal=True, key="v1")
        y_val = 'value' if "Usage" in v else 'Cost'
        fig = px.bar(df.groupby([df['timestamp'].dt.date, 'Tariff'])[y_val].sum().reset_index(), x='timestamp', y=y_val, color='Tariff', color_discrete_map={'Day': '#00CC96', 'Night': '#636EFA', 'Peak': '#EF553B'}, barmode='stack', template="plotly_white", labels={y_val: "kWh" if "Usage" in v else "€"})
        fig.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig, width="stretch", config={'scrollZoom': True})
    st.markdown('</div>', unsafe_allow_html=True)

# --- BLOCK 2: 30-min kW ---
with col2:
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">📈 30-min Readings in kW</div>', unsafe_allow_html=True)
    df = all_data[all_data['type'] == "READ_KW"].copy()
    
    with st.expander("📥 Upload ESB File"):
        up = st.file_uploader("Select CSV", type="csv", key="u2")
        if up:
            raw = pd.read_csv(up)
            d_col = 'Read Date and End Time' if 'Read Date and End Time' in raw.columns else 'Timestamp'
            raw['Timestamp'] = pd.to_datetime(raw[d_col], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "READ_KW")
            st.rerun()

    if not df.empty:
        st.columns(2)[0].metric("Max Peak Load", f"{df['value'].max():.2f} kW")
        fig = px.line(df, x='timestamp', y='value', line_shape='hv', color_discrete_sequence=['#FF4B4B'], template="plotly_white", labels={'value': 'Demand (kW)'})
        fig.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig, width="stretch", config={'scrollZoom': True})
    st.markdown('</div>', unsafe_allow_html=True)

col3, col4 = st.columns(2)

# --- BLOCK 3: Daily DNP ---
with col3:
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">📅 Daily Snapshot DNP</div>', unsafe_allow_html=True)
    df = all_data[all_data['type'] == "DNP_SNAPSHOT"].copy()
    
    with st.expander("📥 Upload ESB File"):
        up = st.file_uploader("Select CSV", type="csv", key="u3")
        if up:
            raw = pd.read_csv(up)
            d_col = 'Read Date and End Time' if 'Read Date and End Time' in raw.columns else 'Timestamp'
            raw['Timestamp'] = pd.to_datetime(raw[d_col], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "DNP_SNAPSHOT")
            st.rerun()

    if not df.empty:
        df = df.sort_values('timestamp')
        df['delta'] = df['value'].diff()
        df.loc[(df['delta'] > 500) | (df['delta'] < 0), 'delta'] = 0
        st.metric("Total Delta Usage", f"{df['delta'].sum():.1f} kWh")
        fig = px.bar(df, x='timestamp', y='delta', color_discrete_sequence=['#636EFA'], template="plotly_white", labels={'delta': 'kWh/Day'})
        fig.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig, width="stretch", config={'scrollZoom': True})
    st.markdown('</div>', unsafe_allow_html=True)

# --- BLOCK 4: Daily Total ---
with col4:
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">📜 Daily Total History</div>', unsafe_allow_html=True)
    df = all_data[all_data['type'] == "TOTAL_SNAPSHOT"].copy()
    
    with st.expander("📥 Upload ESB File"):
        up = st.file_uploader("Select CSV", type="csv", key="u4")
        if up:
            raw = pd.read_csv(up)
            d_col = 'Read Date and End Time' if 'Read Date and End Time' in raw.columns else 'Timestamp'
            raw['Timestamp'] = pd.to_datetime(raw[d_col], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "TOTAL_SNAPSHOT")
            st.rerun()

    if not df.empty:
        df = df.sort_values('timestamp')
        df['delta'] = df['value'].diff()
        df.loc[(df['delta'] > 500) | (df[(df['delta'] < 0)]), 'delta'] = 0
        st.metric("Total Consumption", f"{df['delta'].sum():.1f} kWh")
        fig = px.area(df, x='timestamp', y='delta', color_discrete_sequence=['#7f8c8d'], template="plotly_white", labels={'delta': 'kWh/Day'})
        fig.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig, width="stretch", config={'scrollZoom': True})
    st.markdown('</div>', unsafe_allow_html=True)

st.caption("Energy Viz | Historical Smart Meter Analytics")
