import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text

# DB setup
DB_PATH = "/app/data/energy_viz.db"
engine = create_engine(f"sqlite:///{DB_PATH}")

def init_db():
    """Initialize tables with Daily Standing Charge."""
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
    """Upsert ESB data to handle corrections."""
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

# UI Config
st.set_page_config(page_title="Energy Viz", page_icon="⚡", layout="wide")
init_db()

# Onboarding / Settings
settings = pd.read_sql("SELECT * FROM settings WHERE id=1", engine)
if settings.empty or st.sidebar.button("⚙️ Setup Rates"):
    st.header("⚡ Energy Rates Configuration")
    with st.form("settings_form"):
        c1, c2 = st.columns(2)
        with c1:
            day_r = st.number_input("Day Rate (€/kWh)", format="%.4f", value=0.3800)
            night_r = st.number_input("Night Rate (€/kWh)", format="%.4f", value=0.1500)
            peak_r = st.number_input("Peak Rate (€/kWh)", format="%.4f", value=0.4200)
        with c2:
            standing_d = st.number_input("Daily Standing Charge (€/day)", format="%.4f", value=0.6303)
            vat_p = st.number_input("VAT Rate (%)", value=9.0)
        if st.form_submit_button("Save & Start"):
            pd.DataFrame([{'id':1,'day_rate':day_r,'night_rate':night_r,'peak_rate':peak_r,'standing_charge':standing_d,'vat_rate':vat_p}]).to_sql('settings', engine, if_exists='replace', index=False)
            st.rerun()
    st.stop()

s = settings.iloc[0]

# File Upload
st.title("⚡ Energy Viz")
uploaded = st.file_uploader("Upload ESB HDF File", type="csv")

if uploaded:
    raw = pd.read_csv(uploaded)
    if 'Read Date and End Time' in raw.columns:
        df = pd.DataFrame()
        df['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'], dayfirst=True)
        df['Value'] = pd.to_numeric(raw['Read Value'], errors='coerce')
        mode = "Demand" if "Demand" in str(raw.iloc[0]) else "Energy"
        save_to_db(df.dropna(), mode)
        st.success(f"Merged records into database ({mode} mode).")

# Load and Filter
data = pd.read_sql("SELECT * FROM consumption ORDER BY timestamp ASC", engine, parse_dates=['timestamp'])

if not data.empty:
    st.sidebar.header("View Mode")
    view = st.sidebar.radio("Analysis Type", ["Cost Analysis (kWh)", "Power Demand (kW)"])
    target_type = "Energy" if view == "Cost Analysis (kWh)" else "Demand"
    filtered = data[data['type'] == target_type].copy()
    
    if not filtered.empty:
        # Charting
        fig = go.Figure()
        if view == "Power Demand (kW)":
            fig.add_trace(go.Scatter(x=filtered['timestamp'], y=filtered['value'], fill='tozeroy', line=dict(color='#FF4B4B')))
            fig.update_layout(xaxis=dict(rangeslider=dict(visible=True, thickness=0.10)), yaxis_title="Demand (kW)")
        else:
            fig.add_trace(go.Bar(x=filtered['timestamp'], y=filtered['value']))
            fig.update_layout(yaxis_title="Energy (kWh)")
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Financial Summary
        if target_type == "Energy":
            st.subheader("Financial Overview (Excluding Tariffs)")
            
            # Calculate days for Standing Charge
            num_days = len(filtered['timestamp'].dt.date.unique())
            total_standing = num_days * s['standing_charge']
            
            # Basic calculation (Single Rate + Standing + VAT)
            raw_energy_cost = filtered['value'].sum() * s['day_rate']
            total_net = raw_energy_cost + total_standing
            total_vat = total_net * (s['vat_rate'] / 100)
            total_gross = total_net + total_vat

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Usage", f"{filtered['value'].sum():.2f} kWh")
            c2.metric("Standing Charge", f"€{total_standing:.2f}", f"{num_days} days")
            c3.metric("VAT ({:.0f}%)".format(s['vat_rate']), f"€{total_vat:.2f}")
            c4.metric("Total Bill (Est.)", f"€{total_gross:.2f}")
    else:
        st.info(f"No {target_type} data found.")
else:
    st.warning("Database empty. Upload CSV to begin.")

st.divider()
st.caption("Energy Viz v1.1.1 | Limerick, IE")
