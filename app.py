import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

# --- DATABASE SETUP ---
DB_PATH = "/app/data/energy_viz.db"
engine = create_engine(f"sqlite:///{DB_PATH}")

@st.cache_data
def load_all_data():
    """Fetch all history from DB."""
    try:
        query = "SELECT * FROM consumption ORDER BY timestamp ASC"
        return pd.read_sql(query, engine, parse_dates=['timestamp'])
    except:
        return pd.DataFrame()

def init_db():
    """Initialize DB with composite primary key to allow multiple types."""
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

def save_to_db(df, data_type):
    """Upsert data and refresh cache."""
    df = df.rename(columns={'Timestamp': 'timestamp', 'Value': 'value'})
    df['type'] = data_type
    with engine.begin() as conn:
        df.to_sql('temp_upload', conn, if_exists='replace', index=False)
        conn.execute(text("""
            INSERT OR REPLACE INTO consumption (timestamp, value, type) 
            SELECT timestamp, value, type FROM temp_upload
        """))
        conn.execute(text("DROP TABLE IF EXISTS temp_upload"))
    st.cache_data.clear()

# --- UI SETUP ---
LOGO_URL = "https://raw.githubusercontent.com/lucslav/energy-viz/main/img/logo.png"
st.set_page_config(page_title="Energy Viz", page_icon=LOGO_URL, layout="wide")
init_db()

st.markdown("""
    <style>
    [data-testid="stMetric"] { background-color: rgba(240, 242, 246, 0.4); padding: 15px; border-radius: 12px; }
    .main-header { background-color: #ffffff; padding: 20px; border-radius: 15px; border: 1px solid #e6e9ef; display: flex; align-items: center; justify-content: center; gap: 20px; margin-bottom: 20px; }
    .status-box { background-color: #f8f9fa; padding: 10px; border-radius: 8px; border-left: 5px solid #00CC96; margin-bottom: 20px; font-size: 0.9rem; }
    </style>
    """, unsafe_allow_html=True)

# --- SETTINGS ---
settings_df = pd.read_sql("SELECT * FROM settings WHERE id=1", engine)
if settings_df.empty:
    st.warning("Please configure your rates in the sidebar to begin.")
    with st.sidebar.form("init_settings"):
        dr = st.number_input("Day Rate (€)", value=0.3397, format="%.4f")
        pr = st.number_input("Peak Rate (€)", value=0.3624, format="%.4f")
        nr = st.number_input("Night Rate (€)", value=0.1785, format="%.4f")
        sc = st.number_input("Daily Standing (€)", value=0.6303, format="%.4f")
        if st.form_submit_button("Save Rates"):
            pd.DataFrame([{'id':1,'day_rate':dr,'peak_rate':pr,'night_rate':nr,'standing_charge':sc,'vat_rate':9.0}]).to_sql('settings', engine, if_exists='replace', index=False)
            st.rerun()
    st.stop()

s = settings_df.iloc[0]
v_mul = 1.09

# --- HEADER ---
st.markdown(f'<div class="main-header"><img src="{LOGO_URL}" width="55"><div><h1 style="margin:0;">Energy Viz</h1><p style="margin:0;color:gray;">ESB Smart Meter Analysis</p></div></div>', unsafe_allow_html=True)

full_data = load_all_data()

tabs = st.tabs([
    "📊 30-min calculated kWh", 
    "📈 30-min readings in kW", 
    "📅 Daily snapshot DNP", 
    "📜 Daily total & export"
])

def render_tab(tab_obj, db_key, label, color, is_pro=False):
    with tab_obj:
        # Dedicated uploader per tab
        with st.expander(f"📥 Browse & Upload: {label}", expanded=full_data[full_data['type'] == db_key].empty):
            up = st.file_uploader(f"Select {label} CSV", type="csv", key=f"up_{db_key}")
            if up:
                raw = pd.read_csv(up)
                d_col = 'Read Date and End Time' if 'Read Date and End Time' in raw.columns else 'Timestamp'
                raw['Timestamp'] = pd.to_datetime(raw[d_col], dayfirst=True)
                df_save = pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')})
                save_to_db(df_save.dropna(), db_key)
                st.rerun()
        
        df = full_data[full_data['type'] == db_key].copy()
        if not df.empty:
            st.markdown(f'<div class="status-box">📂 <b>Database Status:</b> Records from <b>{df["timestamp"].min().date()}</b> to <b>{df["timestamp"].max().date()}</b>.</div>', unsafe_allow_html=True)
            
            if is_pro:
                # Tariff & Cost Logic
                def get_t(dt):
                    h = dt.hour
                    if 17 <= h < 19: return 'Peak'
                    return 'Night' if (h >= 23 or h < 8) else 'Day'
                
                df['Tariff'] = df['timestamp'].apply(get_t)
                r_map = {'Day': s['day_rate'], 'Night': s['night_rate'], 'Peak': s['peak_rate']}
                df['Cost'] = df.apply(lambda r: r['value'] * r_map[r['Tariff']] * v_mul, axis=1)
                
                days = max(1, len(df['timestamp'].dt.date.unique()))
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total Usage", f"{df['value'].sum():.1f} kWh")
                c2.metric("Total Cost", f"€{df['Cost'].sum() + (days * s['standing_charge'] * v_mul):.2f}")
                c3.metric("Avg Daily Usage", f"{df['value'].sum()/days:.2f} kWh")
                c4.metric("Avg Daily Cost", f"€{(df['Cost'].sum()/days) + (s['standing_charge']*v_mul):.2f}")
                
                view = st.radio("Metric:", ["kWh", "Cost (€)"], horizontal=True, key="view_pro")
                y_val = 'value' if view == "kWh" else 'Cost'
                fig = px.bar(df.groupby([df['timestamp'].dt.date, 'Tariff'])[y_val].sum().reset_index(), 
                             x='timestamp', y=y_val, color='Tariff', barmode='stack',
                             color_discrete_map={'Day': '#00CC96', 'Night': '#636EFA', 'Peak': '#EF553B'},
                             template="plotly_white")
            else:
                # Line chart for kW, Area for snapshots
                fig = px.line(df, x='timestamp', y='value', line_shape='hv' if db_key=="READ_KW" else None,
                              color_discrete_sequence=[color], template="plotly_white")
            
            fig.update_xaxes(rangeslider_visible=True)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info(f"No data for {label} in database history.")

# Execute Tabs
render_tab(tabs[0], "CALC_KWH", "30-min calculated kWh", "#00CC96", is_pro=True)
render_tab(tabs[1], "READ_KW", "30-min readings in kW", "#FF4B4B")
render_tab(tabs[2], "DNP_SNAPSHOT", "Daily snapshot DNP", "#636EFA")
render_tab(tabs[3], "TOTAL_SNAPSHOT", "Daily total & export", "#7f8c8d")

# --- SIDEBAR ---
with st.sidebar:
    st.image(LOGO_URL, width=120)
    st.divider()
    if st.button("🗑️ Clear All Usage History"):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM consumption"))
        st.cache_data.clear()
        st.rerun()

st.divider()
st.caption("Energy Viz v1.1.0")
