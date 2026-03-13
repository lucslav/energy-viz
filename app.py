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
    df = df[df['value'] < 100000] 
    with engine.begin() as conn:
        df.to_sql('temp_upload', conn, if_exists='replace', index=False)
        conn.execute(text("INSERT OR REPLACE INTO consumption (timestamp, value, type) SELECT timestamp, value, type FROM temp_upload"))
        conn.execute(text("DROP TABLE IF EXISTS temp_upload"))
    st.cache_data.clear()

# --- CSS: CLEAN WHITE & THIN FONTS ---
st.set_page_config(page_title="Energy Viz", page_icon=LOGO_URL, layout="wide")
init_db()

st.markdown(f"""
    <style>
    .stApp {{ background-color: #ffffff !important; }}
    [data-testid="stSidebar"] {{ background-color: #ffffff !important; border-right: 1px solid #f1f5f9; }}
    h1, h2, h3, .section-header {{ font-weight: 300 !important; letter-spacing: -1.5px; color: #0f172a; }}
    [data-testid="stMetricValue"] {{ font-weight: 200 !important; font-size: 2.2rem !important; color: #0f172a !important; }}
    [data-testid="stMetricLabel"] {{ font-weight: 400 !important; color: #64748b !important; }}
    [data-testid="stMetric"], .stExpander, [data-testid="stVerticalBlock"] > div {{
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
    }}
    hr {{ display: none !important; }}
    [data-testid="stVerticalBlock"] {{ gap: 0rem !important; }}
    .section-header {{ font-size: 1.6rem; margin-top: 45px; padding-bottom: 5px; border-bottom: 1px solid #f1f5f9; margin-bottom: 5px; }}
    .graph-info {{ color: #94a3b8; font-size: 0.85rem; margin-bottom: 20px; font-style: italic; }}
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR ---
settings_df = pd.read_sql("SELECT * FROM settings WHERE id=1", engine)
v_mul = 1.09 # 9% VAT

with st.sidebar:
    st.image(LOGO_URL, width=120)
    if not settings_df.empty:
        s = settings_df.iloc[0]
        st.markdown("### ⚙️ Rates (Inc. VAT)")
        st.write(f"🟢 Night: `€{s['night_rate'] * v_mul:.4f}`")
        st.write(f"🟡 Day: `€{s['day_rate'] * v_mul:.4f}`")
        st.write(f"🔴 Peak: `€{s['peak_rate'] * v_mul:.4f}`")
        st.write(f"📅 Standing: `€{s['standing_charge'] * v_mul:.4f}`")
        if st.button("Edit Rates", use_container_width=True):
            with engine.begin() as conn: conn.execute(text("DELETE FROM settings WHERE id=1"))
            st.rerun()

    st.markdown("---")
    st.markdown("### 📖 Quick Guide")
    st.caption("**kWh:** Actual energy consumed.")
    st.caption("**kW:** Power demand (how hard you pull energy at once).")

if settings_df.empty:
    with st.form("setup"):
        dr, pr, nr, sc = st.number_input("Day", 0.3397, format="%.4f"), st.number_input("Peak", 0.3624, format="%.4f"), st.number_input("Night", 0.1785, format="%.4f"), st.number_input("Standing", 0.6303, format="%.4f")
        if st.form_submit_button("Start Dashboard"):
            pd.DataFrame([{'id':1,'day_rate':dr,'peak_rate':pr,'night_rate':nr,'standing_charge':sc,'vat_rate':9.0}]).to_sql('settings', engine, if_exists='replace', index=False)
            st.rerun()
    st.stop()

# --- HEADER ---
st.markdown(f'<div style="text-align:center; padding: 30px 0;"><img src="{LOGO_URL}" width="160"><h1>Energy Viz</h1><p style="color:#94a3b8; font-size: 1.1rem; font-weight: 300;">Integrated ESB Smart Meter Analytics</p></div>', unsafe_allow_html=True)

all_data = load_all_data()
cl, cr = st.columns(2, gap="large")

# --- 1. 30-min Consumption ---
with cl:
    st.markdown('<div class="section-header">📊 30-min Consumption Details</div>', unsafe_allow_html=True)
    st.markdown('<div class="graph-info">Source: HDF File. Shows exactly WHEN you used energy in 30-min blocks.</div>', unsafe_allow_html=True)
    df1 = all_data[all_data['type'] == "CALC_KWH"].copy()
    with st.expander("📥 Upload 30-min Usage", expanded=df1.empty):
        up1 = st.file_uploader("Upload", type="csv", key="u1", label_visibility="collapsed")
        if up1:
            raw = pd.read_csv(up1)
            raw['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'] if 'Read Date and End Time' in raw.columns else raw['Timestamp'], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "CALC_KWH")
            st.rerun()
    
    if not df1.empty:
        days = max(1, len(df1['timestamp'].dt.date.unique()))
        def get_t(dt):
            h = dt.hour
            if 17 <= h < 19: return 'Peak'
            return 'Night' if (h >= 23 or h < 8) else 'Day'
        df1['Tariff'] = df1['timestamp'].apply(get_t)
        s_v = settings_df.iloc[0]
        r_map = {'Day': s_v['day_rate'], 'Night': s_v['night_rate'], 'Peak': s_v['peak_rate']}
        df1['Cost'] = df1.apply(lambda r: r['value'] * r_map[r['Tariff']] * v_mul, axis=1)
        
        m1, m2 = st.columns(2); m1.metric("Total Usage", f"{df1['value'].sum():.1f} kWh"); m2.metric("Total Cost", f"€{df1['Cost'].sum() + (days*s_v['standing_charge']*v_mul):.2f}")
        m3, m4 = st.columns(2); m3.metric("Daily Avg", f"{df1['value'].sum()/days:.2f} kWh"); m4.metric("Daily Avg Cost", f"€{(df1['Cost'].sum()/days) + (s_v['standing_charge']*v_mul):.2f}")
        m5, m6 = st.columns(2); m5.metric("Monthly Avg", f"{(df1['value'].sum()/days)*30.44:.0f} kWh"); m6.metric("Monthly Avg Cost", f"€{((df1['Cost'].sum()/days) + (s_v['standing_charge']*v_mul))*30.44:.2f}")
        
        v_opt = st.radio("Display:", ["Usage (kWh)", "Cost (€)"], horizontal=True, key="v1")
        y_col = 'value' if "Usage" in v_opt else 'Cost'
        fig1 = px.bar(df1.groupby([df1['timestamp'].dt.date, 'Tariff'])[y_col].sum().reset_index(), x='timestamp', y=y_col, color='Tariff', color_discrete_map={'Day': '#00CC96', 'Night': '#636EFA', 'Peak': '#EF553B'}, template="plotly_white", labels={y_col: "kWh" if "Usage" in v_opt else "€"})
        fig1.update_xaxes(rangeslider_visible=True); st.plotly_chart(fig1, use_container_width=True, config={'scrollZoom': True})

# --- 2. 30-min Demand ---
with cr:
    st.markdown('<div class="section-header">📈 Peak Power Demand</div>', unsafe_allow_html=True)
    st.markdown('<div class="graph-info">Source: HDF File. Shows how hard your electrical system was loaded (kW).</div>', unsafe_allow_html=True)
    df2 = all_data[all_data['type'] == "READ_KW"].copy()
    with st.expander("📥 Upload 30-min Demand", expanded=df2.empty):
        up2 = st.file_uploader("Upload", type="csv", key="u2", label_visibility="collapsed")
        if up2:
            raw = pd.read_csv(up2)
            raw['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'] if 'Read Date and End Time' in raw.columns else raw['Timestamp'], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "READ_KW")
            st.rerun()
    if not df2.empty:
        st.metric("Peak Recorded Load", f"{df2['value'].max():.2f} kW")
        fig2 = px.line(df2, x='timestamp', y='value', line_shape='hv', color_discrete_sequence=['#FF4B4B'], template="plotly_white", labels={'value': 'Demand (kW)'})
        fig2.update_xaxes(rangeslider_visible=True); st.plotly_chart(fig2, use_container_width=True, config={'scrollZoom': True})

# --- 3. Daily Snapshot ---
bl, br = st.columns(2, gap="large")
with bl:
    st.markdown('<div class="section-header">📅 Daily Usage (DNP Snapshot)</div>', unsafe_allow_html=True)
    st.markdown('<div class="graph-info">Source: DNP Snapshot file. Calculated from meter "Odometer" readings.</div>', unsafe_allow_html=True)
    df3 = all_data[all_data['type'] == "DNP_SNAPSHOT"].copy()
    with st.expander("📥 Upload DNP Snapshot", expanded=df3.empty):
        up3 = st.file_uploader("Upload", type="csv", key="u3", label_visibility="collapsed")
        if up3:
            raw = pd.read_csv(up3)
            raw['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'] if 'Read Date and End Time' in raw.columns else raw['Timestamp'], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "DNP_SNAPSHOT")
            st.rerun()
    if not df3.empty:
        df3 = df3.sort_values('timestamp'); df3['delta'] = df3['value'].diff(); df3.loc[(df3['delta'] > 500) | (df3['delta'] < 0), 'delta'] = 0
        st.metric("Total for this DNP Period", f"{df3['delta'].sum():.1f} kWh")
        fig3 = px.bar(df3, x='timestamp', y='delta', template="plotly_white", color_discrete_sequence=['#636EFA'], labels={'delta': 'Usage (kWh)'})
        fig3.update_xaxes(rangeslider_visible=True); st.plotly_chart(fig3, use_container_width=True, config={'scrollZoom': True})

# --- 4. Daily Total History ---
with br:
    st.markdown('<div class="section-header">📜 Long-term Daily History</div>', unsafe_allow_html=True)
    st.markdown('<div class="graph-info">Source: Total Snapshot file. Best for tracking total trends over months.</div>', unsafe_allow_html=True)
    df4 = all_data[all_data['type'] == "TOTAL_SNAPSHOT"].copy()
    with st.expander("📥 Upload Total History", expanded=df4.empty):
        up4 = st.file_uploader("Upload", type="csv", key="u4", label_visibility="collapsed")
        if up4:
            raw = pd.read_csv(up4)
            raw['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'] if 'Read Date and End Time' in raw.columns else raw['Timestamp'], dayfirst=True)
            save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), "TOTAL_SNAPSHOT")
            st.rerun()
    if not df4.empty:
        df4 = df4.sort_values('timestamp'); df4['delta'] = df4['value'].diff(); df4.loc[(df4['delta'] > 500) | (df4['delta'] < 0), 'delta'] = 0
        st.metric("Total for this History Period", f"{df4['delta'].sum():.1f} kWh")
        fig4 = px.area(df4, x='timestamp', y='delta', template="plotly_white", color_discrete_sequence=['#7f8c8d'], labels={'delta': 'Usage (kWh)'})
        fig4.update_xaxes(rangeslider_visible=True); st.plotly_chart(fig4, use_container_width=True, config={'scrollZoom': True})
        
