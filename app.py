import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

# --- CONFIGURATION ---
DB_PATH = "/app/data/energy_viz.db"
engine = create_engine(f"sqlite:///{DB_PATH}")
LOGO_URL = "https://raw.githubusercontent.com/lucslav/energy-viz/main/img/logo.png"

def init_db():
    """Initializes tables with a composite primary key."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY, 
                day_rate REAL, night_rate REAL, peak_rate REAL, 
                standing_charge REAL, vat_rate REAL
            )
        """))
        # Composite PK (timestamp, type) is CRITICAL here
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
    """Load everything once and cache it for speed."""
    try:
        return pd.read_sql("SELECT * FROM consumption ORDER BY timestamp ASC", engine, parse_dates=['timestamp'])
    except:
        return pd.DataFrame()

def save_data(df, data_type):
    """Cleanly upsert data and refresh cache."""
    df = df.rename(columns={'Timestamp': 'timestamp', 'Value': 'value'})
    df['type'] = data_type
    df = df[df['value'] < 100000] # Ignore ESB spikes
    
    with engine.begin() as conn:
        df.to_sql('temp_upload', conn, if_exists='replace', index=False)
        conn.execute(text("""
            INSERT OR REPLACE INTO consumption (timestamp, value, type) 
            SELECT timestamp, value, type FROM temp_upload
        """))
        conn.execute(text("DROP TABLE IF EXISTS temp_upload"))
    st.cache_data.clear()

def full_reset():
    """Drop and recreate table to fix schema issues."""
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS consumption"))
    init_db()
    st.cache_data.clear()

# --- UI SETUP ---
st.set_page_config(page_title="Energy Viz", page_icon=LOGO_URL, layout="wide")
init_db()

# Load settings
settings_df = pd.read_sql("SELECT * FROM settings WHERE id=1", engine)
v_mul = 1.09 # 9% VAT

# --- SIDEBAR ---
with st.sidebar:
    st.image(LOGO_URL, width=120)
    if not settings_df.empty:
        s = settings_df.iloc[0]
        st.header("⚙️ Rates (Incl. VAT)")
        st.write(f"🟢 **Night:** €{s['night_rate'] * v_mul:.4f}")
        st.write(f"🟡 **Day:** €{s['day_rate'] * v_mul:.4f}")
        st.write(f"🔴 **Peak:** €{s['peak_rate'] * v_mul:.4f}")
        if st.button("🔄 Edit Rates"):
            with engine.begin() as conn: conn.execute(text("DELETE FROM settings WHERE id=1"))
            st.rerun()
        
        st.divider()
        st.subheader("🗑️ Database Tools")
        if st.button("FULL RESET: Rebuild Database", help="Use this if tabs are not working together"):
            full_reset()
            st.warning("Database rebuilt. Please re-upload files.")
            st.rerun()
    else:
        st.info("Complete setup to see rates.")

# --- MAIN SETUP ---
if settings_df.empty:
    st.header("⚡ Energy Viz Setup")
    with st.form("setup"):
        c1, c2 = st.columns(2)
        with c1:
            dr = st.number_input("Day Rate (€)", value=0.3397, format="%.4f")
            pr = st.number_input("Peak Rate (€)", value=0.3624, format="%.4f")
            nr = st.number_input("Night Rate (€)", value=0.1785, format="%.4f")
        with c2:
            sc = st.number_input("Daily Standing (€)", value=0.6303, format="%.4f")
            st.info("9% VAT will be added automatically.")
        if st.form_submit_button("Save & Launch"):
            pd.DataFrame([{'id':1,'day_rate':dr,'peak_rate':pr,'night_rate':nr,'standing_charge':sc,'vat_rate':9.0}]).to_sql('settings', engine, if_exists='replace', index=False)
            st.rerun()
    st.stop()

# --- APP HEADER ---
st.markdown(f'<div style="text-align:center; padding:15px; background:white; border-radius:15px; border:1px solid #eee; margin-bottom:20px;"><img src="{LOGO_URL}" width="50"><h2>Energy Viz</h2><p style="color:gray; margin:0;">Smart Meter History from NAS</p></div>', unsafe_allow_html=True)

all_data = load_all_data()

# --- TABS ---
tabs = st.tabs([
    "📊 30-min calculated kWh", 
    "📈 30-min readings in kW", 
    "📅 Daily snapshot DNP", 
    "📜 Daily total & export"
])

def render_tab(idx, db_key, esb_name, color, is_pro=False):
    with tabs[idx]:
        df_sub = all_data[all_data['type'] == db_key].copy()
        
        # Browse Button inside expander
        with st.expander(f"📥 Browse & Upload: {esb_name}", expanded=df_sub.empty):
            up = st.file_uploader(f"Select {esb_name}", type="csv", key=f"up_{db_key}")
            if up:
                raw = pd.read_csv(up)
                d_col = 'Read Date and End Time' if 'Read Date and End Time' in raw.columns else 'Timestamp'
                raw['Timestamp'] = pd.to_datetime(raw[d_col], dayfirst=True)
                df_to_save = pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')})
                save_data(df_to_save.dropna(), db_key)
                st.rerun()
        
        if not df_sub.empty:
            st.caption(f"📂 Data found: {df_sub['timestamp'].min().date()} to {df_sub['timestamp'].max().date()} ({len(df_sub)} points)")
            
            if is_pro:
                def get_t(dt):
                    h = dt.hour
                    if 17 <= h < 19: return 'Peak'
                    return 'Night' if (h >= 23 or h < 8) else 'Day'
                
                df_sub['Tariff'] = df_sub['timestamp'].apply(get_t)
                s_vals = settings_df.iloc[0]
                r_map = {'Day': s_vals['day_rate'], 'Night': s_vals['night_rate'], 'Peak': s_vals['peak_rate']}
                df_sub['Cost'] = df_sub.apply(lambda r: r['value'] * r_map[r['Tariff']] * v_mul, axis=1)
                
                days = max(1, len(df_sub['timestamp'].dt.date.unique()))
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total", f"{df_sub['value'].sum():.1f} kWh")
                c2.metric("Bill", f"€{df_sub['Cost'].sum() + (days * s_vals['standing_charge'] * v_mul):.2f}")
                c3.metric("Avg Day", f"{df_sub['value'].sum()/days:.2f} kWh")
                c4.metric("Avg Cost", f"€{(df_sub['Cost'].sum()/days) + (s_vals['standing_charge']*v_mul):.2f}")
                
                view = st.radio("Show:", ["Usage (kWh)", "Cost (€)"], horizontal=True, key=f"radio_{db_key}")
                y_col = 'value' if "Usage" in view else 'Cost'
                fig = px.bar(df_sub.groupby([df_sub['timestamp'].dt.date, 'Tariff'])[y_col].sum().reset_index(), 
                             x='timestamp', y=y_col, color='Tariff', barmode='stack',
                             color_discrete_map={'Day': '#00CC96', 'Night': '#636EFA', 'Peak': '#EF553B'},
                             template="plotly_white")
            else:
                fig = px.line(df_sub, x='timestamp', y='value', line_shape='hv' if db_key=="READ_KW" else None,
                              color_discrete_sequence=[color], template="plotly_white")
            
            fig.update_xaxes(rangeslider_visible=True)
            st.plotly_chart(fig, width="stretch")

# Execute
render_tab(0, "CALC_KWH", "30-minute readings in calculated kWh", "#00CC96", is_pro=True)
render_tab(1, "READ_KW", "30-minute readings in kW", "#FF4B4B")
render_tab(2, "DNP_SNAPSHOT", "Daily snapshot DNP", "#636EFA")
render_tab(3, "TOTAL_SNAPSHOT", "Daily total & export", "#7f8c8d")

st.divider()
st.caption("Energy Viz v1.1.0")
