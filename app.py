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
    # Spike Filter: Ignore the ESB 9-million kWh error
    df = df[df['value'] < 100000]
    with engine.begin() as conn:
        df.to_sql('temp_upload', conn, if_exists='replace', index=False)
        conn.execute(text("""
            INSERT OR REPLACE INTO consumption (timestamp, value, type) 
            SELECT timestamp, value, type FROM temp_upload
        """))
        conn.execute(text("DROP TABLE IF EXISTS temp_upload"))
    st.cache_data.clear()

# --- UI SETUP ---
st.set_page_config(page_title="Energy Viz", page_icon=LOGO_URL, layout="wide")
init_db()

st.markdown("""
    <style>
    [data-testid="stMetric"] { background-color: rgba(240, 242, 246, 0.4); padding: 10px; border-radius: 10px; border: 1px solid #e6e9ef; }
    .main-header { text-align: center; padding: 20px; }
    .dashboard-card { background-color: #ffffff; padding: 20px; border-radius: 15px; border: 1px solid #eee; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
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
        st.write(f"🟢 **Night:** €{s['night_rate'] * v_mul:.4f}")
        st.write(f"🟡 **Day:** €{s['day_rate'] * v_mul:.4f}")
        st.write(f"🔴 **Peak:** €{s['peak_rate'] * v_mul:.4f}")
        st.divider()
        if st.button("Edit Rates"):
            with engine.begin() as conn: conn.execute(text("DELETE FROM settings WHERE id=1"))
            st.rerun()
        if st.button("Full History Reset"):
            with engine.begin() as conn: conn.execute(text("DELETE FROM consumption"))
            st.cache_data.clear()
            st.rerun()

# Onboarding
if settings_df.empty:
    st.header("⚡ Setup Energy Viz")
    with st.form("setup"):
        dr, pr, nr = st.number_input("Day Rate", 0.3397), st.number_input("Peak Rate", 0.3624), st.number_input("Night Rate", 0.1785)
        sc = st.number_input("Standing Charge", 0.6303)
        if st.form_submit_button("Save & Launch"):
            pd.DataFrame([{'id':1,'day_rate':dr,'peak_rate':pr,'night_rate':nr,'standing_charge':sc,'vat_rate':9.0}]).to_sql('settings', engine, if_exists='replace', index=False)
            st.rerun()
    st.stop()

# --- BRANDED HEADER ---
st.markdown(f'<div class="main-header"><img src="{LOGO_URL}" width="150"><h1 style="font-size: 3rem; margin:0;">Energy Viz</h1><p style="color:gray; font-size: 1.1rem;">Comprehensive ESB Smart Meter Analytics</p></div>', unsafe_allow_html=True)

all_data = load_all_data()

# --- DASHBOARD GRID (2 Rows of 2) ---
col1, col2 = st.columns(2)

# --- BLOCK 1: 30-min calculated kWh (THE PROFESSIONAL TAB) ---
with col1:
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.subheader("📊 30-min Calculated kWh")
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
        df1['Cost'] = df1.apply(lambda r: r['value'] * (s_vals['peak_rate'] if r['Tariff']=='Peak' else (s_vals['night_rate'] if r['Tariff']=='Night' else s_vals['day_rate'])) * v_mul, axis=1)
        
        days = max(1, len(df1['timestamp'].dt.date.unique()))
        months = days / 30.44
        total_kwh, total_cost = df1['value'].sum(), df1['Cost'].sum() + (days * s_vals['standing_charge'] * v_mul)
        
        m1, m2 = st.columns(2)
        m1.metric("Total Usage", f"{total_kwh:.1f} kWh")
        m2.metric("Total Bill", f"€{total_cost:.2f}")
        
        m3, m4 = st.columns(2)
        m3.metric("Avg Monthly Usage", f"{total_kwh/months:.1f} kWh" if months > 0.1 else "N/A")
        m4.metric("Avg Monthly Cost", f"€{total_cost/months:.2f}" if months > 0.1 else "N/A")
        
        view = st.radio("Metric:", ["Usage", "Cost"], horizontal=True, key="v1")
        y_val = 'value' if view == "Usage" else 'Cost'
        fig1 = px.bar(df1.groupby([df1['timestamp'].dt.date, 'Tariff'])[y_val].sum().reset_index(), x='timestamp', y=y_val, color='Tariff', color_discrete_map={'Day': '#00CC96', 'Night': '#636EFA', 'Peak': '#EF553B'}, barmode='stack', template="plotly_white", labels={y_val: "kWh" if view=="Usage" else "€"})
        st.plotly_chart(fig1, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# --- BLOCK 2: 30-min readings in kW (DEMAND) ---
with col2:
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.subheader("📈 30-min Readings in kW")
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

# --- BLOCK 3: Daily Snapshot DNP (REGISTER FIX) ---
with col3:
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.subheader("📅 Daily Snapshot DNP")
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
        # Fixed logic: Calculate difference (usage) from rising register values
        df3 = df3.sort_values('timestamp')
        df3['delta'] = df3['value'].diff()
        df3.loc[(df3['delta'] > 500) | (df3['delta'] < 0), 'delta'] = 0 # Glitch & Reset protection
        
        st.metric("Total Usage (Delta)", f"{df3['delta'].sum():.1f} kWh")
        fig3 = px.bar(df3, x='timestamp', y='delta', color_discrete_sequence=['#636EFA'], template="plotly_white", labels={'delta': 'Daily kWh'})
        st.plotly_chart(fig3, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# --- BLOCK 4: Daily Total (REGISTER FIX) ---
with col4:
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.subheader("📜 Daily Total & Export")
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
        df4.loc[(df4['delta'] > 500) | (df4['delta'] < 0), 'delta'] = 0 # Glitch protection
        
        st.metric("Total Register Usage", f"{df4['delta'].sum():.1f} kWh")
        fig4 = px.area(df4, x='timestamp', y='delta', color_discrete_sequence=['#7f8c8d'], template="plotly_white", labels={'delta': 'Daily kWh'})
        st.plotly_chart(fig4, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.divider()
st.caption("Energy Viz | Historical Analytics")
