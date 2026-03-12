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
    # Spike filter for ESB glitches (ignores the 9M kWh errors)
    df = df[df['value'] < 100000]
    with engine.begin() as conn:
        df.to_sql('temp_upload', conn, if_exists='replace', index=False)
        conn.execute(text("INSERT OR REPLACE INTO consumption (timestamp, value, type) SELECT timestamp, value, type FROM temp_upload"))
        conn.execute(text("DROP TABLE IF EXISTS temp_upload"))
    st.cache_data.clear()

# --- UI SETUP ---
st.set_page_config(page_title="Energy Viz", page_icon=LOGO_URL, layout="wide")
init_db()

settings_df = pd.read_sql("SELECT * FROM settings WHERE id=1", engine)
v_mul = 1.09 # 9% VAT

# --- SIDEBAR ---
with st.sidebar:
    st.image(LOGO_URL, width=120)
    if not settings_df.empty:
        s = settings_df.iloc[0]
        st.header("⚙️ Stawki (z VAT)")
        st.write(f"🟢 **Night:** €{s['night_rate'] * v_mul:.4f}")
        st.write(f"🟡 **Day:** €{s['day_rate'] * v_mul:.4f}")
        st.write(f"🔴 **Peak:** €{s['peak_rate'] * v_mul:.4f}")
        st.write(f"📅 **Opłata stała:** €{s['standing_charge'] * v_mul:.4f}")
        
        st.divider()
        if st.button("🔄 Edytuj stawki"):
            with engine.begin() as conn: conn.execute(text("DELETE FROM settings WHERE id=1"))
            st.rerun()
        if st.button("🗑️ Wyczyść historię"):
            with engine.begin() as conn: conn.execute(text("DELETE FROM consumption"))
            st.cache_data.clear()
            st.rerun()

if settings_df.empty:
    st.header("⚡ Konfiguracja Energy Viz")
    with st.form("setup"):
        dr, pr, nr = st.number_input("Day Rate", 0.3397), st.number_input("Peak Rate", 0.3624), st.number_input("Night Rate", 0.1785)
        sc = st.number_input("Standing Charge", 0.6303)
        if st.form_submit_button("Zapisz i uruchom"):
            pd.DataFrame([{'id':1,'day_rate':dr,'peak_rate':pr,'night_rate':nr,'standing_charge':sc,'vat_rate':9.0}]).to_sql('settings', engine, if_exists='replace', index=False)
            st.rerun()
    st.stop()

# --- HEADER ---
st.markdown(f'<div style="text-align:center;"><img src="{LOGO_URL}" width="50"><h1>Energy Viz v1.1.0</h1></div>', unsafe_allow_html=True)

all_data = load_all_data()

tabs = st.tabs([
    "📊 30-min calculated kWh", 
    "📈 30-min readings in kW", 
    "📅 Daily snapshot DNP", 
    "📜 Daily total"
])

def render_tab(idx, db_key, esb_name, color, mode):
    with tabs[idx]:
        df = all_data[all_data['type'] == db_key].copy()
        
        with st.expander(f"📥 Przeglądaj plik: {esb_name}", expanded=df.empty):
            up = st.file_uploader(f"Wybierz CSV", type="csv", key=f"up_{db_key}")
            if up:
                raw = pd.read_csv(up)
                d_col = 'Read Date and End Time' if 'Read Date and End Time' in raw.columns else 'Timestamp'
                raw['Timestamp'] = pd.to_datetime(raw[d_col], dayfirst=True)
                save_data(pd.DataFrame({'Timestamp': raw['Timestamp'], 'Value': pd.to_numeric(raw['Read Value'], errors='coerce')}).dropna(), db_key)
                st.rerun()

        if not df.empty:
            if mode == "KWH":
                def get_t(dt):
                    h = dt.hour
                    if 17 <= h < 19: return 'Peak'
                    return 'Night' if (h >= 23 or h < 8) else 'Day'
                
                df['Tariff'] = df['timestamp'].apply(get_t)
                s_vals = settings_df.iloc[0]
                r_map = {'Day': s_vals['day_rate'], 'Night': s_vals['night_rate'], 'Peak': s_vals['peak_rate']}
                df['Cost'] = df.apply(lambda r: r['value'] * r_map[r['Tariff']] * v_mul, axis=1)
                
                days = max(1, len(df['timestamp'].dt.date.unique()))
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Łączne zużycie", f"{df['value'].sum():.1f} kWh")
                c2.metric("Suma kosztów", f"€{df['Cost'].sum() + (days * s_vals['standing_charge'] * v_mul):.2f}")
                c3.metric("Średnia doba", f"{df['value'].sum()/days:.2f} kWh")
                c4.metric("Średni koszt doby", f"€{(df['Cost'].sum()/days) + (s_vals['standing_charge']*v_mul):.2f}")
                
                v = st.radio("Widok:", ["Zużycie (kWh)", "Koszt (€)"], horizontal=True, key=f"v_{db_key}")
                y_ax = 'value' if "Zużycie" in v else 'Cost'
                unit = "kWh" if "Zużycie" in v else "€"
                
                daily = df.groupby([df['timestamp'].dt.date, 'Tariff'])[y_ax].sum().reset_index()
                fig = px.bar(daily, x='timestamp', y=y_ax, color='Tariff', 
                             labels={y_ax: unit, 'timestamp': 'Data'},
                             color_discrete_map={'Day': '#00CC96', 'Night': '#636EFA', 'Peak': '#EF553B'}, 
                             barmode='stack', template="plotly_white")
            
            elif mode == "KW":
                c1, c2 = st.columns(2)
                c1.metric("Moc szczytowa (Peak)", f"{df['value'].max():.2f} kW")
                c2.metric("Średnie obciążenie", f"{df['value'].mean():.2f} kW")
                
                fig = px.line(df, x='timestamp', y='value', 
                              labels={'value': 'Moc (kW)', 'timestamp': 'Czas'},
                              line_shape='hv', color_discrete_sequence=[color], template="plotly_white")

            elif mode == "REGISTER":
                df = df.sort_values('timestamp')
                df['daily_usage'] = df['value'].diff().fillna(0)
                df.loc[df['daily_usage'] < 0, 'daily_usage'] = 0 
                
                c1, c2 = st.columns(2)
                c1.metric("Wyliczone zużycie", f"{df['daily_usage'].sum():.1f} kWh")
                c2.metric("Ostatni stan licznika", f"{df['value'].max():.1f}")
                
                fig = px.bar(df, x='timestamp', y='daily_usage', 
                             labels={'daily_usage': 'Zużycie (kWh)', 'timestamp': 'Data'},
                             color_discrete_sequence=[color], template="plotly_white")

            fig.update_xaxes(rangeslider_visible=True)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info(f"Brak danych. Wgraj plik ESB powyżej.")

# Renderowanie zakładek
render_tab(0, "CALC_KWH", "30-minute readings in calculated kWh", "#00CC96", "KWH")
render_tab(1, "READ_KW", "30-minute readings in kW", "#FF4B4B", "KW")
render_tab(2, "DNP_SNAPSHOT", "Daily snapshot of day/night/peak usage", "#636EFA", "REGISTER")
render_tab(3, "TOTAL_SNAPSHOT", "Daily total & export data", "#7f8c8d", "REGISTER")

st.divider()
st.caption("Energy Viz v1.1.0")
