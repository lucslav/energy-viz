import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text

# DB setup
DB_PATH = "/app/data/energy_viz.db"
engine = create_engine(f"sqlite:///{DB_PATH}")

def init_db():
    """Create tables with primary keys for upserting."""
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
    """Save data using INSERT OR REPLACE to handle ESB corrections."""
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
            day = st.number_input("Day Rate (€/kWh)", format="%.4f", value=0.3500)
            night = st.number_input("Night Rate (€/kWh)", format="%.4f", value=0.1500)
            peak = st.number_input("Peak Rate (€/kWh)", format="%.4f", value=0.4000)
        with c2:
            standing = st.number_input("Annual Standing Charge (€)", value=250.0)
            vat = st.number_input("VAT Rate (%)", value=9.0)
        if st.form_submit_button("Save & Start"):
            pd.DataFrame([{'id':1,'day_rate':day,'night_rate':night,'peak_rate':peak,'standing_charge':standing,'vat_rate':vat}]).to_sql('settings', engine, if_exists='replace', index=False)
            st.rerun()
    st.stop()

s = settings.iloc[0]

# File Upload & Smart Detection
st.title("⚡ Energy Viz")
uploaded = st.file_uploader("Upload ESB HDF File", type="csv")

if uploaded:
    raw = pd.read_csv(uploaded)
    if 'Read Date and End Time' in raw.columns:
        df = pd.DataFrame()
        df['Timestamp'] = pd.to_datetime(raw['Read Date and End Time'], dayfirst=True)
        df['Value'] = pd.to_numeric(raw['Read Value'], errors='coerce')
        
        # Detect mode: kW (Demand) vs kWh (Energy)
        content_sample = str(raw.iloc[0])
        mode = "Demand" if "Demand" in content_sample else "Energy"
        
        save_to_db(df.dropna(), mode)
        st.success(f"Merged {len(df)} records into database ({mode} mode).")

# Load and Filter
data = pd.read_sql("SELECT * FROM consumption ORDER BY timestamp ASC", engine, parse_dates=['timestamp'])

if not data.empty:
    st.sidebar.header("View Mode")
    view = st.sidebar.radio("Analysis Type", ["Cost Analysis (kWh)", "Power Demand (kW)"])
    
    # Filter by selected mode
    target_type = "Energy" if view == "Cost Analysis (kWh)" else "Demand"
    filtered = data[data['type'] == target_type].copy()
    
    if not filtered.empty:
        # Charting
        fig = go.Figure()
        
        if view == "Power Demand (kW)":
            # HV-Line chart for demand spikes
            fig.add_trace(go.Scatter(x=filtered['timestamp'], y=filtered['value'], 
                                     line=dict(color='#FF4B4B', width=2),
                                     fill='tozeroy', name="Load (kW)"))
            
            # --- FIXED RANGE SLIDER GLITCH ---
            fig.update_layout(
                xaxis=dict(
                    rangeslider=dict(visible=True, thickness=0.10), # Explicit thickness
                    type="date"
                ),
                yaxis=dict(title="Demand (kW)", fixedrange=False), # Allow vertical zoom
                height=500,
                margin=dict(l=20, r=20, t=40, b=20)
            )
        else:
            # Cost analysis bar chart
            fig.add_trace(go.Bar(x=filtered['timestamp'], y=filtered['value'], name="Consumption (kWh)"))
            fig.update_layout(height=500, yaxis_title="Energy (kWh)")

        st.plotly_chart(fig, use_container_width=True)
        
        # Quick Stats
        c1, c2, c3 = st.columns(3)
        total_val = filtered['value'].sum()
        unit = "kWh" if target_type == "Energy" else "kW (Max)"
        c1.metric("Total Period Usage", f"{total_val:.2f} {unit}")
        
        if target_type == "Energy":
            # Simple cost estimate (excluding VAT/Standing for now)
            cost = total_val * s['day_rate'] 
            c2.metric("Estimated Cost (Day Rate)", f"€{cost:.2f}")
    else:
        st.info(f"No {target_type} data found. Please upload the correct ESB file.")

else:
    st.warning("Database is empty. Upload a CSV file to begin.")

st.divider()
st.caption("Energy Viz v1.1.0 | Limerick, IE")
