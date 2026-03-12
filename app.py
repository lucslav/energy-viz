import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text

# DB Setup
DB_PATH = "/app/data/energy_viz.db"
engine = create_engine(f"sqlite:///{DB_PATH}")

def init_db():
    """Initialize persistent storage."""
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
                timestamp DATETIME PRIMARY KEY,
                value REAL,
                type TEXT
            )
        """))
        conn.commit()

def save_to_db(df, data_type):
    """Upsert data into SQLite."""
    df = df.rename(columns={'Timestamp': 'timestamp', 'Value': 'value'})
    df['type'] = data_type
    df.to_sql('temp_upload', engine, if_exists='replace', index=False)
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT OR REPLACE INTO consumption (timestamp, value, type)
            SELECT timestamp, value, type FROM temp_upload
        """))
        conn.execute(text("DROP TABLE temp_upload"))
        conn.commit()

def get_tariff(dt):
    """Assign tariff based on Irish time bands."""
    h = dt.hour
    if 17 <= h < 19: return 'Peak'
    if 8 <= h < 23: return 'Day'
    return 'Night'

# --- UI Configuration ---
LOGO_URL = "https://raw.githubusercontent.com/lucslav/energy-viz/main/img/logo.png"

st.set_page_config(
    page_title="Energy Viz", 
    page_icon=LOGO_URL, 
    layout="wide"
)
init_db()

# Load Settings
settings_df = pd.read_sql("SELECT * FROM settings WHERE id=1", engine)

# Onboarding if empty
if settings_df.empty:
    st.image(LOGO_URL, width=100)
    st.title("Energy Viz Setup")
    st.info("First run detected. Please enter your rates from your provider's bill.")
    with st.form("init_settings"):
        c1, c2 = st.columns(2)
        with c1:
            dr = st.number_input("Day Rate (€/kWh)", format="%.4f", value=0.3800)
            nr = st.number_input("Night Rate (€/kWh)", format="%.4f", value=0.1500)
            pr = st.number_input("Peak Rate (€/kWh)", format="%.4f", value=0.4200)
        with c2:
            sc = st.number_input("Daily Standing Charge (€/day)", format="%.4f", value=0.6303)
            vt = st.number_input("VAT Rate (%)", value=9.0)
        if st.form_submit_button("Save & Launch"):
            pd.DataFrame([{'id':1,'day_rate':dr,'night_rate':nr,'peak_rate':pr,'standing_charge':sc,'vat_rate':vt}]).to_sql('settings', engine, if_exists='replace', index=False)
            st.rerun()
    st.stop()

s = settings_df.iloc[0]

# --- Sidebar ---
with st.sidebar:
    st.image(LOGO_URL, width=120)
    st.subheader("Current Rates (Incl. VAT)")
    v_mul = 1 + (s['vat_rate'] / 100)
    st.write(f"🟢 **Night:** €{s['night_rate'] * v_mul:.4f}")
    st.write(f"🟡 **Day:** €{s['day_rate'] * v_mul:.4f}")
    st.write(f"🔴 **Peak:** €{s['peak_rate'] * v_mul:.4f}")
    st.write(f"📅 **Standing:** €{s['standing_charge'] * v_mul:.4f}/day")
    
    if st.button("🔄 Change Rates"):
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM settings WHERE id=1"))
            conn.commit()
        st.rerun()

# --- Main App Header ---
col_l, col_r = st.columns([1, 10])
with col_l:
    st.image(LOGO_URL, width=80)
with col_r:
    st.title("Energy Viz")
    st.markdown("### *Interactive ESB Smart Meter Analytics*")

# --- Data Processing ---
data = pd.read_sql("SELECT * FROM consumption ORDER BY timestamp ASC", engine, parse_dates=['timestamp'])

# Upload Section
with st.expander("📤 Add ESB Data (CSV)", expanded=data.empty):
    up = st.file_uploader("Upload CSV", type="csv", label_visibility="collapsed")
    if up:
        raw = pd.read_csv(up)
        if 'Read Date and End Time' in raw.columns:
            df = pd.DataFrame()
            df['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'], dayfirst=True)
            df['Value'] = pd.to_numeric(raw['Read Value'], errors='coerce')
            mode = "Demand" if "Demand" in str(raw.iloc[0]) else "Energy"
            save_to_db(df.dropna(), mode)
            st.success(f"Merged {mode} data into history.")
            st.rerun()

if not data.empty:
    df_energy = data[data['type'] == "Energy"].copy()
    
    if not df_energy.empty:
        df_energy['Tariff'] = df_energy['timestamp'].apply(get_tariff)
        rates = {'Day': s['day_rate'], 'Night': s['night_rate'], 'Peak': s['peak_rate']}
        df_energy['Cost'] = df_energy.apply(lambda x: x['value'] * rates[x['Tariff']], axis=1)
        
        # Calculations
        total_kwh = df_energy['value'].sum()
        days_count = len(df_energy['timestamp'].dt.date.unique())
        energy_net = df_energy['Cost'].sum()
        standing_net = days_count * s['standing_charge']
        total_gross = (energy_net + standing_net) * v_mul
        
        avg_daily_kwh = total_kwh / days_count if days_count > 0 else 0
        avg_daily_cost = total_gross / days_count if days_count > 0 else 0

        # --- Metrics ---
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Usage", f"{total_kwh:.1f} kWh")
        m2.metric("Total Cost (Est.)", f"€{total_gross:.2f}")
        m3.metric("Avg Daily Usage", f"{avg_daily_kwh:.2f} kWh")
        m4.metric("Avg Daily Cost", f"€{avg_daily_cost:.2f}")

        # --- Chart ---
        st.subheader("Usage by Tariff")
        colors = {'Day': '#f1c40f', 'Night': '#2ecc71', 'Peak': '#e74c3c'}
        fig = go.Figure()
        for t in ['Night', 'Day', 'Peak']:
            mask = df_energy[df_energy['Tariff'] == t]
            if not mask.empty:
                fig.add_trace(go.Bar(x=mask['timestamp'], y=mask['value'], name=t, marker_color=colors[t]))
        
        fig.update_layout(barmode='stack', height=450, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)
    
    # Demand Chart
    df_demand = data[data['type'] == "Demand"]
    if not df_demand.empty:
        st.subheader("Power Demand Peaks (kW)")
        fig_kw = go.Figure()
        fig_kw.add_trace(go.Scatter(x=df_demand['timestamp'], y=df_demand['value'], fill='tozeroy', line=dict(color='#3498db')))
        fig_kw.update_layout(height=300, xaxis=dict(rangeslider=dict(visible=True, thickness=0.08)))
        st.plotly_chart(fig_kw, use_container_width=True)

else:
    st.warning("History is empty. Upload your first CSV file to see analysis.")

# --- Footer ---
st.divider()
st.caption(f"Energy Viz v1.1.0 | Database: {len(data)} records")
