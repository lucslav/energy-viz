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
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY, 
                day_rate REAL, night_rate REAL, peak_rate REAL, 
                standing_charge REAL, vat_rate REAL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS consumption (
                timestamp DATETIME, 
                value REAL, 
                type TEXT,
                PRIMARY KEY (timestamp, type)
            )
        """))
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
        conn.execute(text("""
            INSERT OR REPLACE INTO consumption (timestamp, value, type) 
            SELECT timestamp, value, type FROM temp_upload
        """))
        conn.execute(text("DROP TABLE IF EXISTS temp_upload"))
    st.cache_data.clear()

# --- UI SETUP & CUSTOM CSS ---
st.set_page_config(page_title="Energy Viz", page_icon=LOGO_URL, layout="wide")
init_db()

st.markdown(f"""
    <style>
    /* Main Background */
    .stApp {{
        background-color: #f4f7f9;
    }}
    /* Metrics Styling */
    [data-testid="stMetric"] {{
        background-color: #ffffff;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #e0e6ed;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.03);
    }}
    /* Header Container */
    .main-header {{
        text-align: center;
        padding: 40px 20px;
        background: linear-gradient(135deg, #ffffff 0%, #eef2f7 100%);
        border-radius: 0 0 30px 30px;
        margin-bottom: 30px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
    }}
    /* Dashboard Cards */
    .dashboard-card {{
        background-color: #ffffff;
        padding: 25px;
        border-radius: 20px;
        border: 1px solid #e6e9ef;
        margin-bottom: 25px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.02);
    }}
    /* Card Titles */
    .card-title {{
        color: #1e293b;
        font-weight: 700;
        border-bottom: 3px solid #636efa;
        display: inline-block;
        margin-bottom: 20px;
        padding-bottom: 5px;
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
        st.divider()
        if st.button("Edit Rates"):
            with engine.begin() as conn: conn.execute(text("DELETE FROM settings WHERE id=1"))
            st.rerun()
        if st.button("Full Reset"):
            with engine.begin() as conn: conn.execute(text("DELETE FROM consumption"))
            st.cache_data.clear()
            st.rerun()

if settings_df.empty:
    st.header("⚡ Setup Energy Viz")
    with st.form("setup"):
        dr = st.number_input("Day Rate", 0.3397, format="%.4f")
        pr = st.number_input("Peak Rate", 0.3624, format="%.4f")
        nr = st.number_input("Night Rate", 0.1785, format="%.4f")
        sc = st.number_input("Standing Charge", 0.6303, format="%.4f")
        if st.form_submit_button("Save & Launch"):
            pd.DataFrame([{'id':1,'day_rate':dr,'peak_rate':pr,'night_rate':nr,'standing_charge':sc,'vat_rate':9.0}]).to_sql('settings', engine, if_exists='replace', index=False)
            st.rerun()
    st.stop()

# --- BRANDED HEADER ---
st.markdown(f'''
    <div class="main-header">
        <img src="{LOGO_URL}" width="180">
        <h1 style="font-size: 3.5rem; margin-top: 15px; margin-bottom: 0px; letter-spacing: -2px; color: #0f172a;">Energy Viz</h1>
        <p style="color:#64748b; font-size: 1.3rem; margin-top: 5px; font-weight: 300;">Comprehensive ESB Smart Meter Analytics</p>
    </div>
''', unsafe_allow_html=True)

all_data = load_all_data()

# --- DASHBOARD GRID ---
col1, col2 = st.columns(2)

# BLOCK 1: 30-min calculated kWh
with col1:
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">📊 30-min Calculated kWh</div>', unsafe_allow_html=True)
    df1 = all_data[all_data['type'] == "CALC_KWH"].copy()
    
    with st.expander("📥 Browse File"):
        up1 = st.file_uploader("Upload CSV", type="csv", key="u1")
        if up1:
            raw = pd.read_csv(up1)
            d_col = 'Read Date and End Time' if 'Read Date and End Time' in raw.columns else 'Timestamp'
            raw['Timestamp'] = pd.to_datetime(raw[d_col], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "CALC_KWH")
            st.rerun()

    if not df1.empty:
        def get_t(dt):
            h = dt.hour
            if 17 <= h < 19: return 'Peak'
            return 'Night' if (h >= 23 or h < 8) else 'Day'
        
        df1['Tariff'] = df1['timestamp'].apply(get_t)
        s_vals = settings_df.iloc[0]
        r_map = {'Day': s_vals['day_rate'], 'Night': s_vals['night_rate'], 'Peak': s_vals['peak_rate']}
        df1['Cost'] = df1.apply(lambda r: r['value'] * r_map[r['Tariff']] * v_mul, axis=1)
        
        days = max(1, len(df1['timestamp'].dt.date.unique()))
        months = days / 30.44
        total_kwh, total_cost = df1['value'].sum(), df1['Cost'].sum() + (days * s_vals['standing_charge'] * v_mul)
        
        m1, m2 = st.columns(2)
        m1.metric("Total Usage", f"{total_kwh:.1f} kWh")
        m2.metric("Total Bill", f"€{total_cost:.2f}")
        
        m3, m4 = st.columns(2)
        m3.metric("Avg Daily Usage", f"{total_kwh/days:.2f} kWh")
        m4.metric("Avg Daily Cost", f"€{total_cost/days:.2f}")

        m5, m6 = st.columns(2)
        m5.metric("Avg Monthly Usage", f"{total_kwh/months:.1f} kWh" if months > 0.1 else "N/A")
        m6.metric("Avg Monthly Cost", f"€{total_cost/months:.2f}" if months > 0.1 else "N/A")
        
        view = st.radio("Display Metric:", ["Usage (kWh)", "Cost (€)"], horizontal=True, key="v1")
        y_val = 'value' if "Usage" in view else 'Cost'
        fig1 = px.bar(df1.groupby([df1['timestamp'].dt.date, 'Tariff'])[y_val].sum().reset_index(), x='timestamp', y=y_val, color='Tariff', color_discrete_map={'Day': '#00CC96', 'Night': '#636EFA', 'Peak': '#EF553B'}, barmode='stack', template="plotly_white", labels={y_val: "kWh" if "Usage" in view else "€"})
        st.plotly_chart(fig1, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# BLOCK 2: 30-min readings in kW
with col2:
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">📈 30-min Readings in kW</div>', unsafe_allow_html=True)
    df2 = all_data[all_data['type'] == "READ_KW"].copy()
    
    with st.expander("📥 Browse File"):
        up2 = st.file_uploader("Upload CSV", type="csv", key="u2")
        if up2:
            raw = pd.read_csv(up2)
            d_col = 'Read Date and End Time' if 'Read Date and End Time' in raw.columns else 'Timestamp'
            raw['Timestamp'] = pd.to_datetime(raw[d_col], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "READ_KW")
            st.rerun()

    if not df2.empty:
        c1, c2 = st.columns(2)
        c1.metric("Peak Load", f"{df2['value'].max():.2f} kW")
        c2.metric("Avg Demand", f"{df2['value'].mean():.2f} kW")
        fig2 = px.line(df2, x='timestamp', y='value', line_shape='hv', color_discrete_sequence=['#FF4B4B'], template="plotly_white", labels={'value': 'kW'})
        st.plotly_chart(fig2, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

col3, col4 = st.columns(2)

# BLOCK 3: Daily Snapshot DNP
with col3:
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">📅 Daily Snapshot DNP</div>', unsafe_allow_html=True)
    df3 = all_data[all_data['type'] == "DNP_SNAPSHOT"].copy()
    
    with st.expander("📥 Browse File"):
        up3 = st.file_uploader("Upload CSV", type="csv", key="u3")
        if up3:
            raw = pd.read_csv(up3)
            d_col = 'Read Date and End Time' if 'Read Date and End Time' in raw.columns else 'Timestamp'
            raw['Timestamp'] = pd.to_datetime(raw[d_col], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "DNP_SNAPSHOT")
            st.rerun()

    if not df3.empty:
        df3 = df3.sort_values('timestamp')
        df3['delta'] = df3['value'].diff()
        df3.loc[(df3['delta'] > 500) | (df3['delta'] < 0), 'delta'] = 0
        
        st.metric("Total Usage (Calculated Delta)", f"{df3['delta'].sum():.1f} kWh")
        fig3 = px.bar(df3, x='timestamp', y='delta', color_discrete_sequence=['#636EFA'], template="plotly_white", labels={'delta': 'Daily kWh'})
        st.plotly_chart(fig3, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# BLOCK 4: Daily Total
with col4:
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">📜 Daily Total & Export</div>', unsafe_allow_html=True)
    df4 = all_data[all_data['type'] == "TOTAL_SNAPSHOT"].copy()
    
    with st.expander("📥 Browse File"):
        up4 = st.file_uploader("Upload CSV", type="csv", key="u4")
        if up4:
            raw = pd.read_csv(up4)
            d_col = 'Read Date and End Time' if 'Read Date and End Time' in raw.columns else 'Timestamp'
            raw['Timestamp'] = pd.to_datetime(raw[d_col], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "TOTAL_SNAPSHOT")
            st.rerun()

    if not df4.empty:
        df4 = df4.sort_values('timestamp')
        df4['delta'] = df4['value'].diff()
        df4.loc[(df4['delta'] > 500) | (df4['delta'] < 0), 'delta'] = 0
        
        st.metric("Total Register Usage", f"{df4['delta'].sum():.1f} kWh")
        fig4 = px.area(df4, x='timestamp', y='delta', color_discrete_sequence=['#7f8c8d'], template="plotly_white", labels={'delta': 'Daily kWh'})
        st.plotly_chart(fig4, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.divider()
st.caption("Energy Viz | Historical Analytics")
        
