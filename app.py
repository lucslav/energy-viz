import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text

# DB Setup (SQLite on NAS storage)
DB_PATH = "/app/data/energy_viz.db"
engine = create_engine(f"sqlite:///{DB_PATH}")

def init_db():
    """Create tables if they don't exist."""
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
    """Upsert logic: handles ESB data corrections and prevents duplicates."""
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

# --- UI Branding ---
LOGO_URL = "https://raw.githubusercontent.com/lucslav/energy-viz/main/img/logo.png"
st.set_page_config(page_title="Energy Viz", page_icon=LOGO_URL, layout="wide")
init_db()

# Load Rates
settings_df = pd.read_sql("SELECT * FROM settings WHERE id=1", engine)

if settings_df.empty:
    st.image(LOGO_URL, width=100)
    st.title("Energy Viz Setup")
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
v_mul = 1 + (s['vat_rate'] / 100)

# --- Header Section ---
h_col1, h_col2 = st.columns([1, 10])
with h_col1: st.image(LOGO_URL, width=80)
with h_col2:
    st.title("Energy Viz")
    st.markdown("### *Interactive ESB Smart Meter Analytics*")

# --- Database & History ---
data = pd.read_sql("SELECT * FROM consumption ORDER BY timestamp ASC", engine, parse_dates=['timestamp'])

with st.expander("📤 Data Management (Upload History)", expanded=data.empty):
    if not data.empty:
        types_in_db = data['type'].value_counts()
        summary = ", ".join([f"{k}: {v}" for k, v in types_in_db.items()])
        st.write(f"📂 **Active History:** {summary} | From {data['timestamp'].min().date()} to {data['timestamp'].max().date()}")
    
    up = st.file_uploader("Upload ESB CSV File", type="csv", label_visibility="collapsed")
    if up:
        raw = pd.read_csv(up)
        if 'Read Date and End Time' in raw.columns:
            df = pd.DataFrame()
            df['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'], dayfirst=True)
            df['Value'] = pd.to_numeric(raw['Read Value'], errors='coerce')
            
            # Smart 4-Type Detection
            sample = str(raw.iloc[0])
            if "Demand" in sample: m = "Demand"
            elif "Cumulative" in sample: m = "Cumulative"
            elif "DNP" in sample: m = "DNP"
            else: m = "Energy"
            
            save_to_db(df.dropna(), m)
            st.success(f"Merged {m} data into database history.")
            st.rerun()

if not data.empty:
    df_e = data[data['type'] == "Energy"].copy()
    if not df_e.empty:
        # Tariff assignment
        df_e['Tariff'] = df_e['timestamp'].apply(get_tariff)
        rates = {'Day': s['day_rate'], 'Night': s['night_rate'], 'Peak': s['peak_rate']}
        df_e['Cost_Net'] = df_e.apply(lambda x: x['value'] * rates[x['Tariff']], axis=1)
        df_e['Cost_Gross'] = df_e['Cost_Net'] * v_mul
        
        # Summary KPI
        total_kwh = df_e['value'].sum()
        days_count = len(df_e['timestamp'].dt.date.unique())
        energy_net = df_e['Cost_Net'].sum()
        standing_net = days_count * s['standing_charge']
        total_gross = (energy_net + standing_net) * v_mul
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Usage", f"{total_kwh:.1f} kWh")
        m2.metric("Total Bill (Est.)", f"€{total_gross:.2f}")
        m3.metric("Avg Monthly Usage", f"{(total_kwh/days_count)*30.44:.1f} kWh")
        m4.metric("Avg Daily Usage", f"{total_kwh/days_count:.2f} kWh")

        # --- View Toggle & Energy Chart ---
        st.divider()
        view_opt = st.radio("Toggle View:", ["Usage (kWh)", "Cost (€ Incl. VAT)"], horizontal=True)
        col_y = "value" if "Usage" in view_opt else "Cost_Gross"
        lab_y = "Energy (kWh)" if "Usage" in view_opt else "Cost (€)"

        fig = go.Figure()
        cols = {'Day': '#f1c40f', 'Night': '#2ecc71', 'Peak': '#e74c3c'}
        for t in ['Night', 'Day', 'Peak']:
            mask = df_e[df_e['Tariff'] == t]
            if not mask.empty:
                fig.add_trace(go.Bar(x=mask['timestamp'], y=mask[col_y], name=t, marker_color=cols[t]))
        
        fig.update_layout(barmode='stack', height=500, yaxis_title=lab_y,
                          xaxis=dict(rangeslider=dict(visible=True, thickness=0.08)))
        st.plotly_chart(fig, use_container_width=True)

    # Power Demand (kW) Section
    df_d = data[data['type'] == "Demand"]
    if not df_d.empty:
        st.subheader("Peak Demand Trends (kW)")
        fig_kw = go.Figure()
        fig_kw.add_trace(go.Scatter(x=df_d['timestamp'], y=df_d['value'], fill='tozeroy', line=dict(color='#3498db')))
        fig_kw.update_layout(height=350, yaxis_title="Power (kW)",
                             xaxis=dict(rangeslider=dict(visible=True, thickness=0.08)))
        st.plotly_chart(fig_kw, use_container_width=True)

# Sidebar Breakdown & Settings
with st.sidebar:
    st.image(LOGO_URL, width=120)
    st.header("Financial Breakdown")
    if not data[data['type'] == "Energy"].empty:
        st.write(f"**Energy (Net):** €{energy_net:.2f}")
        st.write(f"**Standing Chg:** €{standing_net:.2f}")
        st.write(f"**VAT ({s['vat_rate']}%):** €{total_gross - (energy_net + standing_net):.2f}")
    st.divider()
    st.subheader("Unit Rates")
    st.write(f"🟢 Night: €{s['night_rate'] * v_mul:.4f}")
    st.write(f"🟡 Day: €{s['day_rate'] * v_mul:.4f}")
    st.write(f"🔴 Peak: €{s['peak_rate'] * v_mul:.4f}")
    if st.button("🔄 Edit Settings"):
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM settings WHERE id=1"))
            conn.commit()
        st.rerun()

# --- Footer ---
st.divider()
st.caption(f"Energy Viz v1.1.0 | Database-Powered | Persistent History")
