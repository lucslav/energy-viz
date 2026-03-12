import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

# --- DB & CONFIG ---
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
    df = df[df['value'] < 100000] # Spike protection
    with engine.begin() as conn:
        df.to_sql('temp_upload', conn, if_exists='replace', index=False)
        conn.execute(text("INSERT OR REPLACE INTO consumption (timestamp, value, type) SELECT timestamp, value, type FROM temp_upload"))
        conn.execute(text("DROP TABLE IF EXISTS temp_upload"))
    st.cache_data.clear()

# --- CUSTOM CSS (Greys & Shading) ---
st.set_page_config(page_title="Energy Viz", page_icon=LOGO_URL, layout="wide")
init_db()

st.markdown(f"""
    <style>
    .stApp {{ background-color: #f8fafc !important; }}
    
    /* Metrics & Cards with Shading */
    [data-testid="stMetric"] {{
        background-color: #ffffff !important;
        padding: 15px !important;
        border-radius: 12px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05) !important;
        border: 1px solid #e2e8f0 !important;
    }}
    
    .dashboard-card {{
        background-color: #ffffff;
        padding: 25px;
        border-radius: 15px;
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.04);
        border: 1px solid #e2e8f0;
    }}

    /* Tasteful Horizontal Separator */
    .h-divider {{
        margin: 40px 0 20px 0;
        border: 0;
        height: 1px;
        background-image: linear-gradient(to right, rgba(0, 0, 0, 0), rgba(0, 0, 0, 0.1), rgba(0, 0, 0, 0));
    }}

    /* Sidebar - Graphite High Contrast */
    [data-testid="stSidebar"] {{ background-color: #27272a !important; }}
    [data-testid="stSidebar"] * {{ color: #ffffff !important; font-weight: 500 !important; }}
    
    /* Clean Headers */
    .section-header {{
        font-size: 1.7rem;
        font-weight: 800;
        color: #18181b;
        margin-bottom: 20px;
    }}
    
    hr {{ display: none !important; }} /* Remove default streamlit lines */
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
        st.write(f"🟢 Night: `€{s['night_rate'] * v_mul:.4f}`")
        st.write(f"🟡 Day: `€{s['day_rate'] * v_mul:.4f}`")
        st.write(f"🔴 Peak: `€{s['peak_rate'] * v_mul:.4f}`")
        st.write(f"📅 Standing: `€{s['standing_charge'] * v_mul:.4f}`")
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Edit Rates", use_container_width=True):
            with engine.begin() as conn: conn.execute(text("DELETE FROM settings WHERE id=1"))
            st.rerun()
        if st.button("Full Reset", use_container_width=True):
            with engine.begin() as conn: conn.execute(text("DELETE FROM consumption"))
            st.cache_data.clear()
            st.rerun()

if settings_df.empty:
    with st.form("setup"):
        dr, pr, nr, sc = st.number_input("Day", 0.3397, format="%.4f"), st.number_input("Peak", 0.3624, format="%.4f"), st.number_input("Night", 0.1785, format="%.4f"), st.number_input("Standing", 0.6303, format="%.4f")
        if st.form_submit_button("Start Dashboard"):
            pd.DataFrame([{'id':1,'day_rate':dr,'peak_rate':pr,'night_rate':nr,'standing_charge':sc,'vat_rate':9.0}]).to_sql('settings', engine, if_exists='replace', index=False)
            st.rerun()
    st.stop()

# --- HEADER ---
st.markdown(f'''
    <div style="text-align:center; padding: 40px 0;">
        <img src="{LOGO_URL}" width="160">
        <h1 style="font-size: 4rem; margin: 10px 0 0 0; letter-spacing: -3px; color: #18181b;">Energy Viz</h1>
        <p style="color:#71717a; font-size: 1.2rem;">Integrated Smart Meter Analytics</p>
    </div>
''', unsafe_allow_html=True)

all_data = load_all_data()
col_left, col_right = st.columns(2, gap="large")

# --- ROW 1 LEFT: 30-min kWh ---
with col_left:
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-header">📊 30-min Consumption (kWh)</div>', unsafe_allow_html=True)
    df1 = all_data[all_data['type'] == "CALC_KWH"].copy()
    
    with st.expander("📥 Browse File", expanded=df1.empty):
        up1 = st.file_uploader("Upload CSV", type="csv", key="u1", label_visibility="collapsed")
        if up1:
            raw = pd.read_csv(up1)
            raw['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'] if 'Read Date and End Time' in raw.columns else raw['Timestamp'], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "CALC_KWH")
            st.rerun()

    if not df1.empty:
        # TARIFF MATH
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
        total_usage = df1['value'].sum()
        total_cost = df1['Cost'].sum() + (days * s_v['standing_charge'] * v_mul)

        m1, m2 = st.columns(2)
        m1.metric("Total Consumption", f"{total_usage:.1f} kWh")
        m2.metric("Total Cost", f"€{total_cost:.2f}")
        
        m3, m4 = st.columns(2)
        m3.metric("Daily Avg Consumption", f"{total_usage/days:.2f} kWh")
        m4.metric("Monthly Avg Cost", f"€{total_cost/months:.2f}" if months > 0.1 else "N/A")

        v_type = st.radio("Switch View:", ["Consumption (kWh)", "Cost (€)"], horizontal=True, key="r1")
        y_col = 'value' if "Consumption" in v_type else 'Cost'
        
        fig1 = px.bar(df1.groupby([df1['timestamp'].dt.date, 'Tariff'])[y_col].sum().reset_index(), x='timestamp', y=y_col, color='Tariff', color_discrete_map={'Day': '#00CC96', 'Night': '#636EFA', 'Peak': '#EF553B'}, barmode='stack', template="plotly_white", labels={y_col: "kWh" if "Consumption" in v_type else "€"})
        fig1.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig1, use_container_width=True, config={'scrollZoom': True})
    st.markdown('</div>', unsafe_allow_html=True)

# --- ROW 1 RIGHT: 30-min kW ---
with col_right:
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-header">📈 30-min Demand (kW)</div>', unsafe_allow_html=True)
    df2 = all_data[all_data['type'] == "READ_KW"].copy()
    
    with st.expander("📥 Browse File", expanded=df2.empty):
        up2 = st.file_uploader("Upload CSV", type="csv", key="u2", label_visibility="collapsed")
        if up2:
            raw = pd.read_csv(up2)
            raw['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'] if 'Read Date and End Time' in raw.columns else raw['Timestamp'], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "READ_KW")
            st.rerun()

    if not df2.empty:
        st.metric("Max Peak Load", f"{df2['value'].max():.2f} kW")
        fig2 = px.line(df2, x='timestamp', y='value', line_shape='hv', color_discrete_sequence=['#FF4B4B'], template="plotly_white", labels={'value': 'kW'})
        fig2.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig2, use_container_width=True, config={'scrollZoom': True})
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="h-divider"></div>', unsafe_allow_html=True)

# --- ROW 2: SNAPSHOTS ---
col_bot_l, col_bot_r = st.columns(2, gap="large")

with col_bot_l:
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-header">📅 Daily Snapshot (DNP)</div>', unsafe_allow_html=True)
    df3 = all_data[all_data['type'] == "DNP_SNAPSHOT"].copy()
    
    with st.expander("📥 Browse File", expanded=df3.empty):
        up3 = st.file_uploader("Upload CSV", type="csv", key="u3", label_visibility="collapsed")
        if up3:
            raw = pd.read_csv(up3)
            raw['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'] if 'Read Date and End Time' in raw.columns else raw['Timestamp'], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "DNP_SNAPSHOT")
            st.rerun()

    if not df3.empty:
        df3 = df3.sort_values('timestamp')
        df3['delta'] = df3['value'].diff()
        df3.loc[(df3['delta'] > 500) | (df3['delta'] < 0), 'delta'] = 0
        st.metric("Total Snapshot Period Usage", f"{df3['delta'].sum():.1f} kWh")
        fig3 = px.bar(df3, x='timestamp', y='delta', color_discrete_sequence=['#636EFA'], template="plotly_white", labels={'delta': 'Daily kWh'})
        fig3.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig3, use_container_width=True, config={'scrollZoom': True})
    st.markdown('</div>', unsafe_allow_html=True)

with col_bot_r:
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-header">📜 Daily Total History</div>', unsafe_allow_html=True)
    df4 = all_data[all_data['type'] == "TOTAL_SNAPSHOT"].copy()
    
    with st.expander("📥 Browse File", expanded=df4.empty):
        up4 = st.file_uploader("Upload CSV", type="csv", key="u4", label_visibility="collapsed")
        if up4:
            raw = pd.read_csv(up4)
            raw['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'] if 'Read Date and End Time' in raw.columns else raw['Timestamp'], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "TOTAL_SNAPSHOT")
            st.rerun()

    if not df4.empty:
        df4 = df4.sort_values('timestamp')
        df4['delta'] = df4['value'].diff() # <--- FIXED: No more NameError
        df4.loc[(df4['delta'] > 500) | (df4['delta'] < 0), 'delta'] = 0
        st.metric("Total Period Consumption", f"{df4['delta'].sum():.1f} kWh")
        fig4 = px.area(df4, x='timestamp', y='delta', color_discrete_sequence=['#7f8c8d'], template="plotly_white", labels={'delta': 'Daily kWh'})
        fig4.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(fig4, use_container_width=True, config={'scrollZoom': True})
    st.markdown('</div>', unsafe_allow_html=True)

st.caption("Energy Viz | Branded Persistent Analytics")
            
