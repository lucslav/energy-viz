"""
Energy Viz — Universal Smart Meter Dashboard
Smart Meter Dashboard — HDF file analysis
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from datetime import timedelta
import base64, re, io, json, os, shutil, hashlib, hmac
from pathlib import Path

# ─────────────────────────────────────────────
#  PERSISTENCE LAYER
#  All user data stored in /app/data (Docker volume).
#  Mount this volume in docker-compose to survive
#  container restarts and image rebuilds.
# ─────────────────────────────────────────────
DATA_DIR   = Path(os.environ.get("ENERGY_VIZ_DATA", "/app/data"))
HDF_DIR    = DATA_DIR / "hdf"
CONFIG_FILE    = DATA_DIR / "config.json"
API_KEY_FILE   = DATA_DIR / "api_key.enc"
INVOICE_FILE   = DATA_DIR / "invoice.pdf"

SYNC_STATUS_FILE = DATA_DIR / "esb_sync.json"
ESB_CREDS_FILE   = DATA_DIR / "esb_creds.enc"

# Create dirs on startup (safe if already exist)
for d in [DATA_DIR, HDF_DIR]:
    d.mkdir(parents=True, exist_ok=True)

HDF_SLOTS = {
    "calc":  HDF_DIR / "calckWh.csv",
    "kw":    HDF_DIR / "kw.csv",
    "dnp":   HDF_DIR / "dnp.csv",
    "daily": HDF_DIR / "daily.csv",
}

# ── Fernet encryption for API key ──────────────────
# Key derived from a fixed app secret + optional MPRN.
# The secret is never stored — derived at runtime only.
def _fernet():
    """Return a Fernet instance. Install cryptography if missing."""
    try:
        from cryptography.fernet import Fernet
        import cryptography
    except ImportError:
        return None
    # Derive a 32-byte key via HMAC-SHA256
    secret = os.environ.get("ENERGY_VIZ_SECRET", "energy-viz-default-secret-change-me")
    key_bytes = hmac.new(secret.encode(), b"energy-viz-api-key", hashlib.sha256).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_api_key(plaintext: str) -> bytes | None:
    f = _fernet()
    if f is None or not plaintext:
        return None
    return f.encrypt(plaintext.encode())


def decrypt_api_key() -> str:
    if not API_KEY_FILE.exists():
        return ""
    f = _fernet()
    if f is None:
        return ""
    try:
        return f.decrypt(API_KEY_FILE.read_bytes()).decode()
    except Exception:
        return ""


# ── Config persistence ─────────────────────────────
_CONFIG_KEYS = [
    "lang", "tariff", "mprn", "supplier",
    "api_provider", "billing_start", "billing_end", "billing_days",
]

def save_config():
    """Persist non-sensitive config to JSON file."""
    data = {}
    for k in _CONFIG_KEYS:
        v = st.session_state.get(k)
        # Dates are not JSON-serialisable — convert to ISO string
        if hasattr(v, "isoformat"):
            v = v.isoformat()
        data[k] = v
    CONFIG_FILE.write_text(json.dumps(data, indent=2))




def encrypt_esb_creds(email: str, password: str) -> bytes | None:
    """Encrypt ESB credentials as JSON using Fernet."""
    f = _fernet()
    if f is None:
        return None
    payload = json.dumps({"email": email, "password": password})
    return f.encrypt(payload.encode())


def decrypt_esb_creds() -> tuple[str, str]:
    """Return (email, password) or ('', '')."""
    if not ESB_CREDS_FILE.exists():
        return "", ""
    f = _fernet()
    if f is None:
        return "", ""
    try:
        data = json.loads(f.decrypt(ESB_CREDS_FILE.read_bytes()).decode())
        return data.get("email", ""), data.get("password", "")
    except Exception:
        return "", ""


def read_sync_status() -> dict:
    """Read last sync status from disk."""
    if not SYNC_STATUS_FILE.exists():
        return {}
    try:
        return json.loads(SYNC_STATUS_FILE.read_text())
    except Exception:
        return {}


def write_sync_status(status: dict):
    """Write sync status to disk."""
    SYNC_STATUS_FILE.write_text(json.dumps(status, indent=2, default=str))

def load_config():
    """Load persisted config into session state (only if not already set)."""
    if not CONFIG_FILE.exists():
        return False
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except Exception:
        return False

    from datetime import date
    for k, v in data.items():
        # lang is always restored from config (overrides default "en")
        if k == "lang":
            if v in ("en", "pl"):
                st.session_state[k] = v
            continue
        if k not in st.session_state or st.session_state[k] in (None, "", [], {}):
            # Restore dates
            if k in ("billing_start", "billing_end") and isinstance(v, str) and v:
                try:
                    v = date.fromisoformat(v)
                except ValueError:
                    v = None
            st.session_state[k] = v
    return True


def save_hdf_file(slot: str, uploaded_file) -> Path:
    """Save uploaded HDF CSV to the data volume and return path."""
    dest = HDF_SLOTS[slot]
    dest.write_bytes(uploaded_file.getvalue())
    return dest


def load_hdf_file(slot: str):
    """Return a file-like object from persisted HDF, or None."""
    path = HDF_SLOTS[slot]
    if path.exists():
        return io.BytesIO(path.read_bytes())
    return None


def save_invoice_pdf(uploaded_file) -> Path:
    """Save uploaded invoice PDF to the data volume."""
    INVOICE_FILE.write_bytes(uploaded_file.getvalue())
    return INVOICE_FILE


def hdf_file_info(slot: str) -> dict | None:
    """Return metadata about a persisted HDF file, or None."""
    path = HDF_SLOTS[slot]
    if not path.exists():
        return None
    stat = path.stat()
    import datetime as dt_mod
    return {
        "path":     str(path),
        "size_kb":  stat.st_size // 1024,
        "modified": dt_mod.datetime.fromtimestamp(stat.st_mtime).strftime("%d %b %Y %H:%M"),
    }

# ─────────────────────────────────────────────
#  PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Energy Viz",
    page_icon="https://raw.githubusercontent.com/lucslav/energy-viz/main/img/logo.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
#  GLOBAL CSS
# ─────────────────────────────────────────────
#  THEME COLORS
# ─────────────────────────────────────────────
_THEME_DARK = dict(
    bg="#161b22", bg2="#1c2330", bg3="#0d1117",
    card="#161b22", card2="#1c2330",
    border="#30363d", border2="#21262d",
    text="#e6edf3", muted="#7d8590", muted2="#a0aab4",
    input_bg="#1c2330", hover_bg="#21262d",
)
_THEME_LIGHT = dict(
    bg="#f6f8fa", bg2="#ffffff", bg3="#eaeef2",
    card="#ffffff", card2="#f0f2f5",
    border="#d0d7de", border2="#d8dee4",
    text="#1f2328", muted="#636c76", muted2="#57606a",
    input_bg="#ffffff", hover_bg="#f3f4f6",
)

def _get_theme():
    """Detect Streamlit theme. Returns 'dark' or 'light'."""
    try:
        base = st.get_option("theme.base")
        return "light" if base == "light" else "dark"
    except Exception:
        return "dark"

def _build_colors():
    """Build COLORS dict — data colors stay consistent, UI colors follow theme."""
    T = _THEME_LIGHT if _get_theme() == "light" else _THEME_DARK
    return dict(
        # Data colors — same in both themes
        day="#388bfd", peak="#e8610a", night="#8250df",
        total="#2da44e", kw="#1b8b93", red="#cf222e",
        yellow="#b08800", green="#2da44e",
        # Aliases
        blue="#388bfd", cyan="#1b8b93", purple="#8250df",
        orange="#e8610a",
        # UI colors — theme-aware
        bg=T["bg"], bg2=T["bg2"], bg3=T["bg3"],
        card=T["card"], card2=T["card2"],
        border=T["border"], border2=T["border2"],
        text=T["text"], muted=T["muted"], muted2=T["muted2"],
        grid=T["border"], input_bg=T["input_bg"],
    ) if _get_theme() == "light" else dict(
        # Data colors — slightly brighter for dark bg
        day="#58a6ff", peak="#f0883e", night="#bc8cff",
        total="#3fb950", kw="#39d0d8", red="#f85149",
        yellow="#d29922", green="#3fb950",
        # Aliases
        blue="#58a6ff", cyan="#39d0d8", purple="#bc8cff",
        orange="#f0883e",
        # UI colors
        bg=T["bg"], bg2=T["bg2"], bg3=T["bg3"],
        card=T["card"], card2=T["card2"],
        border=T["border"], border2=T["border2"],
        text=T["text"], muted=T["muted"], muted2=T["muted2"],
        grid=T["border"], input_bg=T["input_bg"],
    )

COLORS = _build_colors()

# ─────────────────────────────────────────────
#  THEME-AWARE CSS
# ─────────────────────────────────────────────
def _inject_css():
    _theme = _get_theme()
    is_dark = _theme == "dark"
    T = _THEME_DARK if is_dark else _THEME_LIGHT
    C = COLORS

    # Data highlight colors (consistent)
    _day    = C["day"]
    _peak   = C["peak"]
    _night  = C["night"]
    _blue   = C["blue"]

    # Metric background in light mode needs a border
    _metric_bg     = T["card"]
    _metric_border = T["border"]
    _text          = T["text"]
    _muted         = T["muted"]
    _muted2        = T["muted2"]
    _bg            = T["bg"]
    _bg2           = T["bg2"]
    _bg3           = T["bg3"]
    _card          = T["card"]
    _card2         = T["card2"]
    _border        = T["border"]
    _border2       = T["border2"]
    _input_bg      = T["input_bg"]
    _hover_bg      = T["hover_bg"]
    _scrollbar     = T["border"]

    # Alert colors - same in both themes, just background opacity differs
    _alert_info_bg  = "#388bfd18" if not is_dark else "#58a6ff18"
    _alert_warn_bg  = "#e8610a18" if not is_dark else "#f0883e18"
    _alert_good_bg  = "#2da44e18" if not is_dark else "#3fb95018"
    _alert_red_bg   = "#cf222e18" if not is_dark else "#f8514918"
    _alert_info_c   = "#0969da"   if not is_dark else "#58a6ff"
    _alert_warn_c   = "#bc4c00"   if not is_dark else "#f0883e"
    _alert_good_c   = "#1a7f37"   if not is_dark else "#3fb950"
    _alert_red_c    = "#cf222e"   if not is_dark else "#f85149"

    # Gradient title
    _grad_start = "#0969da" if not is_dark else "#58a6ff"
    _grad_end   = "#1b8b93" if not is_dark else "#39d0d8"

    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

html, body, [data-testid="stAppViewContainer"] {{
    background: {_bg} !important;
    color: {_text} !important;
    font-family: 'Space Grotesk', sans-serif !important;
}}
[data-testid="stHeader"]  {{ background: transparent !important; }}
[data-testid="stSidebar"] {{
    background: {_card} !important;
    border-right: 1px solid {_border} !important;
}}
[data-testid="stSidebar"] * {{ color: {_text} !important; }}

/* ── file uploader ── */
section[data-testid="stSidebar"] [data-testid="stFileUploader"],
[data-testid="stFileUploader"] {{
    background: {_card2} !important;
    border: 1px dashed {_border} !important;
    border-radius: 10px !important;
    padding: 6px !important;
}}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"],
[data-testid="stFileUploaderDropzone"] {{
    background: {_card2} !important;
    border: 1px dashed {_border} !important;
    border-radius: 8px !important;
}}
[data-testid="stFileUploader"] *,
[data-testid="stFileUploaderDropzone"] *,
[data-testid="stFileUploaderDropzoneInstructions"] * {{
    color: {_text} !important;
    opacity: 1 !important;
}}
[data-testid="stFileUploaderDropzoneInstructions"] span {{
    color: {_text} !important;
    font-weight: 600 !important;
}}
[data-testid="stFileUploaderDropzoneInstructions"] small,
[data-testid="stFileUploader"] small {{
    color: {_muted} !important;
    opacity: 1 !important;
}}
[data-testid="stFileUploaderDropzone"] button,
[data-testid="stFileUploader"] button {{
    background: {_hover_bg} !important;
    color: {_text} !important;
    border: 1px solid {_border} !important;
    border-radius: 6px !important;
}}

/* ── buttons ── */
.stButton > button {{
    background: linear-gradient(135deg,#1f6feb,#388bfd) !important;
    color:#fff !important; border:none !important;
    border-radius:8px !important;
    font-family:'Space Grotesk',sans-serif !important;
    font-weight:600 !important; padding:.45rem 1.1rem !important;
    transition: opacity .2s !important;
}}
.stButton > button:hover {{ opacity:.85 !important; }}

/* ── metrics ── */
[data-testid="stMetric"] {{
    background:{_metric_bg} !important;
    border:1px solid {_metric_border} !important;
    border-radius:12px !important;
    padding:1rem 1.2rem !important;
}}
[data-testid="stMetricLabel"]  {{ color:{_muted2}!important;font-size:.78rem!important;text-transform:uppercase!important;letter-spacing:.07em!important; }}
[data-testid="stMetricValue"]  {{ font-family:'JetBrains Mono',monospace!important;font-size:1.5rem!important;font-weight:600!important;color:{_text}!important; }}
[data-testid="stMetricDelta"]  {{ font-size:.78rem!important; }}

/* ── tabs ── */
[data-testid="stTabs"] button {{ font-family:'Space Grotesk',sans-serif!important;font-weight:500!important;color:{_muted}!important; }}
[data-testid="stTabs"] button[aria-selected="true"] {{ color:{_blue}!important;border-bottom:2px solid {_blue}!important; }}

hr {{ border-color:{_border}!important; }}

/* ── section headers ── */
.sec {{ display:flex;align-items:center;gap:10px;padding:.5rem 0 .4rem;border-bottom:1px solid {_border};margin-bottom:1rem; }}
.sec .icon  {{ font-size:1.2rem; }}
.sec .title {{ font-size:1.05rem;font-weight:600;color:{_text};margin:0; }}
.sec .badge {{ font-size:.68rem;font-weight:600;padding:2px 8px;border-radius:20px;background:{_card2};color:{_muted};margin-left:auto;border:1px solid {_border}; }}

/* ── KPI cards ── */
.kpi-row  {{ display:flex;gap:10px;margin-bottom:1rem;flex-wrap:wrap; }}
.kpi-card {{ flex:1;min-width:130px;background:{_card};border:1px solid {_border};border-radius:12px;padding:1rem 1.1rem;position:relative;overflow:hidden; }}
.kpi-card::before {{ content:'';position:absolute;top:0;left:0;right:0;height:3px; }}
.kpi-card.blue::before   {{ background:linear-gradient(90deg,#388bfd,#1b8b93); }}
.kpi-card.green::before  {{ background:linear-gradient(90deg,#2da44e,#1a7f37); }}
.kpi-card.orange::before {{ background:linear-gradient(90deg,#e8610a,#b08800); }}
.kpi-card.purple::before {{ background:linear-gradient(90deg,#8250df,#388bfd); }}
.kpi-card.red::before    {{ background:linear-gradient(90deg,#cf222e,#e8610a); }}
.kpi-card.cyan::before   {{ background:linear-gradient(90deg,#1b8b93,#2da44e); }}
.kpi-label {{ font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:{_muted2};margin-bottom:3px; }}
.kpi-value {{ font-family:'JetBrains Mono',monospace;font-size:1.45rem;font-weight:600;color:{_text};line-height:1.2; }}
.kpi-sub   {{ font-size:.76rem;color:{_muted2};margin-top:3px; }}

/* ── alert boxes ── */
.alert-box {{ border-radius:10px;padding:.75rem 1rem;border-left:3px solid;margin:.5rem 0;font-size:.86rem; }}
.alert-info  {{ background:{_alert_info_bg};border-color:{_alert_info_c};color:{_alert_info_c}; }}
.alert-warn  {{ background:{_alert_warn_bg};border-color:{_alert_warn_c};color:{_alert_warn_c}; }}
.alert-good  {{ background:{_alert_good_bg};border-color:{_alert_good_c};color:{_alert_good_c}; }}
.alert-red   {{ background:{_alert_red_bg};border-color:{_alert_red_c};color:{_alert_red_c}; }}

/* ── radio buttons ── */
[data-testid="stRadio"] label,
[data-testid="stRadio"] label *,
div[role="radiogroup"] label,
div[role="radiogroup"] label p {{
    color: {_text} !important;
    font-size: .88rem !important;
    opacity: 1 !important;
}}
[data-testid="stRadio"] label:has(input:checked),
[data-testid="stRadio"] label:has(input:checked) p {{
    color: {_blue} !important;
    font-weight: 600 !important;
}}
[data-testid="stRadio"] input[type="radio"] {{ accent-color: {_blue} !important; }}

/* ── inputs ── */
[data-testid="stSelectbox"] label, [data-testid="stTextInput"] label,
[data-testid="stNumberInput"] label, [data-testid="stDateInput"] label,
[data-testid="stSelectbox"] label *, [data-testid="stTextInput"] label *,
[data-testid="stNumberInput"] label *, [data-testid="stDateInput"] label * {{
    color: {_text} !important; opacity: 1 !important;
}}
[data-testid="stSelectbox"] > div > div,
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input,
[data-testid="stTextArea"] textarea {{
    background: {_input_bg} !important;
    border-color: {_border} !important;
    color: {_text} !important;
}}
[data-testid="stTextInput"] input::placeholder {{ color: {_muted} !important; opacity: 1 !important; }}
[data-testid="stNumberInput"] button {{
    background: {_hover_bg} !important;
    color: {_text} !important;
    border-color: {_border} !important;
}}
[data-testid="stSelectbox"] * {{ color: {_text} !important; }}

/* ── expander ── */
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary * {{ color: {_text} !important; }}
[data-testid="stExpander"] {{
    border-color: {_border} !important;
    background: {_card} !important;
}}

/* ── sliders / toggles ── */
[data-testid="stSlider"] label, [data-testid="stSlider"] label *, [data-testid="stSlider"] p,
[data-testid="stToggle"] label, [data-testid="stToggle"] label *,
[data-testid="stCheckbox"] label, [data-testid="stCheckbox"] label * {{
    color: {_text} !important; opacity: 1 !important;
}}

/* ── global ── */
p, label, span {{ opacity: 1 !important; }}
.stMarkdown p {{ color: {_text} !important; }}
div[class*="stRadio"] > label > div > p {{ color: {_text} !important; }}

/* ── form submit ── */
[data-testid="stFormSubmitButton"] button {{
    background: linear-gradient(135deg, #1f6feb, #388bfd) !important;
    color: #ffffff !important; border: none !important;
    border-radius: 8px !important; font-weight: 600 !important;
    padding: .45rem 1.1rem !important; min-width: 160px !important;
}}
[data-testid="stFormSubmitButton"] button p,
[data-testid="stFormSubmitButton"] button span {{ color: #ffffff !important; }}

/* ── setup card ── */
.setup-card {{
    background:{_card};border:1px solid {_border};border-radius:16px;
    padding:2rem;max-width:640px;margin:2rem auto;
}}
.step-num {{ width:24px;height:24px;border-radius:50%;background:{_blue};color:#fff;
            font-size:.75rem;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:2px; }}

/* ── header logo ── */
.app-header {{ display:flex;align-items:center;gap:14px;padding:.8rem 0 .4rem; }}
.app-header img {{ height:42px;width:auto; }}
.app-header .titles h1 {{ margin:0;font-size:1.6rem;font-weight:700;
    background:linear-gradient(90deg,{_grad_start},{_grad_end});
    -webkit-background-clip:text;-webkit-text-fill-color:transparent; }}
.app-header .titles p  {{ margin:0;color:{_muted};font-size:.84rem; }}

/* ── sidebar logo ── */
.sb-logo {{ display:flex;align-items:center;gap:10px;padding:.5rem 0 1rem;border-bottom:1px solid {_border};margin-bottom:1rem; }}
.sb-logo img {{ height:36px;width:auto; }}
.sb-logo .lname {{ font-size:1.1rem;font-weight:700;color:{_text}; }}
.sb-logo .lsub  {{ font-size:.7rem;color:{_muted}; }}

/* ── tariff row ── */
.tariff-row {{ display:flex;align-items:center;gap:8px;font-size:.78rem;padding:3px 0; }}
.tariff-dot {{ width:8px;height:8px;border-radius:50%;flex-shrink:0; }}

/* ── mobile ── */
@media (max-width: 640px) {{
    .kpi-card {{ min-width:calc(50% - 5px) !important; }}
    .app-header img {{ height:32px; }}
    .app-header .titles h1 {{ font-size:1.2rem; }}
}}

[data-testid="stDataFrame"] {{ background:{_card}!important;border-radius:10px!important; }}
::-webkit-scrollbar {{ width:6px;height:6px; }}
::-webkit-scrollbar-track {{ background:{_bg}; }}
::-webkit-scrollbar-thumb {{ background:{_scrollbar};border-radius:3px; }}
.stApp {{ background:{_bg}!important; }}

</style>
""", unsafe_allow_html=True)

_inject_css()

# ─────────────────────────────────────────────
#  CONSTANTS  (defaults — overridden by user)
# ─────────────────────────────────────────────
DEFAULT_TARIFF = dict(day=0.3397, peak=0.3624, night=0.1785, standing=0.6303)
VAT_RATE       = 0.09
DISCOUNT       = 0.30
LOGO_URL       = "https://raw.githubusercontent.com/lucslav/energy-viz/main/img/logo.png"

# ── Theme-aware color palettes ──

def _rgba(hex_color: str, alpha: float = 0.15) -> str:
    """Convert #rrggbb hex to rgba() string for Plotly fillcolor."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def fmt_date(dt, fmt="%d %b %Y") -> str:
    """Format date with localised month name."""
    s = dt.strftime(fmt)
    lang = st.session_state.get("lang", "en")
    if lang == "pl":
        months_en = TRANSLATIONS["months_short"]["en"]
        months_pl = TRANSLATIONS["months_short"]["pl"]
        for en, pl in zip(months_en, months_pl):
            s = s.replace(en, pl)
    return s


# ─────────────────────────────────────────────
#  TRANSLATIONS
# ─────────────────────────────────────────────
TRANSLATIONS = {
    # ── Month names ──
    "months_short": {
        "en": ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
        "pl": ["sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paź","lis","gru"],
    },
    "months_long": {
        "en": ["January","February","March","April","May","June","July","August","September","October","November","December"],
        "pl": ["Styczeń","Luty","Marzec","Kwiecień","Maj","Czerwiec","Lipiec","Sierpień","Wrzesień","Październik","Listopad","Grudzień"],
    },
    # ── App shell ──
    "app_title":            {"en": "Smart Meter Dashboard",       "pl": "Panel Licznika"},
    "app_subtitle":         {"en": "Smart Meter HDF Analysis",    "pl": "Analiza plików HDF"},
    "first_run_title":      {"en": "First Run Setup",             "pl": "Pierwsze uruchomienie"},
    "welcome_title":        {"en": "Welcome! Let's configure your tariff.", "pl": "Witaj! Skonfigurujmy Twoją taryfę."},
    "welcome_sub":          {"en": "Your settings will be saved to", "pl": "Ustawienia zostaną zapisane w"},
    "persist_tariff":       {"en": "Tariff rates — persisted",    "pl": "Taryfa — zapisana"},
    "persist_hdf":          {"en": "HDF files — persisted",       "pl": "Pliki HDF — zapisane"},
    "persist_invoice":      {"en": "Invoice PDF — persisted",     "pl": "Faktura PDF — zapisana"},
    "persist_api":          {"en": "API key — your choice",       "pl": "Klucz API — Twój wybór"},
    "how_tariff":           {"en": "How would you like to enter your tariff?", "pl": "Jak chcesz wprowadzić taryfę?"},
    "upload_pdf_opt":       {"en": "📄 Upload invoice PDF (auto-extract)", "pl": "📄 Wgraj fakturę PDF (auto-odczyt)"},
    "manual_opt":           {"en": "✏️ Enter rates manually",     "pl": "✏️ Wprowadź stawki ręcznie"},
    # ── Sidebar ──
    "hdf_files":            {"en": "HDF Files",                   "pl": "Pliki HDF"},
    "primary":              {"en": "PRIMARY",                     "pl": "GŁÓWNY"},
    "optional":             {"en": "optional",                    "pl": "opcjonalny"},
    "not_loaded":           {"en": "not loaded",                  "pl": "nie załadowany"},
    "just_uploaded":        {"en": "just uploaded",               "pl": "właśnie wgrany"},
    "saved_session":        {"en": "saved from previous session", "pl": "zapisany z poprzedniej sesji"},
    "not_available":        {"en": "not available",               "pl": "niedostępny"},
    "tariff_rates":         {"en": "Tariff Rates (€/kWh)",        "pl": "Stawki taryfy (€/kWh)"},
    "day_rate":             {"en": "Day",                         "pl": "Dzień"},
    "peak_rate":            {"en": "Peak",                        "pl": "Szczyt"},
    "night_rate":           {"en": "Night",                       "pl": "Noc"},
    "standing_rate":        {"en": "Standing €/d",                "pl": "Opłata stała €/d"},
    "configuration":        {"en": "Configuration",               "pl": "Konfiguracja"},
    "reparse_btn":          {"en": "Change rates / Re-parse",     "pl": "Zmień stawki / Przebuduj"},
    "clear_btn":            {"en": "Clear all saved data",        "pl": "Wyczyść wszystkie dane"},
    "tariff_split":         {"en": "TARIFF SPLIT",                "pl": "PODZIAŁ TARYFY"},
    # ── Upload welcome screen ──
    "upload_title":         {"en": "Upload HDF files to begin",   "pl": "Wgraj pliki HDF aby rozpocząć"},
    "upload_sub":           {"en": "Download CSV exports from the", "pl": "Pobierz eksporty CSV ze"},
    "upload_portal":        {"en": "smart meter portal",          "pl": "portalu licznika"},
    "upload_sidebar":       {"en": "and upload them using the sidebar on the left.", "pl": "i wgraj je przez panel po lewej."},
    # ── Tabs ──
    "tab_overview":         {"en": "📊 Overview",                 "pl": "📊 Przegląd"},
    "tab_consumption":      {"en": "🔌 Consumption",              "pl": "🔌 Zużycie"},
    "tab_power":            {"en": "⚡ Power Demand",             "pl": "⚡ Pobór mocy"},
    "tab_daily":            {"en": "📅 Daily Analysis",           "pl": "📅 Analiza dzienna"},
    "tab_cost":             {"en": "💶 Cost Breakdown",           "pl": "💶 Rozliczenie kosztów"},
    "tab_insights":         {"en": "🔍 Advanced Insights",        "pl": "🔍 Zaawansowane"},
    "tab_prediction":       {"en": "🔮 Bill Prediction",          "pl": "🔮 Prognoza rachunku"},
    "tab_raw":              {"en": "📋 Raw Data",                 "pl": "📋 Dane surowe"},
    # ── Overview ──
    "key_metrics":          {"en": "Key Metrics",                 "pl": "Główne wskaźniki"},
    "period_week":          {"en": "Week",                        "pl": "Tydzień"},
    "period_month":         {"en": "Month",                       "pl": "Miesiąc"},
    "period_bill":          {"en": "Bill",                        "pl": "Rachunek"},
    "period_total":         {"en": "Total",                       "pl": "Całość"},
    "total_consumption":    {"en": "Total Consumption",           "pl": "Zużycie łącznie"},
    "daily_average":        {"en": "Daily Average",               "pl": "Średnia dzienna"},
    "energy_cost":          {"en": "Energy Cost",                 "pl": "Koszt energii"},
    "avg_daily_cost":       {"en": "Avg Daily Cost",              "pl": "Śr. koszt dzienny"},
    "data_span":            {"en": "Data Span",                   "pl": "Zakres danych"},
    "standby_load":         {"en": "Standby Load",                "pl": "Pobór w czuwaniu"},
    "peak_demand":          {"en": "Peak Demand",                 "pl": "Szczytowy pobór"},
    "daily_energy":         {"en": "Daily Energy by Tariff Period", "pl": "Zużycie dzienne wg taryfy"},
    "tariff_split_full":    {"en": "Tariff Split",                "pl": "Podział taryfy"},
    # ── Consumption ──
    "consumption_title":    {"en": "30-Minute Interval Consumption", "pl": "Zużycie — interwały 30-min"},
    "from_label":           {"en": "From",                        "pl": "Od"},
    "to_label":             {"en": "To",                          "pl": "Do"},
    "total_kwh":            {"en": "Total kWh",                   "pl": "Łącznie kWh"},
    "peak_kwh":             {"en": "Peak kWh",                    "pl": "Szczyt kWh"},
    "gross_cost":           {"en": "Gross cost",                  "pl": "Koszt brutto"},
    "heatmap_title":        {"en": "Hourly Usage Heatmap",        "pl": "Mapa zużycia — godziny"},
    # ── Power Demand ──
    "power_title":          {"en": "Power Demand",                "pl": "Pobór mocy"},
    "daily_peak_avg":       {"en": "Daily Peak & Average",        "pl": "Szczyt i średnia dzienna"},
    "load_curve":           {"en": "Load Duration Curve",         "pl": "Krzywa czasu trwania obciążenia"},
    "avg_demand_hour":      {"en": "Average Demand by Hour",      "pl": "Średni pobór wg godziny"},
    # ── Daily Analysis ──
    "daily_registers":      {"en": "Daily Night/Day/Peak Registers", "pl": "Rejestry dzienna Noc/Dzień/Szczyt"},
    "cumulative_registers": {"en": "Cumulative Register Values",  "pl": "Skumulowane wartości rejestrów"},
    "invoice_check":        {"en": "Invoice Cross-Check",         "pl": "Weryfikacja faktury"},
    "daily_trend":          {"en": "Daily kWh Trend",             "pl": "Trend dzienny kWh"},
    # ── Cost Breakdown ──
    "cost_breakdown":       {"en": "Cost Breakdown",              "pl": "Rozliczenie kosztów"},
    "monthly_bill":         {"en": "Monthly Bill Estimate",       "pl": "Szacunkowy rachunek miesięczny"},
    # ── Advanced Insights ──
    "seasonal_trend":       {"en": "Seasonal & Monthly Trend",    "pl": "Trend sezonowy i miesięczny"},
    "load_profile":         {"en": "Average Daily Load Profile",  "pl": "Średni dobowy profil obciążenia"},
    "weekday_weekend":      {"en": "Weekday vs Weekend",          "pl": "Dni robocze / Weekend"},
    "standby_baseline":     {"en": "Standby & Baseline Load",     "pl": "Pobór w czuwaniu i bazowy"},
    "peak_shifting":        {"en": "Peak Shifting Calculator",    "pl": "Kalkulator przeniesienia szczytu"},
    "anomaly_days":         {"en": "Anomaly Days",                "pl": "Dni anomalii"},
    # ── Bill Prediction ──
    "current_progress":     {"en": "Current Period Progress",     "pl": "Postęp bieżącego okresu"},
    "bill_prediction":      {"en": "Bill Prediction",             "pl": "Prognoza rachunku"},
    "billing_period":       {"en": "Billing Period",              "pl": "Okres rozliczeniowy"},
    # ── Raw Data ──
    "raw_data":             {"en": "Raw Data Explorer",           "pl": "Eksplorator danych surowych"},
    "quality_report":       {"en": "Data Quality Report",         "pl": "Raport jakości danych"},
    # ── Setup ──
    "ai_parser":            {"en": "AI Invoice Parser",           "pl": "Analizator faktur AI"},
    "manual_entry":         {"en": "Manual Entry",                "pl": "Wprowadzanie ręczne"},
    "supplier_name":        {"en": "Supplier name",               "pl": "Nazwa dostawcy"},
    "billing_period_start": {"en": "Current period start",        "pl": "Początek bieżącego okresu"},
    "billing_cycle_days":   {"en": "Typical cycle (days)",        "pl": "Typowy cykl (dni)"},
    "confirm_continue":     {"en": "✅ Confirm & Continue",       "pl": "✅ Potwierdź i kontynuuj"},
    "save_continue":        {"en": "✅ Save & Continue",          "pl": "✅ Zapisz i kontynuuj"},
    "review_extracted":     {"en": "Review extracted values",     "pl": "Sprawdź wyodrębnione wartości"},
    "billing_period_hdr":   {"en": "Billing period",              "pl": "Okres rozliczeniowy"},
    "expected_bill_date":   {"en": "Expected billing date",       "pl": "Oczekiwana data rachunku"},
    "days_from_today":      {"en": "days from today",             "pl": "dni od dziś"},
    # ── Alerts ──
    "upload_calc_first":    {"en": "Upload the <strong>calckWh</strong> file.", "pl": "Wgraj plik <strong>calckWh</strong>."},
    "upload_kw_first":      {"en": "Upload the <strong>kW</strong> file.",      "pl": "Wgraj plik <strong>kW</strong>."},
    "upload_dnp_first":     {"en": "Upload <strong>Daily DNP</strong> or <strong>Daily kWh</strong>.", "pl": "Wgraj plik <strong>Daily DNP</strong> lub <strong>Daily kWh</strong>."},
    "incomplete_data":      {"en": "day(s) with incomplete 30-min data", "pl": "dzień/dni z niekompletnymi danymi 30-min"},
    "days_label":           {"en": "days",                        "pl": "dni"},
    "kwh_day":              {"en": "kWh/day",                     "pl": "kWh/dzień"},
    "w_standby":            {"en": "W (2–4am)",                   "pl": "W (2–4 rano)"},
    "incl_off":             {"en": "incl. {pct}% off",            "pl": "z rabatem {pct}%"},
    "gross_label": {"en": "gross",                       "pl": "brutto"},
    "days_remaining":       {"en": "Days Remaining",              "pl": "dni pozostało"},
    "days_elapsed":         {"en": "Days Elapsed",                "pl": "dni minęło"},
    "period_end":           {"en": "Period End",                  "pl": "Koniec okresu"},
    "consumed_so_far":      {"en": "Consumed so far",             "pl": "Zużyto dotąd"},
    "daily_avg_period":     {"en": "Daily avg (period)",          "pl": "Średnia dzienna (okres)"},
    "api_key_privacy":      {"en": "API Key — Privacy",           "pl": "Klucz API — Prywatność"},
    "session_only":         {"en": "Session only — not saved to disk (default, most private)", "pl": "Tylko sesja — nie zapisany (domyślnie, najbardziej prywatny)"},
    "save_to_disk":         {"en": "Save to disk — AES-256 encrypted, survives container restarts", "pl": "Zapisz na dysk — szyfrowanie AES-256, przeżywa restarty"},
    "extract_btn":          {"en": "🔍 Extract tariff data from invoice", "pl": "🔍 Wyodrębnij dane taryfy z faktury"},
    "extraction_ok":        {"en": "✅ Invoice parsed! Review and confirm the values below.", "pl": "✅ Faktura przetworzona! Sprawdź i potwierdź wartości poniżej."},
    "or_manually":          {"en": "Or enter rates manually instead", "pl": "Lub wprowadź stawki ręcznie"},
    "upload_invoice":       {"en": "Upload your electricity bill (PDF)", "pl": "Wgraj rachunek za prąd (PDF)"},
    "enter_api_key":        {"en": "Enter your API key to proceed.", "pl": "Wprowadź klucz API aby kontynuować."},
    "upload_pdf_first":     {"en": "Upload a PDF invoice to continue.", "pl": "Wgraj fakturę PDF aby kontynuować."},
    # Setup form fields
    "mprn_optional":        {"en": "MPRN (optional)",              "pl": "MPRN (opcjonalnie)"},
    "mprn_placeholder":     {"en": "leave blank if unknown",       "pl": "zostaw puste jeśli nieznany"},
    "supplier_placeholder": {"en": "e.g. Electric Ireland",        "pl": "np. Electric Ireland"},
    "day_rate_label":       {"en": "Day rate (€/kWh)",             "pl": "Stawka dzienna (€/kWh)"},
    "peak_rate_label":      {"en": "Peak rate (€/kWh)",            "pl": "Stawka szczytowa (€/kWh)"},
    "night_rate_label":     {"en": "Night rate (€/kWh)",           "pl": "Stawka nocna (€/kWh)"},
    "standing_label":       {"en": "Standing charge (€/d)",        "pl": "Opłata stała (€/dzień)"},
    "discount_label":       {"en": "Discount (%)",                 "pl": "Rabat (%)"},
    "tariff_label":         {"en": "Tariff",                       "pl": "Taryfa"},
    "billing_period_opt":   {"en": "#### 📅 Billing Period *(optional — enables bill prediction)*",
                             "pl": "#### 📅 Okres rozliczeniowy *(opcjonalnie — włącza prognozę rachunku)*"},
    "billing_tip":          {"en": "💡 Find your billing period start on the last page of your electricity bill.<br><br>The expected billing date will be calculated automatically.",
                             "pl": "💡 Znajdź początek okresu rozliczeniowego na ostatniej stronie rachunku za prąd.<br><br>Oczekiwana data rachunku zostanie obliczona automatycznie."},
    "default_rates_tip":    {"en": "ℹ️ Default rates are examples — check your electricity bill for actual rates.",
                             "pl": "ℹ️ Domyślne stawki są przykładowe — sprawdź swój rachunek za prąd."},
    # AI parser
    "ai_provider":          {"en": "AI Provider",                  "pl": "Dostawca AI"},
    "api_key_label":        {"en": "API Key",                      "pl": "Klucz API"},
    "api_key_placeholder":  {"en": "sk-... or AIza... etc.",       "pl": "sk-... lub AIza... itp."},
    "api_key_privacy_hdr":  {"en": "🔑 API Key — Privacy",        "pl": "🔑 Klucz API — Prywatność"},
    "api_key_privacy_sub":  {"en": "Choose whether to save your key across container restarts:",
                             "pl": "Wybierz czy zapisać klucz między restartami kontenera:"},
    "provider_recs":        {"en": "<strong>Provider recommendations:</strong>",
                             "pl": "<strong>Rekomendacje dostawców:</strong>"},
    "provider_anthropic":   {"en": "best PDF support, reliable, from $0.003/invoice",
                             "pl": "najlepsza obsługa PDF, niezawodny, od $0.003/faktura"},
    "provider_gemini":      {"en": "good PDF support, free tier available",
                             "pl": "dobra obsługa PDF, dostępny bezpłatny tier"},
    "provider_openrouter":  {"en": "one key, access to 200+ models including free ones",
                             "pl": "jeden klucz, dostęp do 200+ modeli w tym darmowych"},
    "provider_openai":      {"en": "treats PDF as image, may be less accurate",
                             "pl": "traktuje PDF jak obraz, może być mniej dokładny"},
    "api_called_only":      {"en": "The API is called <strong>only when you click the Extract button</strong> — not on upload.",
                             "pl": "API jest wywoływane <strong>tylko po kliknięciu przycisku Wyodrębnij</strong> — nie przy wgraniu."},
    "if_429":               {"en": "If you get a <strong>429 error</strong>, your daily free quota is exhausted — try a different model or wait until midnight PT for reset.",
                             "pl": "Jeśli wystąpi błąd <strong>429</strong>, dzienny limit darmowy jest wyczerpany — spróbuj innego modelu lub poczekaj do północy czasu PT."},
    "aes_warn":             {"en": "Key will be AES-256 encrypted and stored on this server only. Set the ENERGY_VIZ_SECRET env var for a unique encryption key.",
                             "pl": "Klucz zostanie zaszyfrowany AES-256 i zapisany tylko na tym serwerze. Ustaw zmienną <code>ENERGY_VIZ_SECRET</code> dla unikalnego klucza szyfrowania."},
    "session_key_info":     {"en": "Key lives in browser session memory only. Re-entry required after tab close or container restart.",
                             "pl": "Klucz jest tylko w pamięci sesji przeglądarki. Wymagane ponowne wprowadzenie po zamknięciu karty lub restarcie kontenera."},
    "delete_api_key":       {"en": "🗑️ Delete saved API key from disk",  "pl": "🗑️ Usuń zapisany klucz API z dysku"},
    "openrouter_info":      {"en": "enter the model ID from",            "pl": "wprowadź ID modelu z"},
    "openrouter_free":      {"en": "Recommended free models with PDF support:",
                             "pl": "Zalecane darmowe modele z obsługą PDF:"},
    "openrouter_model_id":  {"en": "OpenRouter model ID",               "pl": "ID modelu OpenRouter"},
    "extract_ok":           {"en": "✅ Invoice parsed! Review and confirm the values below.",
                             "pl": "✅ Faktura przetworzona! Sprawdź i potwierdź wartości poniżej."},
    "enter_api_proceed":    {"en": "Enter your API key to proceed.",     "pl": "Wprowadź klucz API aby kontynuować."},
    "upload_pdf_continue":  {"en": "Upload a PDF invoice to continue.",  "pl": "Wgraj fakturę PDF aby kontynuować."},
    "manually_tip":         {"en": "💡 You can enter rates manually using the expander below.",
                             "pl": "💡 Możesz wprowadzić stawki ręcznie w sekcji poniżej."},
    "or_manually_exp":      {"en": "Or enter rates manually instead",   "pl": "Lub wprowadź stawki ręcznie"},
    # Raw data
    "browse_dataset":       {"en": "Browse dataset",                    "pl": "Przeglądaj zbiór danych"},
    # Billing period review
    "set_period_start":     {"en": "Set the current period start — used for bill prediction.",
                             "pl": "Ustaw <strong>początek bieżącego okresu</strong> — używany do prognozy rachunku."},
    "days_from_today_lbl":  {"en": "days from today",                   "pl": "dni od dziś"},
    # Main app misc
    "download_csv":         {"en": "⬇️ Download CSV",                  "pl": "⬇️ Pobierz CSV"},
    "press_confirm":        {"en": "Press again to confirm — this deletes ALL saved data.",
                             "pl": "Naciśnij ponownie aby potwierdzić — usuwa WSZYSTKIE zapisane dane."},
    "saved_api_deleted":    {"en": "Saved API key deleted.",            "pl": "Zapisany klucz API usunięty."},
    "spikes_p99":           {"en": "Spikes >p99",                 "pl": "Skoki >p99"},
    "energy_net":           {"en": "Energy (net)",                 "pl": "Energia (netto)"},
    "standing_charges":     {"en": "Standing",                     "pl": "Opłata stała"},
    "vat_9":                {"en": "VAT 9%",                       "pl": "VAT 9%"},
    "est_total_bill":       {"en": "Est. total bill",              "pl": "Szac. rachunek łączny"},
    "standby_power":        {"en": "Standby power",                "pl": "Pobór w czuwaniu"},
    "at_night_rate":        {"en": "at night rate",                "pl": "po stawce nocnej"},
    "annual_standby_kwh":   {"en": "Annual Standby Kwh",           "pl": "Roczne zużycie w czuwaniu"},
    "annual_cost":          {"en": "Annual cost",                  "pl": "Koszt roczny"},
    "all_to_night":         {"en": "all to night",                 "pl": "wszystko na noc"},
    "max_saving":           {"en": "Max saving (100%)",            "pl": "Maks. oszczędność (100%)"},
    "days_remaining_lbl":   {"en": "Days remaining",               "pl": "Pozostało dni"},
    "period_end_lbl":       {"en": "Period end",                   "pl": "Koniec okresu"},
    "cumulative_cost":      {"en": "Cumulative Cost Projection",   "pl": "Prognoza kosztu skumulowanego"},
    "est_bill_breakdown":   {"en": "Estimated Bill Breakdown",     "pl": "Szacunkowy podział rachunku"},
    "billing_period_sett":  {"en": "Billing Period Settings",      "pl": "Ustawienia okresu rozliczeniowego"},
    "period_saved":         {"en": "Billing period saved.",        "pl": "Okres rozliczeniowy zapisany."},
    "analysing_invoice":    {"en": "Analysing invoice…",           "pl": "Analizowanie faktury…"},
    "extraction_failed":    {"en": "Extraction failed",            "pl": "Wyodrębnianie nieudane"},
    "network_error":        {"en": "Network error reaching",       "pl": "Błąd sieci przy połączeniu z"},
    "unexpected_error":     {"en": "Unexpected error from",        "pl": "Nieoczekiwany błąd z"},
    "cross_validation":     {"en": "Cross-validation",             "pl": "Weryfikacja krzyżowa"},
    "consumed_so_far_lbl":  {"en": "Consumed so far",             "pl": "Zużyto dotąd"},
    "daily_avg_p":          {"en": "Daily avg (period)",           "pl": "Śr. dzienna (okres)"},
    "days_remaining_m":     {"en": "Days remaining",               "pl": "Pozostało dni"},
    "period_end_m":         {"en": "Period end",                   "pl": "Koniec okresu"},
    "simple_interp":        {"en": "Simple interpolation",         "pl": "Prosta interpolacja"},
    "seasonal_model":       {"en": "Seasonal model",               "pl": "Model sezonowy"},
    "rolling_14d":          {"en": "14-day rolling avg",           "pl": "Średnia krocząca 14 dni"},
    "early_estimate":       {"en": "early estimate, wide range",   "pl": "wczesna estymacja, szeroki zakres"},
    "curr_period_daily":    {"en": "Curr Period Daily", "pl": "Średnia dzienna bieżącego okresu × pozostałe dni"},
    "hist_monthly":         {"en": "Hist Monthly", "pl": "Historyczne średnie miesięczne na dzień"},
    "recent_14d":           {"en": "Recent 14D", "pl": "Trend z ostatnich 14 dni × pozostałe dni"},
    "pct_elapsed":          {"en": "elapsed",                      "pl": "minęło"},
    "total_peak_kwh":       {"en": "Total Peak Kwh",               "pl": "Łącznie kWh szczytowych"},
    "at_shift_pct":         {"en": "At {pct}% shift",             "pl": "Przy przesunięciu {pct}%"},
    "night_cheaper":        {"en": "night {pct}% cheaper",         "pl": "noc tańsza o {pct}%"},
    "annual_standby":       {"en": "Annual Standby Kwh",           "pl": "Roczne kWh w czuwaniu"},
    "how_updates_work":     {"en": "How updates work",             "pl": "Jak działają aktualizacje"},
    "updates_info":         {"en": "Updates Info",
                             "pl": "ESB zawsze eksportuje pełną historię (do 13 miesięcy) przy każdym pobraniu. Wgranie nowszego eksportu automatycznie zawiera wszystkie poprzednie dane + nowe miesiące + korekty ESB — bez ręcznego łączenia. Wystarczy wgrać najnowszy plik."},
    "based_on_seasonal":    {"en": "based on seasonal model",      "pl": "oparty na modelu sezonowym"},
    "period_selector":      {"en": "Period",                       "pl": "Okres"},
    "view_label":           {"en": "View",                         "pl": "Widok"},
    "shift_pct_label":      {"en": "% of peak shifted to night",   "pl": "% szczytu przeniesionego na noc"},
    "anomaly_threshold":    {"en": "anomaly threshold",            "pl": "próg anomalii"},
    "elec_bill":            {"en": "electricity bill",             "pl": "rachunku za prąd"},
    "days_label2":          {"en": "days",                         "pl": "dni"},
    "data_span_days":       {"en": "days",                         "pl": "dni"},
    "kwh_day_lbl":          {"en": "kWh/day",                      "pl": "kWh/dzień"},
    "per_day":              {"en": "/day",                         "pl": "/dzień"},
    "gross_lbl":            {"en": "gross",                        "pl": "brutto"},
    "energy_charges":       {"en": "Energy charges (gross)",       "pl": "Opłaty za energię (brutto)"},
    "your_discount":        {"en": "Your discount",                "pl": "Twój rabat"},
    "standing_charges_lbl": {"en": "Standing charges",             "pl": "Opłaty stałe"},
    "vat_label":            {"en": "VAT 9%",                       "pl": "VAT 9%"},
    "est_bill":             {"en": "Est. total bill",              "pl": "Szac. rachunek łączny"},
    "incl_off_lbl":         {"en": "incl. {n}% off",              "pl": "z rabatem {n}%"},
    # Chart trace names
    "day_off_peak":         {"en": "Day Off-Peak",               "pl": "Dzień poza szczytem"},
    "seven_day_avg":        {"en": "7-day avg",                  "pl": "śr. 7 dni"},
    "rolling_avg_label":    {"en": "7-day average",              "pl": "Śr. 7-dniowa"},
    "trace_avg":            {"en": "Avg",                        "pl": "Śred."},
    "trace_total":          {"en": "Total",                      "pl": "Łącznie"},
    "trace_energy":         {"en": "Energy",                     "pl": "Energia"},
    "trace_simple":         {"en": "Simple interpolation",       "pl": "Prosta interpolacja"},
    "trace_seasonal":       {"en": "Seasonal model",             "pl": "Model sezonowy"},
    "trace_14d":            {"en": "14-day rolling avg",         "pl": "Śr. krocząca 14 dni"},
    "trace_kwh":            {"en": "kWh",                        "pl": "kWh"},
    "bill_date":            {"en": "Bill date",                  "pl": "Data rachunku"},
    "all_time":             {"en": "all-time",                   "pl": "łącznie"},
    "kwh_year_est":         {"en": "kWh/year est.",              "pl": "kWh/rok (est.)"},
    "kwh_day_unit":         {"en": "kWh/day",                    "pl": "kWh/dzień"},
    "kw_cumulative":        {"en": "kWh (cumulative)",           "pl": "kWh (skumulowane)"},
    "reading_rank":         {"en": "Reading rank",               "pl": "Pozycja odczytu"},
    "vs_avg":               {"en": "vs avg",                     "pl": "vs śr."},
    "mean_2sigma":          {"en": ">mean+2σ",                   "pl": ">śr.+2σ"},
    "trace_0":              {"en": "kWh",                        "pl": "kWh"},
    "median":               {"en": "Median",                     "pl": "Mediana"},
    "predicted_bill_range": {"en": "Predicted bill range",       "pl": "Przewidywany zakres rachunku"},
    "most_likely":          {"en": "Most likely",                "pl": "Najbardziej prawdopodobny"},
    "range_label":          {"en": "Range",                      "pl": "Zakres"},
    "projected":            {"en": "projected",                  "pl": "prognoza"},
    "curr_period_desc":     {"en": "Curr Period Daily", "pl": "Śr. dzienna bieżącego okresu × pozostałe dni"},
    "hist_monthly_desc":    {"en": "Hist Monthly", "pl": "Historyczne średnie miesięczne na dzień"},
    "recent_14d_desc":      {"en": "Recent 14D", "pl": "Trend z ostatnich 14 dni × pozostałe dni"},
    "prediction_accuracy":  {"en": "Prediction accuracy depends on how much of the period has elapsed. Currently {pct}% complete — early estimate, wide range.",
                             "pl": "Dokładność prognozy zależy od stopnia zaawansowania okresu. Obecnie {pct}% — wczesna estymacja, szeroki zakres."},
    "simple_extrap":        {"en": "📈 Simple extrapolation",   "pl": "📈 Prosta ekstrapolacja"},
    "seasonal_m":           {"en": "🌡️ Seasonal model",        "pl": "🌡️ Model sezonowy"},
    "rolling_14d_m":        {"en": "📅 14-day rolling avg",     "pl": "📅 Śr. krocząca 14 dni"},
    "est_total_due":        {"en": "Est. Total Due",             "pl": "Szac. kwota do zapłaty"},
    "period_start":         {"en": "Period start",               "pl": "Początek okresu"},
    "cycle_length":         {"en": "Cycle length (days)",        "pl": "Długość cyklu (dni)"},
    "next_bill_expected":   {"en": "Next bill expected",         "pl": "OCZEKIWANA DATA RACHUNKU"},
    "update_billing":       {"en": "💾 Update billing period",  "pl": "💾 Aktualizuj okres rozliczeniowy"},
    "days_elapsed_n":       {"en": "{n} days elapsed",           "pl": "{n} dni minęło"},
    "days_remaining_n":     {"en": "{n} days remaining",         "pl": "{n} dni pozostało"},
    "elapsed_pct":          {"en": "elapsed",                    "pl": "minęło"},
    "day_label_chart":      {"en": "Day",                        "pl": "Dzień"},
    "peak_label_chart":     {"en": "Peak",                       "pl": "Szczyt"},
    "night_label_chart":    {"en": "Night",                      "pl": "Noc"},
    # Weekday names
    "mon": {"en": "Monday",    "pl": "Poniedziałek"},
    "tue": {"en": "Tuesday",   "pl": "Wtorek"},
    "wed": {"en": "Wednesday", "pl": "Środa"},
    "thu": {"en": "Thursday",  "pl": "Czwartek"},
    "fri": {"en": "Friday",    "pl": "Piątek"},
    "sat": {"en": "Saturday",  "pl": "Sobota"},
    "sun": {"en": "Sunday",    "pl": "Niedziela"},
    # Misc chart labels
    "standing_lbl":         {"en": "Standing",                   "pl": "Opłata stała"},
    "energy_cost_period":   {"en": "Energy Cost Period", "pl": "Koszt energii wg taryfy"},
    "cross_val_note":       {"en": "Cross Val Note",
                             "pl": "Weryfikacja: kW × 0,5h ≈ calckWh — śr. błąd <0,001 kWh/interwał."},
    "kw_year_unit":         {"en": "kWh/year est.",              "pl": "kWh/rok (est.)"},
    "night_cheaper_pct":    {"en": "night {pct}% cheaper",       "pl": "noc tańsza o {pct}%"},
    "at_shift_label":       {"en": "At {pct}% shift",            "pl": "Przy przesunięciu {pct}%"},
    "date_col":             {"en": "Date",                       "pl": "Data"},
    "kwh_col":              {"en": "kWh",                        "pl": "kWh"},
    "vs_avg_col":           {"en": "vs avg",                     "pl": "vs śr."},
    # Sidebar
    "power_demand_short":   {"en": "Power Demand",               "pl": "Pobór mocy"},
    "daily_dnp_short":      {"en": "Daily DNP",                  "pl": "Dzienne DNP"},
    "daily_kwh_short":      {"en": "Daily kWh",                  "pl": "Dzienna kWh"},
    "tariff_split_lbl":     {"en": "Tariff Split Lbl",            "pl": "⚡ PODZIAŁ TARYFY"},
    # Rangeselector buttons
    "rs_1d":                {"en": "1d",   "pl": "1d"},
    "rs_1w":                {"en": "1w",   "pl": "1t"},
    "rs_2w":                {"en": "2w",   "pl": "2t"},
    "rs_1m":                {"en": "1m",   "pl": "1m"},
    "rs_3m":                {"en": "3m",   "pl": "3m"},
    "rs_1y":                {"en": "1y",   "pl": "1r"},
    "rs_all":               {"en": "All",  "pl": "Wsz"},
    # Overview alerts
    "dst_warning":          {"en": "{n} day(s) with incomplete 30-min data (e.g. DST clock change — {k} intervals). Minor underestimate for those days.",
                             "pl": "{n} dzień/dni z niekompletnymi danymi 30-min (np. zmiana czasu DST — {k} interwałów). Niewielkie zaniżenie dla tych dni."},
    "outlier_warning":      {"en": "Daily kWh file: outlier row(s) automatically removed (likely meter rollover artifact).",
                             "pl": "Plik dzienny kWh: automatycznie usunięto wiersze odstające (prawdopodobnie artefakt przepełnienia licznika)."},
    # Power Demand metrics
    "peak_demand_lbl":      {"en": "Peak demand",                "pl": "Szczytowy pobór"},
    "avg_demand_lbl":       {"en": "Avg demand",                 "pl": "Śred. pobór"},
    "pct95_lbl":            {"en": "95th pct",                   "pl": "95. percentyl"},
    "spikes_lbl":           {"en": "Spikes >p99",                "pl": "Skoki >p99"},
    "kw_all_time":          {"en": "kW all-time",                "pl": "kW (łącznie)"},
    # Cross validation
    "cross_val":            {"en": "Cross Val",
                             "pl": "Weryfikacja: kW × 0,5h ≈ calckWh — śr. błąd <0,001 kWh/interwał."},
    # Daily Analysis
    "daily_total_kwh":      {"en": "Daily Total kWh",            "pl": "Dzienne łączne kWh"},
    "reg_24h":              {"en": "24h register",               "pl": "Rejestr 24h"},
    "day_off_peak_lbl":     {"en": "Day Off-Peak",               "pl": "Dzień poza szczytem"},
    # Cost Breakdown chart labels
    "day_donut":            {"en": "Day",                        "pl": "Dzień"},
    "peak_donut":           {"en": "Peak",                       "pl": "Szczyt"},
    "night_donut":          {"en": "Night",                      "pl": "Noc"},
    # Bill prediction
    "pct_elapsed_lbl":      {"en": "{pct}% elapsed",             "pl": "{pct}% minęło"},
    "n_days_elapsed":       {"en": "{n} days elapsed",           "pl": "{n} dni minęło"},
    "n_days_remaining":     {"en": "{n} days remaining",         "pl": "{n} dni pozostało"},
    "in_n_days":            {"en": "in {n} days",                "pl": "za {n} dni"},
    "kwh_projected":        {"en": "~{n} kWh projected",         "pl": "~{n} kWh prognoza"},
    "your_discount_lbl":    {"en": "Your discount ({pct}%)",     "pl": "Twój rabat ({pct}%)"},
    "next_bill_exp":        {"en": "Next bill expected",         "pl": "Następny rachunek"},
    "update_billing_btn":   {"en": "💾 Update billing period",  "pl": "💾 Aktualizuj okres"},
    # Raw Data quality
    "dst_slots_kept":       {"en": "{n} DST clock-back slot(s) kept (valid)", "pl": "DST: {n} dodatkowych slotów (poprawne)"},
    "dupes_removed":        {"en": "{n} exact duplicate row(s) removed",      "pl": "usunięto {n} duplikat(ów)"},
    "outliers_removed_lbl": {"en": "{n} meter rollover outlier(s) removed",   "pl": "usunięto {n} artefakt(y) przepełnienia"},
    "rows_summary":         {"en": "{raw:,} rows in → {clean:,} rows clean",  "pl": "{raw:,} wierszy → {clean:,} po czyszczeniu"},
    "no_issues":            {"en": "No issues found",            "pl": "Brak problemów"},
    "how_updates_info":     {"en": "Updates Info",
                             "pl": "ESB zawsze eksportuje pełną historię (do 13 miesięcy) przy każdym pobraniu. Wgranie nowszego eksportu automatycznie zawiera wszystkie poprzednie dane + nowe miesiące + korekty ESB — bez ręcznego łączenia. Wystarczy wgrać najnowszy plik."},
    # Misc
    "primary_badge":        {"en": "PRIMARY",                    "pl": "GŁÓWNY"},
    "net_label":            {"en": "net",                        "pl": "netto"},
    "gross_label":          {"en": "gross",                      "pl": "brutto"},
    "incl_pct_off":         {"en": "incl. {pct}% off",          "pl": "z rabatem {pct}%"},
    "days_x":               {"en": "{n}d × €{r:.4f}",           "pl": "{n}d × €{r:.4f}"},
    "auto_checked":         {"en": "auto-checked on every upload", "pl": "sprawdzane przy każdym wgraniu"},
    "kw_file_badge":        {"en": "kW file",                    "pl": "plik kW"},
    "dnp_badge":            {"en": "DNP",                        "pl": "DNP"},
    "register_24h_badge":   {"en": "24h register",               "pl": "rejestr 24h"},
    "save_badge":           {"en": "Save",                       "pl": "Zapisz"},
    "upload_files_to_see":  {"en": "Upload Files To See", "pl": "Wgraj pliki aby zobaczyć raport jakości danych."},
    "net_pct_off":          {"en": "Net ({pct}% off)",            "pl": "Netto ({pct}% rabatu)"},
    "incl_pct_off_lbl":     {"en": "incl. {pct}% off",           "pl": "z rabatem {pct}%"},
    "weekday_weekend_pl":   {"en": "Weekday vs Weekend",          "pl": "Dni robocze / Weekend"},
    "avg_kwh_axis":         {"en": "avg kWh",                     "pl": "śred. kWh"},
    "avg_kw_axis":          {"en": "avg kW",                      "pl": "śred. kW"},
    "predicted_range":      {"en": "📊 Predicted bill range",     "pl": "📊 Przewidywany zakres rachunku"},
    "most_likely_lbl":      {"en": "Most likely",                 "pl": "Najbardziej prawdopodobny"},
    "range_lbl":            {"en": "Range",                       "pl": "Zakres"},
    "next_bill_lbl":        {"en": "Next bill expected",          "pl": "Następny rachunek"},
    "n_days_from_today":    {"en": "{n} days from today",         "pl": "za {n} dni"},
    "cross_val_alert":      {"en": "Cross-validation: kW × 0.5h ≈ calckWh — mean error <b>&lt;0.001 kWh</b>/interval.", "pl": "Weryfikacja: kW × 0,5h ≈ calckWh — śr. błąd <b>&lt;0,001 kWh</b>/interwał."},
    "trace_simple_short":   {"en": "Simple",                      "pl": "Prosta"},
    "trace_seasonal_short": {"en": "Seasonal",                    "pl": "Sezonowy"},
    "trace_14d_short":      {"en": "14-day",                      "pl": "14-dniowa"},
    "kwh_projected_lbl":    {"en": "~{n} kWh projected",         "pl": "~{n} kWh prognoza"},
    "pct_elapsed_bar":      {"en": "{pct}% elapsed",              "pl": "{pct}% minęło"},
    "n_elapsed_lbl":        {"en": "{n} days elapsed",            "pl": "{n} dni minęło"},
    "n_remaining_lbl":      {"en": "{n} days remaining",          "pl": "{n} dni pozostało"},
    "day_off_peak_dnp":     {"en": "☀️ Day Off-Peak",             "pl": "☀️ Dzień poza szczytem"},
    "legend_avg":           {"en": "Avg",                         "pl": "Śred."},
    "legend_day":           {"en": "Day",                         "pl": "Dzień"},
    "legend_peak":          {"en": "Peak",                        "pl": "Szczyt"},
    "legend_night":         {"en": "Night",                       "pl": "Noc"},
    "legend_7d_avg":        {"en": "7-day avg",                   "pl": "śred. 7 dni"},
    "euro_cumul":           {"en": "€ (cumulative)",              "pl": "€ (skumulowane)"},
    "daily_dnp_label":      {"en": "Daily DNP",                   "pl": "Dzienne DNP"},
    "sidebar_primary":      {"en": "PRIMARY",                     "pl": "GŁÓWNY"},
    "sidebar_optional":     {"en": "optional",                    "pl": "opcjonalny"},
    "tariff_split_header":  {"en": "TARIFF SPLIT",                "pl": "PODZIAŁ TARYFY"},
    "forecast_lbl":         {"en": "Forecast",                    "pl": "Prognoza"},
    "median_lbl":           {"en": "Median",                      "pl": "Mediana"},
    "spikes_html":          {"en": "● spikes >p99",               "pl": "● skoki >p99"},
    "standby_short":        {"en": "standby",                     "pl": "czuwania"},
    "kwh_year_szac":        {"en": "kWh/year est.",               "pl": "kWh/rok (szac.)"},
    "days_from_today_lbl":  {"en": "{n} days from today",         "pl": "za {n} dni"},
    "in_n_days_lbl":        {"en": "in {n} days",                 "pl": "za {n} dni"},
    "elapsed_lbl":          {"en": "elapsed",                     "pl": "minęło"},
    "most_likely_full":     {"en": "Most likely",                 "pl": "Najbardziej prawdopodobny"},
    "range_full":           {"en": "Range",                       "pl": "Zakres"},
    "next_bill_full":       {"en": "Next bill expected",          "pl": "Następny rachunek"},
    "update_billing_full":  {"en": "💾 Update billing period",   "pl": "💾 Aktualizuj okres"},
    "standby_lbl_pl":       {"en": "Standby",                    "pl": "Czuwanie"},
    "cons_days":            {"en": "Days in range",              "pl": "Dni w zakresie"},
    "cons_max_day":         {"en": "Peak day",                    "pl": "Najwyższy dzień"},
    "cons_min_day":         {"en": "Lowest day",                  "pl": "Najniższy dzień"},
    "cons_avg_day":         {"en": "Daily avg",                   "pl": "Śred. dzienna"},
    "total_cost":           {"en": "Total cost",                  "pl": "Koszt łączny"},
    # ESB Auto-sync
    "esb_sync_title":       {"en": "ESB Auto-Sync",               "pl": "Auto-synchronizacja ESB"},
    "esb_sync_email":       {"en": "ESB account email",           "pl": "Email konta ESB"},
    "esb_sync_password":    {"en": "ESB account password",        "pl": "Hasło konta ESB"},
    "esb_sync_save":        {"en": "💾 Save credentials",         "pl": "💾 Zapisz dane logowania"},
    "esb_sync_clear":       {"en": "🗑️ Clear credentials",        "pl": "🗑️ Usuń dane logowania"},
    "esb_sync_now":         {"en": "🔄 Sync now",                 "pl": "🔄 Synchronizuj teraz"},
    "esb_sync_status":      {"en": "Last sync",                   "pl": "Ostatnia synchronizacja"},
    "esb_sync_ok":          {"en": "✅ Sync successful",          "pl": "✅ Synchronizacja udana"},
    "esb_sync_fail":        {"en": "⚠️ Sync failed",              "pl": "⚠️ Synchronizacja nieudana"},
    "esb_sync_never":       {"en": "Never synced",                "pl": "Brak synchronizacji"},
    "esb_sync_files":       {"en": "Files updated",               "pl": "Zaktualizowane pliki"},
    "esb_sync_running":     {"en": "🔄 Syncing…",                 "pl": "🔄 Synchronizuję…"},
    "esb_sync_no_creds":    {"en": "Enter ESB credentials to enable auto-sync.", "pl": "Wpisz dane ESB aby włączyć auto-synchronizację."},
    "esb_sync_rate_limit":  {"en": "⚠️ ESB rate limit hit (max 2 logins/24h). Next attempt after midnight.", "pl": "⚠️ Limit logowań ESB (max 2/24h). Kolejna próba po północy."},
    "esb_sync_login_fail":  {"en": "⚠️ Login failed — check your ESB email and password.", "pl": "⚠️ Błąd logowania — sprawdź email i hasło ESB."},
    "esb_sync_creds_saved": {"en": "Credentials saved. First sync runs within 10 seconds.", "pl": "Dane zapisane. Pierwsza synchronizacja za 10 sekund."},
    "esb_sync_weekly":      {"en": "Syncs automatically every week.", "pl": "Synchronizacja automatyczna co tydzień."},
    "esb_sync_next":        {"en": "Next sync",                   "pl": "Następna synchronizacja"},
    "esb_creds_stored":     {"en": "🔒 Credentials stored (AES-256)", "pl": "🔒 Dane zapisane (AES-256)"},
    "enter_manually_tip":   {"en": "💡 You can enter rates manually using the expander below.", "pl": "💡 Możesz wprowadzić stawki ręcznie w sekcji poniżej."},
}


def t(key: str) -> str:
    """Return translation for current language."""
    lang = st.session_state.get("lang", "en")
    entry = TRANSLATIONS.get(key, {})
    return entry.get(lang, entry.get("en", key))



def _build_plotly_base():
    C = COLORS
    return dict(
        paper_bgcolor=C["bg"], plot_bgcolor=C["bg"],
        font=dict(family="Space Grotesk, sans-serif", color=C["text"], size=12),
        xaxis=dict(
            gridcolor=C["grid"], linecolor=C["grid"],
            showgrid=True, zeroline=False,
            tickfont=dict(color=C["text"], size=11),
            title_font=dict(color=C["text"]),
        ),
        yaxis=dict(
            gridcolor=C["grid"], linecolor=C["grid"],
            showgrid=True, zeroline=False,
            tickfont=dict(color=C["text"], size=11),
            title_font=dict(color=C["text"]),
        ),
        legend=dict(
            bgcolor=C["card2"], bordercolor=C["grid"], borderwidth=1,
            font=dict(size=11, color=C["text"]),
            orientation="h", yanchor="top", y=-0.15, xanchor="left", x=0,
        ),
        margin=dict(l=10, r=10, t=40, b=50),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=C["card2"], bordercolor=C["grid"],
            font=dict(color=C["text"], size=12),
        ),
    )

PLOTLY_BASE = _build_plotly_base()

def _build_rangeslider_x():
    C = COLORS
    return dict(
        gridcolor=C["grid"], linecolor=C["grid"], showgrid=True, zeroline=False,
        rangeslider=dict(visible=True, thickness=0.08, bgcolor=C["card2"],
                         bordercolor=C["grid"], borderwidth=1),
        rangeselector=dict(
            bgcolor=C["card2"], bordercolor=C["grid"], borderwidth=1,
            activecolor=C["day"], font=dict(color=C["text"], size=11),
            buttons=[
                dict(count=1,  label=t("rs_1d"), step="day",   stepmode="backward"),
                dict(count=7,  label=t("rs_1w"), step="day",   stepmode="backward"),
                dict(count=14, label=t("rs_2w"), step="day",   stepmode="backward"),
                dict(count=1,  label=t("rs_1m"), step="month", stepmode="backward"),
                dict(count=3,  label=t("rs_3m"), step="month", stepmode="backward"),
                dict(count=1,  label=t("rs_1y"), step="year",  stepmode="backward"),
                dict(step="all", label=t("rs_all")),
            ],
        ),
    )

RANGESLIDER_X = _build_rangeslider_x()


def _inject_pl_month_names():
    """Inject JS via st.components to patch Plotly month names to Polish."""
    if st.session_state.get("lang", "en") != "pl":
        return
    import streamlit.components.v1 as components
    pl_map = {
        "Jan": "sty", "Feb": "lut", "Mar": "mar", "Apr": "kwi",
        "May": "maj", "Jun": "cze", "Jul": "lip", "Aug": "sie",
        "Sep": "wrz", "Oct": "paź", "Nov": "lis", "Dec": "gru",
        "January": "Styczeń", "February": "Luty", "March": "Marzec",
        "April": "Kwiecień", "June": "Czerwiec", "July": "Lipiec",
        "August": "Sierpień", "September": "Wrzesień", "October": "Październik",
        "November": "Listopad", "December": "Grudzień",
    }
    replacements_js = ", ".join([f'["{k}", "{v}"]' for k, v in pl_map.items()])
    components.html(f"""
    <script>
    (function() {{
        const map = new Map([{replacements_js}]);
        function patchPlotly() {{
            // Target Plotly tick labels in parent frame
            const frames = [window.parent, window];
            frames.forEach(w => {{
                try {{
                    w.document.querySelectorAll('.xtick text, .ytick text, .infolayer .g-xtitle, .infolayer .g-ytitle').forEach(el => {{
                        for (const [en, pl] of map) {{
                            if (el.textContent && el.textContent.includes(en)) {{
                                el.textContent = el.textContent.replaceAll(en, pl);
                            }}
                        }}
                    }});
                }} catch(e) {{}}
            }});
        }}
        setTimeout(patchPlotly, 800);
        setTimeout(patchPlotly, 2000);
        setTimeout(patchPlotly, 4000);
        const obs = new MutationObserver(patchPlotly);
        try {{
            obs.observe(window.parent.document.body, {{childList: true, subtree: true}});
        }} catch(e) {{
            obs.observe(document.body, {{childList: true, subtree: true}});
        }}
    }})();
    </script>
    """, height=0, scrolling=False)

# Start background scheduler (once per container process)
_start_scheduler(DATA_DIR, HDF_SLOTS, ESB_CREDS_FILE, SYNC_STATUS_FILE, _fernet)

# ─────────────────────────────────────────────
#  SESSION STATE INIT
#  Defaults first, then overlay with persisted config.
# ─────────────────────────────────────────────
def ss(key, default):
    if key not in st.session_state:
        st.session_state[key] = default

ss("setup_done",       False)
ss("lang",             "en")          # 🇮🇪 en | 🇵🇱 pl
ss("tariff",           DEFAULT_TARIFF.copy())
ss("mprn",             "")
ss("supplier",         "")
ss("api_key",          "")        # legacy single key — kept for backward compat
ss("api_keys",         {})        # dict: provider_code → api_key (per-provider storage)
ss("api_provider",     "")
ss("billing_start",    None)
ss("billing_end",      None)
ss("billing_days",     60)
ss("invoices",         [])
ss("_config_loaded",   False)

# ── Restore from disk on first render ──
if not st.session_state["_config_loaded"]:
    restored = load_config()
    # If we have a saved config with tariff data, mark setup as done
    if restored and st.session_state.get("tariff", {}).get("day"):
        st.session_state["setup_done"] = True
    # Restore encrypted API key into session (memory only)
    saved_key = decrypt_api_key()
    if saved_key:
        st.session_state["api_key"]      = saved_key
        st.session_state["api_provider"] = st.session_state.get("api_provider", "")
    st.session_state["_config_loaded"] = True

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def section(icon, title, badge=None):
    badge_html = f'<span class="badge">{badge}</span>' if badge else ""
    st.markdown(f'<div class="sec"><span class="icon">{icon}</span>'
                f'<span class="title">{title}</span>{badge_html}</div>',
                unsafe_allow_html=True)

def kpi_html(label, value, sub="", color="blue"):
    return (f'<div class="kpi-card {color}"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-value">{value}</div><div class="kpi-sub">{sub}</div></div>')

def alert(msg, kind="info"):
    icons = {"info":"ℹ️","warn":"⚠️","good":"✅","red":"🚨"}
    st.markdown(f'<div class="alert-box alert-{kind}">{icons.get(kind,"ℹ️")} {msg}</div>',
                unsafe_allow_html=True)

def apply_layout(fig, title="", height=380, has_rangeselector=False):
    fig.update_layout(**PLOTLY_BASE,
                      title=dict(text=title, font=dict(size=13, color=COLORS["muted"]), x=0),
                      height=height)
    if has_rangeselector:
        fig.update_layout(margin=dict(l=10, r=10, t=80, b=60))
    # Polish: override datetime axis month names via tickformat
    # Plotly uses browser locale — we patch with custom ticktext post-hoc
    if st.session_state.get("lang", "en") == "pl":
        fig.update_layout(
            xaxis_tickformatstops=[
                dict(dtickrange=[None, "M1"],  value="%d %b"),
                dict(dtickrange=["M1",  "M12"], value="%b %Y"),
                dict(dtickrange=["M12", None],  value="%Y"),
            ]
        )
    return fig

def get_period(hour, minute=0):
    t = hour + minute / 60
    if 17 <= t < 19:     return "peak"
    if t >= 23 or t < 8: return "night"
    return "day"

# ─────────────────────────────────────────────
#  PDF INVOICE PARSER  (multi-provider AI SDKs)
# ─────────────────────────────────────────────
# Model names use the new google-genai SDK (GA since May 2025).
# The old google-generativeai package is deprecated (EOL Nov 30 2025)
# and does not support models released after that date.
PROVIDERS = {
    "Anthropic (Claude 3.5 Sonnet)":    "anthropic",
    "Google (Gemini 2.5 Flash)":        "gemini-2.5-flash",
    "Google (Gemini 2.0 Flash)":        "gemini-2.0-flash",
    "Google (Gemini 2.0 Flash Lite)":   "gemini-2.0-flash-lite",
    "OpenRouter (choose model below)":  "openrouter",
    "OpenAI (GPT-4o)":                  "openai",
}

def _is_gemini(provider: str) -> bool:
    return provider.startswith("gemini-")

EXTRACT_PROMPT = """You are a utility bill parser. Extract the following fields from this electricity bill.
Return ONLY a valid JSON object — no markdown, no explanation, nothing else:
{
  "mprn": "meter point reference number as string or null",
  "supplier": "electricity supplier name or null",
  "tariff_name": "tariff/plan name or null",
  "rate_day": <float, day/off-peak unit rate in EURO per kWh, or null>,
  "rate_peak": <float, peak unit rate in EURO per kWh, or null>,
  "rate_night": <float, night unit rate in EURO per kWh, or null>,
  "standing_charge": <float, daily standing charge in EURO, or null>,
  "discount_pct": <float, percentage discount e.g. 30.0, or 0>,
  "vat_pct": <float, VAT percentage e.g. 9.0>,
  "billing_period_start": "DD Mon YY e.g. 13 Jan 26 or null",
  "billing_period_end": "DD Mon YY e.g. 12 Mar 26 or null",
  "billing_period_days": <integer or null>,
  "total_due": <float, total amount due in EURO, or null>
}"""


def _parse_raw_json(raw: str) -> dict:
    """Extract and parse JSON from AI response, with truncation recovery."""
    raw = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
    if not raw.startswith("{"):
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            raw = m.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        diff = raw.count("{") - raw.count("}")
        if diff > 0:
            try:
                return json.loads(raw.rstrip(",\n ") + "}" * diff)
            except json.JSONDecodeError:
                pass
        raise RuntimeError(
            "AI returned malformed or truncated JSON.\n"
            f"First 300 chars of response: {raw[:300]}"
        )


def _error_msg(provider: str, code: int) -> str:
    if code == 429:
        if _is_gemini(provider):
            return (
                f"**Google Gemini 429 — daily quota exhausted** (`{provider}`)\n\n"
                "Your AI Studio key is correct — the free daily limit is used up.\n\n"
                "**Try in order:**\n"
                "1. Switch to **Gemini 2.0 Flash Lite** — higher free RPD\n"
                "2. Switch to **Anthropic Claude** — $5 free credit at "
                "[console.anthropic.com](https://console.anthropic.com)\n"
                "3. Wait until midnight PT for quota reset "
                "([monitor](https://ai.dev/rate-limit))\n"
                "4. Enable billing in AI Studio (~€0.0003/invoice)"
            )
        return f"**{provider} 429 — rate limit.** Wait 60s and retry."
    if code in (401, 403):
        tip = (" Key must be from [aistudio.google.com](https://aistudio.google.com)."
               if _is_gemini(provider) else "")
        return f"**{provider} {code} — invalid API key.**{tip}"
    return f"**{provider} HTTP {code}.**"


@st.cache_data(show_spinner=False)
def parse_invoice_ai(pdf_bytes: bytes, provider: str, api_key: str) -> dict:
    """
    Extract tariff data from an invoice PDF.
    Uses google-genai (new SDK), anthropic, and openai packages.
    """
    raw = ""
    try:
        # ── Anthropic Claude — native PDF document support ──
        if provider == "anthropic":
            import anthropic as _anth
            client = _anth.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": base64.b64encode(pdf_bytes).decode(),
                            },
                        },
                        {"type": "text", "text": EXTRACT_PROMPT},
                    ],
                }],
            )
            raw = msg.content[0].text

        # ── Google Gemini — new google-genai SDK ──
        elif _is_gemini(provider):
            from google import genai as _genai
            from google.genai import types as _gtypes
            client = _genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=provider,
                contents=[
                    EXTRACT_PROMPT,
                    _gtypes.Part.from_bytes(
                        data=pdf_bytes,
                        mime_type="application/pdf",
                    ),
                ],
                config=_gtypes.GenerateContentConfig(
                    max_output_tokens=2048,
                    # Force JSON output — prevents truncation and wrapping text
                    response_mime_type="application/json",
                ),
            )
            raw = response.text

        # ── OpenAI GPT-4o ──
        elif provider == "openai":
            from openai import OpenAI as _OAI
            client = _OAI(api_key=api_key)
            resp = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": EXTRACT_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": ("data:image/jpeg;base64,"
                                        + base64.b64encode(pdf_bytes).decode()),
                                "detail": "high",
                            },
                        },
                    ],
                }],
            )
            raw = resp.choices[0].message.content

        # ── OpenRouter — OpenAI-compatible, any model ──
        elif provider == "openrouter":
            from openai import OpenAI as _OAI
            or_model = api_key.split("||")[1] if "||" in api_key else "google/gemini-2.5-flash-lite"
            or_key   = api_key.split("||")[0]
            client   = _OAI(
                api_key=or_key,
                base_url="https://openrouter.ai/api/v1",
            )
            # OpenRouter routes to many backends — send PDF as base64 inline_data
            # for models that support it (Gemini), or text-only prompt as fallback.
            # Using the multimodal format that works across most vision models:
            resp = client.chat.completions.create(
                model=or_model,
                max_tokens=2048,
                response_format={"type": "json_object"},
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": EXTRACT_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": ("data:application/pdf;base64,"
                                        + base64.b64encode(pdf_bytes).decode()),
                            },
                        },
                    ],
                }],
                extra_headers={
                    "HTTP-Referer": "https://github.com/lucslav/energy-viz",
                    "X-Title": "Energy Viz",
                },
            )
            raw = resp.choices[0].message.content

        else:
            raise ValueError(f"Unknown provider: {provider}")

    except Exception as exc:
        cls  = type(exc).__name__
        msg  = str(exc)

        if "ResourceExhausted" in cls or "429" in msg:
            raise RuntimeError(_error_msg(provider, 429)) from exc
        if "PermissionDenied" in cls or "AuthenticationError" in cls \
                or "401" in msg or "403" in msg:
            raise RuntimeError(_error_msg(provider, 401)) from exc
        if "ConnectionError" in cls or "TimeoutError" in cls:
            raise RuntimeError(
                f"Network error reaching {provider}. Check your connection."
            ) from exc
        if "ModuleNotFoundError" in cls or "ImportError" in cls:
            pkg = {"anthropic": "anthropic", "openai": "openai"}.get(
                provider, "google-genai"
            )
            raise RuntimeError(
                f"Required package not installed: `{pkg}`\n"
                "Add it to requirements.txt and rebuild the container."
            ) from exc
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(
            f"Unexpected error from {provider}: {msg[:300]}"
        ) from exc

    return _parse_raw_json(raw)


# ─────────────────────────────────────────────
#  FIRST-RUN SETUP SCREEN
# ─────────────────────────────────────────────
def setup_screen():
    st.markdown(f"""
    <div class="app-header">
        <img src="{LOGO_URL}" alt="Energy Viz logo" onerror="this.style.display='none'">
        <div class="titles">
            <h1>Energy Viz</h1>
            <p>{t("app_title")} — {t("first_run_title")}</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Language selector — first thing in setup ──
    st.markdown(f"""
    <div style="background:#1c2330;border:1px solid #30363d;border-radius:12px;
                padding:1rem 1.2rem;margin-bottom:1rem">
        <div style="font-weight:600;font-size:.9rem;color:#e6edf3;margin-bottom:.6rem">
            🌐 Language / Język
        </div>
    </div>""", unsafe_allow_html=True)
    lc1, lc2, _ = st.columns([1, 1, 2])
    with lc1:
        if st.button("🇮🇪 English", use_container_width=True,
                     type="primary" if st.session_state.get("lang","en") == "en" else "secondary",
                     key="setup_lang_en"):
            st.session_state["lang"] = "en"
            st.rerun()
    with lc2:
        if st.button("🇵🇱 Polski", use_container_width=True,
                     type="primary" if st.session_state.get("lang","en") == "pl" else "secondary",
                     key="setup_lang_pl"):
            st.session_state["lang"] = "pl"
            st.rerun()

    st.markdown(f"""
    <div class="setup-card">
        <h3 style="margin:0 0 .5rem;color:#e6edf3">{t("welcome_title")}</h3>
        <p style="color:#7d8590;font-size:.88rem;margin-bottom:.8rem">
            Your settings will be saved to <code style="color:#58a6ff">{DATA_DIR}</code>
            (Docker volume) and survive container restarts and rebuilds.
        </p>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
            <div style="background:#1f3a5f22;border:1px solid #58a6ff44;border-radius:8px;
                        padding:.4rem .8rem;font-size:.75rem;color:#58a6ff">
                💾 {t("persist_tariff")}
            </div>
            <div style="background:#1f3a5f22;border:1px solid #58a6ff44;border-radius:8px;
                        padding:.4rem .8rem;font-size:.75rem;color:#58a6ff">
                📁 {t("persist_hdf")}
            </div>
            <div style="background:#1f3a5f22;border:1px solid #58a6ff44;border-radius:8px;
                        padding:.4rem .8rem;font-size:.75rem;color:#58a6ff">
                📄 {t("persist_invoice")}
            </div>
            <div style="background:#f0883e22;border:1px solid #f0883e44;border-radius:8px;
                        padding:.4rem .8rem;font-size:.75rem;color:#f0883e">
                🔑 {t("persist_api")}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    method = st.radio(
        t("how_tariff"),
        [t("upload_pdf_opt"), t("manual_opt")],
        horizontal=True,
    )

    if method == t("upload_pdf_opt"):
        _setup_pdf()
    else:
        _setup_manual()


def _setup_pdf():
    st.markdown(f"#### 🤖 {t('ai_parser')}")

    st.markdown(f"""
    <div class="alert-box alert-info" style="color:#e6edf3!important">
        ℹ️ {t("api_called_only")}<br><br>
        {t("provider_recs")}<br>
        &nbsp;• <strong>Anthropic Claude</strong> — {t("provider_anthropic")}<br>
        &nbsp;• <strong>Google Gemini</strong> — {t("provider_gemini")}
        (<a href="https://aistudio.google.com" style="color:#58a6ff">aistudio.google.com</a>)<br>
        &nbsp;• <strong>OpenRouter</strong> — {t("provider_openrouter")}
        (<a href="https://openrouter.ai/models" style="color:#58a6ff">openrouter.ai/models</a>)<br>
        &nbsp;• <strong>OpenAI GPT-4o</strong> — {t("provider_openai")}<br><br>
        {t("if_429")}
    </div>""", unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1])
    with col1:
        _provider_display = {
            "Anthropic (Claude 3.5 Sonnet)": "Anthropic (Claude 3.5 Sonnet)",
            "Google (Gemini 2.5 Flash)": "Google (Gemini 2.5 Flash)",
            "Google (Gemini 2.0 Flash)": "Google (Gemini 2.0 Flash)",
            "Google (Gemini 2.0 Flash Lite)": "Google (Gemini 2.0 Flash Lite)",
            "OpenRouter (choose model below)": f"OpenRouter ({t('period_selector').lower()} model)",
            "OpenAI (GPT-4o)": "OpenAI (GPT-4o)",
        }
        _provider_keys = list(PROVIDERS.keys())
        _provider_labels = [_provider_display.get(k, k) for k in _provider_keys]
        _provider_idx = st.selectbox(t("ai_provider"), range(len(_provider_keys)),
                                     format_func=lambda i: _provider_labels[i])
        provider_name = _provider_keys[_provider_idx]
    with col2:
        # Pre-fill from per-provider storage
        saved_keys  = st.session_state.get("api_keys", {})
        provider_code_tmp = PROVIDERS[provider_name]
        default_key = saved_keys.get(provider_code_tmp, "")
        if not default_key:  # legacy fallback
            legacy = st.session_state.get("api_key", "")
            default_key = legacy.split("||")[0] if "||" in legacy else legacy
        display_key = default_key.split("||")[0] if "||" in default_key else default_key
        api_key = st.text_input(t("api_key_label"), value=display_key, type="password",
                                placeholder=t("api_key_placeholder"))

    # ── OpenRouter model selector ──
    provider_code = PROVIDERS[provider_name]
    or_model = ""
    # ── OpenRouter model info ──
    if provider_code == "openrouter":
        st.markdown(f"""
        <div style="background:#1c2330;border:1px solid #30363d;
                    border-left:3px solid #58a6ff;border-radius:10px;
                    padding:.7rem 1rem;margin:.4rem 0;font-size:.82rem;color:#e6edf3">
            🔀 <strong>OpenRouter</strong> — {t("openrouter_info")}
            <a href="https://openrouter.ai/models" style="color:#58a6ff" target="_blank">openrouter.ai/models</a>.<br>
            {t("openrouter_free")}<br>
            <code>google/gemini-2.5-flash-lite</code> &nbsp;·&nbsp;
            <code>google/gemini-2.5-pro:free</code> &nbsp;·&nbsp;
            <code>anthropic/claude-3.5-sonnet</code>
        </div>""", unsafe_allow_html=True)
        # Restore saved model from per-provider key storage
        saved_or_full  = st.session_state.get("api_keys", {}).get("openrouter", "")
        saved_or_model = saved_or_full.split("||")[1] if "||" in saved_or_full else ""
        or_model = st.text_input(
            t("openrouter_model_id"),
            value=saved_or_model or "google/gemini-2.5-flash-lite",
            placeholder="provider/model-name",
        )
        api_key_effective = f"{api_key}||{or_model}" if or_model else api_key
    else:
        api_key_effective = api_key

    # ── API key storage toggle ──────────────────────
    already_saved_to_disk = API_KEY_FILE.exists()

    st.markdown(f"""
    <div style="background:#1c2330;border:1px solid #30363d;
                border-radius:10px;padding:.8rem 1rem;margin:.6rem 0">
        <div style="font-weight:600;font-size:.88rem;color:#e6edf3!important;margin-bottom:.4rem">
            {t("api_key_privacy_hdr")}
        </div>
        <div style="font-size:.78rem;color:#e6edf3!important">
            {t("api_key_privacy_sub")}
        </div>
    </div>""", unsafe_allow_html=True)

    api_storage = st.radio(
        "api_storage_radio",
        [
            t("session_only"),
            t("save_to_disk"),
        ],
        index=1 if already_saved_to_disk else 0,
        label_visibility="collapsed",
    )
    save_api_to_disk = api_storage.startswith("💾")

    if save_api_to_disk:
        fernet_ok = _fernet() is not None
        if fernet_ok:
            st.markdown(f"""
            <div class="alert-box alert-warn">
                ⚠️ {t("aes_warn")}
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="alert-box alert-red">
                🚨 <code>cryptography</code> not installed — key cannot be encrypted.
                Add <code>cryptography&gt;=42.0</code> to requirements.txt.
            </div>""", unsafe_allow_html=True)
            save_api_to_disk = False
    else:
        st.markdown(f"""
        <div class="alert-box alert-info" style="color:#e6edf3!important">
            ℹ️ {t("session_key_info")}
        </div>""", unsafe_allow_html=True)

    if already_saved_to_disk:
        if st.button(t("delete_api_key")):
            API_KEY_FILE.unlink(missing_ok=True)
            st.session_state["api_key"] = ""
            st.success(t("saved_api_deleted"))
            st.rerun()

    pdf_file = st.file_uploader(t("upload_invoice"), type=["pdf"])

    if pdf_file and api_key:
        if st.button(t("extract_btn")):
            with st.spinner(f"{t('analysing_invoice')} {provider_name}…"):
                try:
                    pdf_bytes = pdf_file.getvalue()
                    data = parse_invoice_ai(pdf_bytes, provider_code, api_key_effective)
                    INVOICE_FILE.write_bytes(pdf_bytes)
                    # Save API key per-provider
                    st.session_state["api_keys"][provider_code] = api_key_effective
                    st.session_state["api_key"]      = api_key_effective  # legacy compat
                    st.session_state["api_provider"] = provider_code
                    if save_api_to_disk:
                        enc = encrypt_api_key(api_key_effective)
                        if enc:
                            API_KEY_FILE.write_bytes(enc)
                    _apply_extracted(data)
                    # ── flag to show review form on next render ──
                    st.session_state["_show_review"] = True
                    st.rerun()
                except Exception as e:
                    err_msg = str(e)
                    if err_msg.startswith("**"):
                        st.markdown(f"""
                        <div class="alert-box alert-red">
                            🚨 {err_msg.replace(chr(10), '<br>')}
                        </div>""", unsafe_allow_html=True)
                    else:
                        st.error(f"Extraction failed: {err_msg}")
                    st.info(t("enter_manually_tip"))
    elif pdf_file:
        st.info(t("enter_api_key"))
    else:
        st.info(t("upload_pdf_first"))

    # ── Show review form if extraction succeeded (persists across rerenders) ──
    if st.session_state.get("_show_review") and st.session_state.get("_extracted"):
        st.success(t("extraction_ok"))
        _show_extracted_review()

    with st.expander(t("or_manually")):
        _setup_manual(inside_expander=True)


def _apply_extracted(data: dict):
    st.session_state["_extracted"] = data


def _show_extracted_review():
    data = st.session_state.get("_extracted", {})
    st.markdown(f"#### {t('review_extracted')}")

    c1, c2 = st.columns(2)
    with c1:
        mprn     = st.text_input(t("mprn_optional"),     value=str(data.get("mprn") or ""))
        supplier = st.text_input(t("supplier_name"), value=str(data.get("supplier") or ""))
        tariff   = st.text_input(t("tariff_label"),   value=str(data.get("tariff_name") or ""))
    with c2:
        r_day   = st.number_input(t("day_rate_label"),      value=float(data.get("rate_day")        or DEFAULT_TARIFF["day"]),     step=0.001, format="%.4f")
        r_peak  = st.number_input(t("peak_rate_label"),     value=float(data.get("rate_peak")       or DEFAULT_TARIFF["peak"]),    step=0.001, format="%.4f")
        r_night = st.number_input(t("night_rate_label"),    value=float(data.get("rate_night")      or DEFAULT_TARIFF["night"]),   step=0.001, format="%.4f")
        r_stand = st.number_input(t("standing_label"), value=float(data.get("standing_charge") or DEFAULT_TARIFF["standing"]),step=0.001, format="%.4f")

    st.markdown(f"#### {t('billing_period_hdr')}")
    alert(f'{t("billing_period_hdr")} — {t("billing_period_start")}', "info")

    extracted_end = data.get("billing_period_end")
    default_start = None
    default_days  = int(data.get("billing_period_days") or 60)
    if extracted_end:
        try:
            from datetime import datetime, timedelta, date
            parsed = datetime.strptime(str(extracted_end), "%d %b %y").date()
            default_start = parsed + timedelta(days=1)
        except Exception:
            pass

    from datetime import date as dt_date, timedelta
    today = dt_date.today()
    b1, b2 = st.columns(2)
    with b1:
        b_start = st.date_input(t("billing_period_start"), value=default_start or today)
        b_days  = st.number_input(t("billing_cycle_days"), value=default_days, min_value=14, max_value=120, step=1)
    with b2:
        b_end = b_start + timedelta(days=b_days)
        st.markdown(f"""
        <div style="background:#1c2330;border:1px solid #30363d;border-radius:10px;
                    padding:1rem;margin-top:1.7rem">
            <div style="font-size:.7rem;text-transform:uppercase;color:#7d8590">Expected billing date</div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:1.3rem;color:#58a6ff;margin:.3rem 0">
                {fmt_date(b_end)}
            </div>
            <div style="font-size:.78rem;color:#7d8590">
                {t("days_from_today_lbl").format(n=(b_end - dt_date.today()).days)}
            </div>
        </div>""", unsafe_allow_html=True)

    if st.button(t("confirm_continue")):
        st.session_state["tariff"]        = dict(day=r_day, peak=r_peak, night=r_night, standing=r_stand)
        st.session_state["mprn"]          = mprn
        st.session_state["supplier"]      = supplier
        st.session_state["billing_start"] = b_start
        st.session_state["billing_end"]   = b_end
        st.session_state["billing_days"]  = int(b_days)
        st.session_state["setup_done"]    = True
        st.session_state["_show_review"]  = False   # clear flag
        save_config()
        st.rerun()


def _setup_manual(inside_expander=False):
    if not inside_expander:
        st.markdown(f"#### ✏️ {t('manual_entry')}")

    form_key = "manual_setup_expander" if inside_expander else "manual_setup"
    with st.form(form_key):
        c1, c2 = st.columns(2)
        with c1:
            mprn     = st.text_input(t("mprn_optional"), placeholder=t("mprn_placeholder"))
            supplier = st.text_input(t("supplier_name"),   placeholder=t("supplier_placeholder"))
        with c2:
            r_day   = st.number_input(t("day_rate_label"),      value=DEFAULT_TARIFF["day"],      step=0.001, format="%.4f")
            r_peak  = st.number_input(t("peak_rate_label"),     value=DEFAULT_TARIFF["peak"],     step=0.001, format="%.4f")
            r_night = st.number_input(t("night_rate_label"),    value=DEFAULT_TARIFF["night"],    step=0.001, format="%.4f")
            r_stand = st.number_input(t("standing_label"), value=DEFAULT_TARIFF["standing"], step=0.001, format="%.4f")
    
        st.markdown(t("billing_period_opt"))
        from datetime import date as dt_date, timedelta
        b1, b2 = st.columns(2)
        with b1:
            b_start = st.date_input(t("billing_period_start"), value=None,
                                    help="Leave empty to skip — prediction tab will be unavailable")
            b_days  = st.number_input(t("billing_cycle_days"), value=60, min_value=14, max_value=120, step=1)
        with b2:
            st.markdown(f"""
            <div style="background:#1c2330;border:1px solid #30363d;border-radius:10px;
                        padding:1rem;margin-top:1.7rem;font-size:.82rem;color:#7d8590">
                {t("billing_tip")}
            </div>""", unsafe_allow_html=True)

        st.markdown(f"""
        <div class="alert-box alert-info" style="margin-top:.5rem">
            {t("default_rates_tip")}
        </div>""", unsafe_allow_html=True)

        submitted = st.form_submit_button(t("save_continue"))
        if submitted:
            b_end = (b_start + timedelta(days=int(b_days))) if b_start else None
            st.session_state["tariff"]        = dict(day=r_day, peak=r_peak, night=r_night, standing=r_stand)
            st.session_state["mprn"]          = mprn
            st.session_state["supplier"]      = supplier
            st.session_state["billing_start"] = b_start
            st.session_state["billing_end"]   = b_end
            st.session_state["billing_days"]  = int(b_days)
            st.session_state["setup_done"]    = True
            save_config()   # ← persist to /app/data/config.json
            st.rerun()


# ─────────────────────────────────────────────
#  SHOW SETUP SCREEN IF NOT CONFIGURED YET
# ─────────────────────────────────────────────
if not st.session_state["setup_done"]:
    setup_screen()
    st.stop()

# ─────────────────────────────────────────────
#  RESOLVED TARIFF VALUES  (from session)
# ─────────────────────────────────────────────
T           = st.session_state["tariff"]
TARIFF_DAY  = T["day"]
TARIFF_PEAK = T["peak"]
TARIFF_NIGHT= T["night"]
STANDING_DAY= T["standing"]
DISC_PCT    = 0.0
DISC_FACTOR = 1.0  # rates from invoice are already post-discount

# ─────────────────────────────────────────────
#  DATA LOADERS
# ─────────────────────────────────────────────
def _dedup_hdf(df: pd.DataFrame, value_col: str = "Read Value") -> tuple[pd.DataFrame, dict]:
    """
    Deduplicate ESB HDF export rows correctly:

    ESB always exports the FULL available history (up to 13 months) in each download.
    This means:
    - Uploading a newer export already includes all old data + new months + any corrections.
    - No manual merging of files is needed — just replace with the newest export.

    Within a single file, duplicate timestamps can appear for two legitimate reasons:
    1. DST clock-back (Oct): 01:00 and 01:30 each appear twice — BOTH are valid real slots.
    2. True duplicates: identical MPRN + timestamp + value — safe to remove (export artifact).

    ESB corrections (revised readings for old timestamps) would show up as same MPRN +
    same timestamp but different value. Within a single export ESB always provides
    the corrected value only, so no action needed — the file is already clean.

    Strategy:
    - Sort chronologically.
    - For rows with identical (MPRN, timestamp): keep ALL if values differ (DST).
    - Drop rows where MPRN + timestamp + value are all identical (exact duplicate).
    """
    before = len(df)

    # Drop rows where MPRN + timestamp + raw value are 100% identical
    df = df.drop_duplicates(
        subset=["MPRN", "Read Date and End Time", value_col], keep="first"
    ).reset_index(drop=True)

    after  = len(df)
    removed = before - after

    # Count remaining timestamp duplicates (these are legitimate DST slots)
    ts_dupes = df.duplicated(subset=["MPRN", "Read Date and End Time"], keep=False).sum()

    report = {
        "rows_raw":     before,
        "rows_clean":   after,
        "exact_dupes_removed": removed,
        "dst_slots":    ts_dupes,   # pairs of legitimate DST clock-back readings
    }
    return df, report



def _open_hdf(file_or_path):
    """Accept either an uploaded file widget or a path string."""
    if isinstance(file_or_path, str):
        # Return BytesIO so file handle is not left open
        return io.BytesIO(Path(file_or_path).read_bytes())
    return file_or_path  # UploadedFile or BytesIO

@st.cache_data(show_spinner=False, hash_funcs={io.BytesIO: lambda x: x.getvalue()})
def load_calc_kwh(file):
    df = pd.read_csv(_open_hdf(file))
    df.columns = df.columns.str.strip()
    df["datetime"] = pd.to_datetime(df["Read Date and End Time"], dayfirst=True)
    df = df.sort_values("datetime").reset_index(drop=True)
    df["value"]   = pd.to_numeric(df["Read Value"], errors="coerce")

    # ── Deduplication ──
    df, _report = _dedup_hdf(df)

    df["hour"]    = df["datetime"].dt.hour
    df["minute"]  = df["datetime"].dt.minute
    df["date"]    = df["datetime"].dt.date
    df["weekday"] = df["datetime"].dt.weekday
    df["month"]   = df["datetime"].dt.to_period("M").astype(str)
    df["period"]  = df.apply(lambda r: get_period(r["hour"], r["minute"]), axis=1)
    tmap = {"day": TARIFF_DAY, "peak": TARIFF_PEAK, "night": TARIFF_NIGHT}
    df["cost"]     = df["value"] * df["period"].map(tmap)
    df["cost_net"] = df["cost"] * DISC_FACTOR
    daily = df.groupby("date")["value"].sum().rename("daily_kwh")
    df = df.merge(daily, on="date", how="left")

    # Attach quality report as attribute via session state key
    st.session_state["_qr_calc"] = _report
    return df


@st.cache_data(show_spinner=False, hash_funcs={io.BytesIO: lambda x: x.getvalue()})
def load_kw(file):
    df = pd.read_csv(_open_hdf(file))
    df.columns = df.columns.str.strip()
    df["datetime"] = pd.to_datetime(df["Read Date and End Time"], dayfirst=True)
    df = df.sort_values("datetime").reset_index(drop=True)
    df["value"] = pd.to_numeric(df["Read Value"], errors="coerce")
    df, _report = _dedup_hdf(df)
    df["date"]  = df["datetime"].dt.date
    df["hour"]  = df["datetime"].dt.hour
    st.session_state["_qr_kw"] = _report
    return df


@st.cache_data(show_spinner=False, hash_funcs={io.BytesIO: lambda x: x.getvalue()})
def load_dnp(file):
    df = pd.read_csv(_open_hdf(file))
    df.columns = df.columns.str.strip()
    df["datetime"] = pd.to_datetime(df["Read Date and End Time"], dayfirst=True)
    df = df.sort_values("datetime").reset_index(drop=True)
    df["value"] = pd.to_numeric(df["Read Value"], errors="coerce")
    df, _report = _dedup_hdf(df)
    df["date"]  = df["datetime"].dt.date
    df["type"]  = df["Read Type"].str.strip()
    st.session_state["_qr_dnp"] = _report
    return df


@st.cache_data(show_spinner=False, hash_funcs={io.BytesIO: lambda x: x.getvalue()})
def load_daily(file):
    df = pd.read_csv(_open_hdf(file))
    df.columns = df.columns.str.strip()
    df["datetime"] = pd.to_datetime(df["Read Date and End Time"], dayfirst=True)
    df = df.sort_values("datetime").reset_index(drop=True)
    df["value"] = pd.to_numeric(df["Read Value"], errors="coerce")
    df, _report = _dedup_hdf(df)
    df["date"]   = df["datetime"].dt.date
    # Remove meter rollover outliers (e.g. 9,311,406 kWh artifact)
    median_val   = df["value"].median()
    outliers     = (df["value"] >= median_val * 10).sum()
    df = df[df["value"] < median_val * 10].copy()
    df["daily"]  = df["value"].diff().clip(lower=0)
    _report["outliers_removed"] = int(outliers)
    st.session_state["_qr_daily"] = _report
    return df

# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    # ── Language toggle ──
    lang_col1, lang_col2 = st.columns(2)
    with lang_col1:
        if st.button("🇮🇪 English", use_container_width=True,
                     type="primary" if st.session_state.get("lang","en") == "en" else "secondary"):
            st.session_state["lang"] = "en"
            save_config()
            st.rerun()
    with lang_col2:
        if st.button("🇵🇱 Polski", use_container_width=True,
                     type="primary" if st.session_state.get("lang","en") == "pl" else "secondary"):
            st.session_state["lang"] = "pl"
            save_config()
            st.rerun()

    st.markdown("<div style='margin-bottom:.5rem'></div>", unsafe_allow_html=True)

    # Logo
    st.markdown(f"""
    <div class="sb-logo">
        <img src="{LOGO_URL}" alt="logo" onerror="this.style.display='none'">
        <div>
            <div class="lname">Energy Viz</div>
            <div class="lsub">Smart Meter Dashboard</div>
        </div>
    </div>""", unsafe_allow_html=True)

    # ── HDF file uploads — compact design ──
    st.markdown(f'<div style="font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:{COLORS["muted"]};margin-bottom:.5rem">📂 {t("hdf_files")}</div>', unsafe_allow_html=True)

    # Helper: show persisted file status below each uploader
    def _file_card(slot, color, icon, label, hint, primary=False):
        info = hdf_file_info(slot)
        border = f"border-left:3px solid {color}"
        bg = "background:linear-gradient(135deg,#1a2a3a,#1c2330)" if primary else "background:#1c2330"
        badge = f'<span style="font-size:.6rem;background:{color}22;color:{color};padding:1px 5px;border-radius:8px;margin-left:auto;border:1px solid {color}44">{t("sidebar_primary") if primary else t("sidebar_optional")}</span>'
        # File status line
        if info:
            fname = info["path"].split("/")[-1]
            # truncate long filename
            if len(fname) > 22: fname = fname[:10] + "…" + fname[-8:]
            status = f'<div style="margin-top:.3rem;font-size:.65rem;background:{COLORS["bg3"]};border:1px solid {COLORS["border"]};border-radius:5px;padding:2px 6px;color:#58a6ff">💾 {fname}</div>'
        else:
            status = f'<div style="margin-top:.3rem;font-size:.65rem;color:#30363d">○ not loaded</div>'
        st.markdown(f"""
        <div style="{bg};{border};border-radius:8px;padding:.5rem .7rem;margin-bottom:.3rem">
            <div style="display:flex;align-items:center;gap:5px">
                <span style="font-size:.8rem">{icon}</span>
                <span style="font-weight:600;font-size:.78rem;color:{color}">{label}</span>
                {badge}
            </div>
            <div style="font-size:.65rem;color:#7d8590;margin-top:1px">{hint}</div>
            {status}
        </div>""", unsafe_allow_html=True)

    _file_card("calc",  "#58a6ff", "⭐", "30-min kWh", "HDF_calckWh_…csv", primary=True)
    f_calc = st.file_uploader("calckWh", type="csv", key="calc", label_visibility="collapsed")

    _file_card("kw",    "#39d0d8", "⚡", t("power_title"), "HDF_kW_…csv")
    f_kw = st.file_uploader("kW", type="csv", key="kw", label_visibility="collapsed")

    _file_card("dnp",   "#bc8cff", "🌙", t("daily_dnp_label"), "HDF_DailyDNP_kWh_…csv")
    f_dnp = st.file_uploader("DNP", type="csv", key="dnp", label_visibility="collapsed")

    _file_card("daily", "#3fb950", "📅", "kWh", "HDF_Daily_kWh_…csv")
    f_daily = st.file_uploader("Daily", type="csv", key="daily", label_visibility="collapsed")

    # ── Upload status summary + persistence ──
    # Save any newly uploaded files to disk immediately
    for slot, file_widget in [("calc",f_calc),("kw",f_kw),("dnp",f_dnp),("daily",f_daily)]:
        if file_widget is not None:
            save_hdf_file(slot, file_widget)

    # Build status line showing uploaded + persisted
    def _slot_status(slot, uploaded):
        info = hdf_file_info(slot)
        if uploaded:
            return f'<span style="color:#3fb950">✅ {slot}</span>'
        elif info:
            return f'<span style="color:{COLORS["muted"]}">💾 {slot} <span style="font-size:.65rem">({info["modified"]})</span></span>'
        else:
            return f'<span style="color:#30363d">○ {slot} — {t("not_loaded")}</span>'

    status_html = " · ".join([
        _slot_status("calc",  f_calc),
        _slot_status("kw",    f_kw),
        _slot_status("dnp",   f_dnp),
        _slot_status("daily", f_daily),
    ])
    st.markdown(
        f'<div style="font-size:.7rem;margin-top:.4rem;line-height:1.8">{status_html}</div>'
        f'<div style="font-size:.65rem;color:#30363d;margin-top:2px">'
        f'✅ {t("just_uploaded")} &nbsp;·&nbsp; 💾 {t("saved_session")} &nbsp;·&nbsp; ○ {t("not_available")}'
        f'</div>',
        unsafe_allow_html=True,
    )

    if not f_calc and not hdf_file_info("calc"):
        st.markdown(
            f'<div style="font-size:.72rem;color:#f0883e;margin-top:.3rem">'
            f'⚠️ {t("upload_calc_first")}</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Tariff rates (editable — save on change) ──
    st.markdown(f"##### 🧾 {t('tariff_rates')}")
    t_day   = st.number_input(t("day_rate"),           value=TARIFF_DAY,   step=0.001, format="%.4f")
    t_peak  = st.number_input(t("peak_rate"),          value=TARIFF_PEAK,  step=0.001, format="%.4f")
    t_night = st.number_input(t("night_rate"),         value=TARIFF_NIGHT, step=0.001, format="%.4f")
    t_stand = st.number_input(t("standing_rate"),  value=STANDING_DAY, step=0.001, format="%.4f")
    # Persist rate edits immediately
    if (t_day   != TARIFF_DAY   or t_peak  != TARIFF_PEAK or
        t_night != TARIFF_NIGHT or t_stand != STANDING_DAY):
        st.session_state["tariff"] = dict(day=t_day, peak=t_peak, night=t_night, standing=t_stand)
        save_config()

    # ── ESB Auto-Sync ──
    st.divider()
    st.markdown(f"##### 🔄 {t('esb_sync_title')}")

    _sync_email, _sync_pass = decrypt_esb_creds()
    _has_creds = bool(_sync_email and _sync_pass)

    # Show sync status
    _sync_st = read_sync_status()
    if _sync_st:
        _last = _sync_st.get("last_attempt", "")[:16].replace("T", " ")
        if _sync_st.get("success"):
            _files = ", ".join(_sync_st.get("files_updated", []))
            st.markdown(
                f'<div class="alert-box alert-good" style="font-size:.75rem;padding:.4rem .7rem">'
                f'✅ {_last}<br><span style="opacity:.8">{t("esb_sync_files")}: {_files}</span></div>',
                unsafe_allow_html=True
            )
        else:
            _err = _sync_st.get("error", "unknown")
            if _err == "rate_limited":
                _msg = t("esb_sync_rate_limit")
            elif _err == "login_failed":
                _msg = t("esb_sync_login_fail")
            elif _err == "no_credentials":
                _msg = t("esb_sync_no_creds")
            else:
                _msg = f'{t("esb_sync_fail")}: {_err}'
            st.markdown(
                f'<div class="alert-box alert-warn" style="font-size:.75rem;padding:.4rem .7rem">'
                f'{_msg}<br><span style="opacity:.7">{_last}</span></div>',
                unsafe_allow_html=True
            )
    else:
        if _has_creds:
            st.caption(t("esb_sync_weekly"))
        else:
            st.caption(t("esb_sync_no_creds"))

    # Credentials form
    with st.expander(t("esb_creds_stored") if _has_creds else "🔑 " + t("esb_sync_email"), expanded=not _has_creds):
        _new_email = st.text_input(t("esb_sync_email"), value=_sync_email, key="esb_email_input",
                                   placeholder="name@example.com")
        _new_pass  = st.text_input(t("esb_sync_password"), value=_sync_pass, key="esb_pass_input",
                                   type="password", placeholder="••••••••")
        _c1, _c2 = st.columns(2)
        with _c1:
            if st.button(t("esb_sync_save"), use_container_width=True, key="esb_save_btn"):
                if _new_email and _new_pass:
                    _enc = encrypt_esb_creds(_new_email, _new_pass)
                    if _enc:
                        ESB_CREDS_FILE.write_bytes(_enc)
                        # Reset sync status so scheduler runs soon
                        if SYNC_STATUS_FILE.exists():
                            SYNC_STATUS_FILE.unlink()
                        st.success(t("esb_sync_creds_saved"))
                        st.rerun()
        with _c2:
            if _has_creds and st.button(t("esb_sync_clear"), use_container_width=True, key="esb_clear_btn"):
                ESB_CREDS_FILE.unlink(missing_ok=True)
                st.rerun()

    # Manual sync button
    if _has_creds:
        if st.button(t("esb_sync_now"), use_container_width=True, key="esb_sync_now_btn"):
            with st.spinner(t("esb_sync_running")):
                _result = esb_sync_now(DATA_DIR, HDF_SLOTS, ESB_CREDS_FILE, SYNC_STATUS_FILE, _fernet)
            st.rerun()

    # ── Update / reset ──
    st.divider()
    st.markdown(f"##### 🔄 {t('configuration')}")
    if st.button(t("reparse_btn"), use_container_width=True):
        st.session_state["setup_done"] = False
        st.rerun()
    if st.button(t("clear_btn"), use_container_width=True):
        if st.session_state.get("_confirm_clear"):
            import shutil as _shutil
            _shutil.rmtree(DATA_DIR, ignore_errors=True)
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            HDF_DIR.mkdir(parents=True, exist_ok=True)
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
        else:
            st.session_state["_confirm_clear"] = True
            st.warning(t("press_confirm"))

    # ── Tariff donut placeholder ──
    sidebar_chart_slot = st.empty()

# ─────────────────────────────────────────────
#  HEADER  (with logo)
# ─────────────────────────────────────────────

st.markdown(f"""
<div class="app-header">
    <img src="{LOGO_URL}" alt="Energy Viz" onerror="this.style.display='none'">
    <div class="titles">
        <h1>{t("app_title")}</h1>
        <p>{t("app_subtitle")}</p>
    </div>
</div>
""", unsafe_allow_html=True)

# Inject Polish month names into Plotly axes if needed
_inject_pl_month_names()

# ─────────────────────────────────────────────
#  TABS
# Rebuild theme-dependent objects on every rerun
COLORS = _build_colors()
PLOTLY_BASE = _build_plotly_base()
RANGESLIDER_X = _build_rangeslider_x()

# ─────────────────────────────────────────────
tabs = st.tabs([
    t("tab_overview"), t("tab_consumption"), t("tab_power"),
    t("tab_daily"), t("tab_cost"), t("tab_insights"),
    t("tab_prediction"), t("tab_raw"),
])

# ── Guard: no files (neither uploaded nor persisted) ──
_any_persisted = any(hdf_file_info(s) for s in ["calc","kw","dnp","daily"])
if not any([f_calc, f_dnp, f_kw, f_daily]) and not _any_persisted:
    with tabs[0]:
        st.markdown("<br>", unsafe_allow_html=True)
        # ── Hero ──
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            st.markdown(f"""
<div style="text-align:center;padding:2rem 1.5rem;background:#161b22;
            border-radius:16px;border:1px dashed #30363d">
<img src="{LOGO_URL}" style="height:52px;margin-bottom:.8rem"
     onerror="this.style.display:none">
<h2 style="color:#e6edf3;margin:.3rem 0 .5rem">Upload HDF files to begin</h2>
<p style="color:#7d8590;font-size:.84rem;margin:0 auto;max-width:360px">
Download CSV exports from the
<a href="https://myaccount.esbnetworks.ie/Api/HistoricConsumption"
   style="color:#58a6ff" target="_blank">smart meter portal</a>
and upload them using the sidebar on the left.
</p>
</div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ── File type cards ──
        ca, cb, cc, cd = st.columns(4)
        for col, icon, color, title, fname, desc in [
            (ca, "⭐", "#58a6ff", "calckWh",    "HDF_calckWh_…csv",        "30-min kWh · Day/Peak/Night · **required**"),
            (cb, "⚡", "#39d0d8", "kW Demand",  "HDF_kW_…csv",             "Instantaneous kW · spike detection"),
            (cc, "🌙", "#bc8cff", t("daily_dnp_label"),  "HDF_DailyDNP_kWh_…csv",  "Cumulative registers · invoice check"),
            (cd, "📅", "#3fb950", "kWh",  "HDF_Daily_kWh_…csv",     "24h total · long-range trend"),
        ]:
            with col:
                st.markdown(f"""
<div style="background:#161b22;border:1px solid #30363d;
            border-top:3px solid {color};border-radius:10px;padding:.8rem;height:100%">
<div style="font-weight:700;font-size:.82rem;color:{color};margin-bottom:.3rem">{icon} {title}</div>
<div style="font-size:.68rem;color:#7d8590;font-family:monospace;margin-bottom:.4rem">{fname}</div>
<div style="font-size:.72rem;color:#a0aab4">{desc}</div>
</div>""", unsafe_allow_html=True)

    st.stop()

# ── Load data — uploaded file takes priority, fallback to persisted ──
def _resolve(uploaded, slot):
    """Return uploaded file if present, else return path string for persisted file."""
    if uploaded is not None:
        return uploaded
    path = HDF_SLOTS[slot]
    if path.exists():
        return str(path)   # return path string — stable cache key across restarts
    return None

src_calc  = _resolve(f_calc,  "calc")
src_kw    = _resolve(f_kw,    "kw")
src_dnp   = _resolve(f_dnp,   "dnp")
src_daily = _resolve(f_daily, "daily")

df_calc  = load_calc_kwh(src_calc)  if src_calc  else None
df_kw    = load_kw(src_kw)          if src_kw    else None
df_dnp   = load_dnp(src_dnp)        if src_dnp   else None
df_daily = load_daily(src_daily)    if src_daily else None

disc_factor = DISC_FACTOR  # always apply configured discount
# Recalculate costs if sidebar rates were changed
if df_calc is not None:
    tmap = {"day": t_day, "peak": t_peak, "night": t_night}
    df_calc["cost"]     = df_calc["value"] * df_calc["period"].map(tmap)
    df_calc["cost_net"] = df_calc["cost"] * disc_factor

# ── Sidebar donut ──
if df_calc is not None:
    with sidebar_chart_slot.container():
        st.divider()
        st.markdown(f'<p style="color:{COLORS["muted"]};font-size:.7rem;text-transform:uppercase;'
                    f'letter-spacing:.08em;margin-bottom:4px">⚡ {t("tariff_split_header")}</p>',
                    unsafe_allow_html=True)
        by_p   = df_calc.groupby("period")["value"].sum()
        tot_sb = by_p.sum()
        fig_sb = go.Figure(go.Pie(
            labels=[{'day': t("legend_day"), 'peak': t("legend_peak"), 'night': t("legend_night")}.get(p, p.capitalize()) for p in by_p.index],
            values=by_p.values,
            hole=0.60,
            marker=dict(colors=[COLORS.get(p,"#888") for p in by_p.index],
                        line=dict(color="#0d1117", width=2)),
            textinfo="label+percent",
            textfont=dict(size=10, color=COLORS["text"]),
            direction="clockwise", sort=False,
            hovertemplate="<b>%{label}</b><br>%{value:.1f} kWh · %{percent}<extra></extra>",
        ))
        fig_sb.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Space Grotesk", color=COLORS["text"], size=10),
            showlegend=False, margin=dict(l=0,r=0,t=0,b=0), height=185,
            annotations=[dict(
                text=f"<b>{tot_sb:,.0f}</b><br><span style='font-size:9px'>kWh</span>",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=13, color=COLORS["text"]),
            )],
        )
        st.plotly_chart(fig_sb, use_container_width=True, config={"displayModeBar": False})
        for p_key, p_lbl, color in [("day", t("legend_day"), COLORS["day"]),
                                     ("peak", t("legend_peak"), COLORS["peak"]),
                                     ("night", t("legend_night"), COLORS["night"])]:
            kwh = by_p.get(p_key, 0)
            pct = kwh / tot_sb * 100 if tot_sb else 0
            st.markdown(
                f'<div class="tariff-row">'
                f'<div class="tariff-dot" style="background:{color}"></div>'
                f'<span style="color:{COLORS["muted"]}">{p_lbl}</span>'
                f'<span style="margin-left:auto;font-family:\'JetBrains Mono\',monospace;'
                f'color:{color}">{pct:.1f}%</span>'
                f'<span style="color:{COLORS["muted"]};font-size:.7rem">{kwh:.0f} kWh</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        # Show MPRN only if user entered it
        if st.session_state.get("mprn"):
            st.markdown(
                f'<p style="color:{COLORS["muted"]};font-size:.7rem;text-align:center;'
                f'margin-top:8px">MPRN: {st.session_state["mprn"]}</p>',
                unsafe_allow_html=True,
            )


# ════════════════════════════════════════════
#  TAB 0 — OVERVIEW
# ════════════════════════════════════════════
with tabs[0]:
    # ── Period selector ──
    ov_col1, ov_col2 = st.columns([3, 1])
    with ov_col1:
        section("📌", t("key_metrics"))
    with ov_col2:
        ov_period_idx = st.radio(t("period_selector"),
                             [t("period_week"), t("period_month"), t("period_bill"), t("period_total")],
                             index=3, horizontal=True, label_visibility="collapsed",
                             key="ov_period")
        # Map by index position (language-independent)
        _period_opts = [t("period_week"), t("period_month"), t("period_bill"), t("period_total")]
        ov_period_i = _period_opts.index(ov_period_idx) if ov_period_idx in _period_opts else 3

    # Filter data by selected period
    if df_calc is not None:
        now = df_calc["datetime"].max()
        if ov_period_i == 0:    # Week
            ov_cutoff = now - pd.Timedelta(days=7)
        elif ov_period_i == 1:  # Month
            ov_cutoff = now - pd.Timedelta(days=30)
        elif ov_period_i == 2 and st.session_state.get("billing_start"):  # Bill
            ov_cutoff = pd.Timestamp(st.session_state["billing_start"])
        else:  # Total
            ov_cutoff = df_calc["datetime"].min()
        df_ov = df_calc[df_calc["datetime"] >= ov_cutoff]
    else:
        df_ov = None

    kpis = []
    if df_ov is not None and len(df_ov):
        total_kwh  = df_ov["value"].sum()
        total_cost = df_ov["cost"].sum() * disc_factor
        days_data  = max((df_ov["datetime"].max() - df_ov["datetime"].min()).days, 1)
        avg_daily_kwh  = total_kwh / days_data
        avg_daily_cost = total_cost / days_data
        standby    = df_ov[df_ov["hour"].isin([2,3])]["value"].mean()
        kpis.append(kpi_html(t("total_consumption"),  f"{total_kwh:,.0f}", "kWh", "blue"))
        kpis.append(kpi_html(t("daily_average"),       f"{avg_daily_kwh:.1f}", t("kwh_day_unit"), "green"))
        kpis.append(kpi_html(t("energy_cost"),        f"€{total_cost:,.2f}",
                              "", "orange"))
        kpis.append(kpi_html(t("avg_daily_cost"),     f"€{avg_daily_cost:.2f}", t("per_day"), "cyan"))
        kpis.append(kpi_html(t("data_span"),           f"{days_data}", t("days_label"), "purple"))
        kpis.append(kpi_html(t("standby_load"),        f"{standby*2*1000:.0f}", t("w_standby"), "red"))
    if df_kw is not None:
        kpis.append(kpi_html(t("peak_demand"), f"{df_kw['value'].max():.2f}", "kW", "red"))
    st.markdown('<div class="kpi-row">' + "".join(kpis) + '</div>', unsafe_allow_html=True)

    if df_calc is not None:
        incomplete = (df_calc.groupby("date").size() < 48).sum()
        if incomplete:
            _dst_msg = t("dst_warning").format(n=f"<strong>{incomplete}</strong>", k=44)
            alert(_dst_msg, "warn")
    if df_daily is not None and st.session_state.get("_qr_daily", {}).get("outliers_removed"):
        alert(t("outlier_warning"), "red")

    st.divider()

    if df_ov is not None and len(df_ov):
        section("📈", t("daily_energy"), badge=ov_period_idx)
        dp = df_ov.groupby(["date","period"])["value"].sum().reset_index()
        dpiv = dp.pivot(index="date", columns="period", values="value").fillna(0).reset_index()
        for c in ["day","peak","night"]:
            if c not in dpiv.columns: dpiv[c] = 0
        roll7 = dpiv[["day","peak","night"]].sum(axis=1).rolling(7, min_periods=1).mean()

        fig = go.Figure()
        for p, color, label in [
            ("night",COLORS["night"],f"🌙 {t('night_label_chart')}"),
            ("day",  COLORS["day"],  f"☀️ {t('day_label_chart')}"),
            ("peak", COLORS["peak"], f"🔥 {t('peak_label_chart')}"),
        ]:
            fig.add_trace(go.Bar(x=dpiv["date"], y=dpiv[p], name=label,
                                 marker_color=color, marker_line_width=0))
        fig.add_trace(go.Scatter(x=dpiv["date"], y=roll7, name=t("seven_day_avg"), mode="lines",
                                 line=dict(color=COLORS["yellow"], width=2, dash="dot")))
        apply_layout(fig, "", height=360)
        fig.update_layout(barmode="stack", yaxis_title="kWh")
        st.plotly_chart(fig, use_container_width=True)

    if df_calc is not None:
        # Use filtered data matching selected period
        _split_df = df_ov if df_ov is not None and len(df_ov) else df_calc
        _split_label = ov_period_idx if ov_period_idx else t("period_total")
        section("🎯", t("tariff_split_full"), badge=_split_label)
        by_p = _split_df.groupby("period")["value"].sum()
        tot  = by_p.sum()
        c1, c2, c3 = st.columns(3)
        for col, p, icon, color in [
            (c1,"day","☀️",COLORS["day"]),
            (c2,"peak","🔥",COLORS["peak"]),
            (c3,"night","🌙",COLORS["night"]),
        ]:
            v    = by_p.get(p, 0)
            rate = {"day":t_day,"peak":t_peak,"night":t_night}[p]
            _p_name = {"day":t("legend_day"),"peak":t("legend_peak"),"night":t("legend_night")}[p]
            with col:
                st.markdown(f"""
                <div style="background:#161b22;border:1px solid #30363d;
                            border-radius:12px;padding:1rem;border-top:3px solid {color}">
                    <div style="font-size:1.3rem">{icon}</div>
                    <div style="font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;
                                color:#7d8590;margin:.3rem 0">{_p_name}</div>
                    <div style="font-family:'JetBrains Mono',monospace;font-size:1.35rem;
                                font-weight:700;color:{color}">{v:,.1f} kWh</div>
                    <div style="font-size:.8rem;color:#7d8590">
                        {v/tot*100:.1f}% · €{v*rate:,.2f}
                    </div>
                </div>""", unsafe_allow_html=True)


# ════════════════════════════════════════════
#  TAB 1 — CONSUMPTION
# ════════════════════════════════════════════
with tabs[1]:
    if df_calc is None:
        alert(t("upload_calc_first"), "info"); st.stop()

    min_d = df_calc["datetime"].min().date()
    max_d = df_calc["datetime"].max().date()

    section("🌡️", t("heatmap_title"), badge="calckWh")
    ca, cb = st.columns(2)
    with ca: d_from = st.date_input(t("from_label"), value=min_d, min_value=min_d, max_value=max_d, key="cf")
    with cb: d_to   = st.date_input(t("to_label"),   value=max_d, min_value=min_d, max_value=max_d, key="ct")
    mask = (df_calc["date"] >= d_from) & (df_calc["date"] <= d_to)
    df_f = df_calc[mask].copy()

    heat = df_f.groupby(["date","hour"])["value"].sum().reset_index()
    heat_piv = heat.pivot(index="date", columns="hour", values="value").fillna(0)
    fig2 = go.Figure(go.Heatmap(
        z=heat_piv.values,
        x=[f"{h:02d}:00" for h in heat_piv.columns],
        y=[str(d) for d in heat_piv.index],
        colorscale=[[0,"#0d1117"],[0.25,"#1f3a5f"],[0.55,"#58a6ff"],[0.8,"#f0883e"],[1,"#f85149"]],
        hoverongaps=False, colorbar=dict(title="kWh", tickfont=dict(color=COLORS["muted"])),
    ))
    fig2.add_vrect(x0="17:00", x1="19:00", fillcolor=_rgba(COLORS["peak"], 0.13), line_width=0,
                   annotation_text=t("peak_rate"), annotation_font_color=COLORS["peak"])
    apply_layout(fig2, "", height=max(280, len(heat_piv)*14+60))
    fig2.update_layout(
        yaxis_autorange="reversed",
        xaxis=dict(
            tickmode="array",
            tickvals=[f"{h:02d}:00" for h in range(0, 24)],
            ticktext=[f"{h:02d}:00" if h % 3 == 0 else " " for h in range(0, 24)],
            ticks="outside",
            ticklen=4,
            tickwidth=1,
            tickcolor=COLORS["text"],
            tickfont=dict(size=9, color=COLORS["text"]),
            tickangle=-45,
        ),
    )
    st.plotly_chart(fig2, use_container_width=True)


# ════════════════════════════════════════════
#  TAB 2 — POWER DEMAND
# ════════════════════════════════════════════
with tabs[2]:
    if df_kw is None:
        alert(t("upload_kw_first"), "info"); st.stop()

    section("⚡", t("power_title"), badge=t("kw_file_badge"))
    if df_calc is not None:
        alert(t("cross_val_alert"), "good")

    min_d = df_kw["datetime"].min().date()
    max_d = df_kw["datetime"].max().date()
    ka, kb = st.columns(2)
    with ka: d_from = st.date_input(t("from_label"), value=min_d, min_value=min_d, max_value=max_d, key="kf")
    with kb: d_to   = st.date_input(t("to_label"),   value=max_d, min_value=min_d, max_value=max_d, key="kt")
    mask = (df_kw["date"] >= d_from) & (df_kw["date"] <= d_to)
    df_f = df_kw[mask].copy()
    p95  = df_f["value"].quantile(0.95)
    p99  = df_f["value"].quantile(0.99)

    k1, k2, k3, k4 = st.columns(4)
    # Sanity check - domestic meters should be < 20 kW
    max_val = df_f['value'].max()
    if max_val > 50:
        st.warning(f"⚠️ Peak value {max_val:,.1f} seems very high for a domestic meter. "
                   f"Check you uploaded the correct file — Power Demand expects the "
                   f"`HDF_kW_…csv` file, not the calckWh file.")
    k1.metric(t("peak_demand_lbl"),  f"{df_f['value'].max():.3f} kW")
    k2.metric(t("avg_demand_lbl"),   f"{df_f['value'].mean():.3f} kW")
    k3.metric(t("pct95_lbl"),     f"{p95:.3f} kW")
    k4.metric(t("spikes_p99"),  f"{(df_f['value']>p99).sum()}")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_f["datetime"], y=df_f["value"], mode="lines", name="kW",
                             line=dict(color=COLORS["kw"], width=1),
                             fill="tozeroy", fillcolor=_rgba(COLORS["kw"], 0.09)))
    spikes = df_f[df_f["value"]>p99]
    fig.add_trace(go.Scatter(x=spikes["datetime"], y=spikes["value"], mode="markers",
                             name=f">p99 ({p99:.2f} kW)",
                             marker=dict(color=COLORS["red"], size=6)))
    fig.add_hline(y=p95, line_dash="dash", line_color=COLORS["peak"],
                  annotation_text=f"p95: {p95:.2f} kW", annotation_font_color=COLORS["peak"])
    apply_layout(fig, "", height=400)
    fig.update_layout(
        yaxis_title="kW", xaxis=RANGESLIDER_X,
        margin=dict(l=10, r=10, t=40, b=10),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.markdown(
        f'<div style="display:flex;font-size:.8rem;margin-top:-4px;margin-bottom:4px">'
        f'<div style="min-width:55px"></div>'
        f'<div style="display:flex;gap:14px">'
        f'<span style="color:{COLORS["kw"]}">— kW</span>'
        f'<span style="color:{COLORS["red"]}">{t("spikes_html")}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    section("📊", t("daily_peak_avg"))
    ds2 = df_f.groupby("date")["value"].agg(["max","mean"]).reset_index()
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(x=ds2["date"], y=ds2["max"], name=t("peak_rate"),
                          marker_color=COLORS["peak"], marker_line_width=0))
    fig2.add_trace(go.Scatter(x=ds2["date"], y=ds2["mean"], name=t("trace_avg"),
                              line=dict(color=COLORS["kw"], width=2, dash="dot")))
    apply_layout(fig2, "", height=280)
    fig2.update_layout(yaxis_title="kW")
    st.plotly_chart(fig2, use_container_width=True)

    section("📉", t("load_curve"))
    sv = df_f["value"].sort_values(ascending=False).reset_index(drop=True)
    fig3 = go.Figure(go.Scatter(x=list(range(len(sv))), y=sv, mode="lines", fill="tozeroy",
                                line=dict(color=COLORS["kw"], width=2),
                                fillcolor=_rgba(COLORS["kw"], 0.13)))
    for pv, lbl, col in [(0.50,t("median_lbl"),COLORS["muted"]),(0.95,"p95",COLORS["peak"])]:
        idx = int(len(sv)*(1-pv))
        fig3.add_vline(x=idx, line_dash="dot", line_color=col,
                       annotation_text=lbl, annotation_font_color=col)
    apply_layout(fig3, "", height=260)
    fig3.update_layout(xaxis_title=t("load_curve"), yaxis_title="kW")
    st.plotly_chart(fig3, use_container_width=True)

    section("🕐", t("avg_demand_hour"))
    hourly = df_f.groupby("hour")["value"].mean().reset_index()
    hcol = [COLORS["peak"] if 17<=h<19 else COLORS["night"] if (h>=23 or h<8) else COLORS["day"]
            for h in hourly["hour"]]
    hourly["hour_str"] = hourly["hour"].apply(lambda h: f"{h:02d}:00")
    fig4 = go.Figure(go.Bar(x=hourly["hour_str"], y=hourly["value"],
                            marker_color=hcol, marker_line_width=0))
    apply_layout(fig4, "", height=250)
    fig4.update_layout(
        xaxis=dict(
            tickmode="array",
            tickvals=[f"{h:02d}:00" for h in range(0, 24)],
            ticktext=[f"{h:02d}:00" if h % 3 == 0 else " " for h in range(0, 24)],
            ticks="outside",
            ticklen=4,
            tickwidth=1,
            tickcolor=COLORS["text"],
            tickfont=dict(size=9, color=COLORS["text"]),
            tickangle=-45,
            gridcolor=COLORS["grid"],
        ),
        yaxis_title="kW",
    )
    st.plotly_chart(fig4, use_container_width=True)


# ════════════════════════════════════════════
#  TAB 3 — DAILY ANALYSIS
# ════════════════════════════════════════════
with tabs[3]:
    if df_dnp is None and df_daily is None:
        alert("Upload <strong>Daily DNP</strong> or <strong>Daily kWh</strong>.", "info"); st.stop()

    col_map = {
        "Night Import Register (kWh)":        (COLORS["night"], f"🌙 {t('night_label_chart')}"),
        "Day Peak Import Register (kWh)":     (COLORS["peak"],  f"🔥 {t('peak_label_chart')}"),
        "Day Off-Peak Import Register (kWh)": (COLORS["day"],   t("day_off_peak_dnp")),
    }

    if df_dnp is not None:
        section("📅", t("daily_registers"), badge=t("dnp_badge"))
        pivot = df_dnp.pivot_table(index="date", columns="type", values="value", aggfunc="max")
        pivot.columns = [c.strip() for c in pivot.columns]
        pivot = pivot.reset_index().sort_values("date")
        for c in col_map:
            if c in pivot.columns:
                pivot[c+"_delta"] = pivot[c].diff().clip(lower=0)

        fig = go.Figure()
        for cn, (color, label) in col_map.items():
            dc = cn+"_delta"
            if dc in pivot.columns:
                fig.add_trace(go.Bar(x=pivot["date"], y=pivot[dc], name=label,
                                     marker_color=color, marker_line_width=0))
        apply_layout(fig, "", height=340)
        fig.update_layout(barmode="stack", yaxis_title="kWh")
        st.plotly_chart(fig, use_container_width=True)

        section("📈", t("cumulative_registers"))
        fig2 = go.Figure()
        for cn, (color, label) in col_map.items():
            if cn in pivot.columns:
                fig2.add_trace(go.Scatter(x=pivot["date"], y=pivot[cn], name=label,
                                          line=dict(color=color, width=2)))
        apply_layout(fig2, "", height=300)
        fig2.update_layout(
            yaxis_title=t("kw_cumulative"),
            legend=dict(
                orientation="h", yanchor="top", y=-0.18,
                xanchor="left", x=0,
                font=dict(size=10, color=COLORS["text"]),
                bgcolor="rgba(0,0,0,0)",
            ),
            margin=dict(l=10, r=10, t=20, b=70),
        )
        st.plotly_chart(fig2, use_container_width=True)

    if df_daily is not None:
        section("📅", t("daily_total_kwh"), badge=t("reg_24h"))
        df_d = df_daily[df_daily["daily"].notna() & (df_daily["daily"] > 0)].copy()
        df_d["date"]  = pd.to_datetime(df_d["date"])
        df_d["roll7"] = df_d["daily"].rolling(7, min_periods=1).mean()
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_d["date"], y=df_d["daily"],
                             marker_color=COLORS["total"], marker_line_width=0, name=t("trace_kwh")))
        fig.add_trace(go.Scatter(x=df_d["date"], y=df_d["roll7"], name=t("seven_day_avg"),
                                 line=dict(color=COLORS["yellow"], width=2)))
        fig.add_hline(y=df_d["daily"].mean(), line_dash="dot", line_color=COLORS["muted"],
                      annotation_text=f"Mean: {df_d['daily'].mean():.1f} kWh",
                      annotation_font_color=COLORS["muted"])
        apply_layout(fig, "", height=320)
        fig.update_layout(yaxis_title=t("kwh_day_unit"))
        st.plotly_chart(fig, use_container_width=True)


# ════════════════════════════════════════════
#  TAB 4 — COST BREAKDOWN
# ════════════════════════════════════════════
with tabs[4]:
    if df_calc is None:
        alert(t("upload_calc_first"), "info"); st.stop()

    section("💶", t("cost_breakdown"), badge="calckWh")
    by_p = df_calc.groupby("period").agg(kwh=("value","sum"), cost=("cost","sum")).reset_index()
    by_p["cost_net"] = by_p["cost"] * disc_factor
    total_cost       = by_p["cost_net"].sum()
    days_total       = max((df_calc["datetime"].max() - df_calc["datetime"].min()).days, 1)
    standing_total   = days_total * t_stand
    vat_total        = (total_cost + standing_total) * VAT_RATE
    bill_total       = total_cost + standing_total + vat_total

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(t("energy_net"),    f"€{total_cost:.2f}")
    k2.metric(t("standing_charges"),        f"€{standing_total:.2f}", f"{days_total}d × €{t_stand:.4f}")
    k3.metric("VAT 9%",          f"€{vat_total:.2f}")
    k4.metric(t("est_total_bill"), f"€{bill_total:.2f}")

    st.divider()
    cmap = {"day":COLORS["day"],"peak":COLORS["peak"],"night":COLORS["night"]}
    c1, c2 = st.columns([1,1])
    with c1:
        fig_pie = go.Figure(go.Pie(
            labels=[{'day': t("day_donut"), 'peak': t("peak_donut"), 'night': t("night_donut")}.get(p, p.capitalize()) for p in by_p["period"]],
            values=by_p["cost_net"].round(2), hole=0.55,
            marker=dict(colors=[cmap.get(p,"#888") for p in by_p["period"]]),
            textinfo="label+percent", textfont=dict(color=COLORS["text"], size=12),
        ))
        fig_pie.update_layout(
            paper_bgcolor=COLORS["bg"], font=dict(family="Space Grotesk", color=COLORS["text"]),
            showlegend=False, margin=dict(l=10,r=10,t=30,b=10), height=260,
            title=dict(text=t("energy_cost_period"),
                       font=dict(size=13, color=COLORS["muted"]), x=0.5),
            annotations=[dict(text=f"€{total_cost:.2f}", x=0.5, y=0.5,
                              font_size=20, font_color=COLORS["text"], showarrow=False)],
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    with c2:
        for _, row in by_p.iterrows():
            p = row["period"]; color = cmap.get(p,"#888")
            _p_lbl = {"day": t("legend_day"), "peak": t("legend_peak"), "night": t("legend_night")}.get(p, p.capitalize())
            st.markdown(f"""
            <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;
                        padding:.75rem 1.1rem;margin:.4rem 0;border-left:3px solid {color}">
                <div style="display:flex;justify-content:space-between;align-items:center">
                    <div>
                        <div style="font-weight:600;color:{color}">{_p_lbl}</div>
                        <div style="font-size:.78rem;color:#7d8590">{row['kwh']:,.1f} kWh</div>
                    </div>
                    <div style="text-align:right">
                        <div style="font-family:'JetBrains Mono',monospace;font-size:1.15rem;font-weight:600">
                            €{row['cost_net']:.2f}</div>
                        <div style="font-size:.73rem;color:#7d8590">
                            {row['cost_net']/total_cost*100:.1f}%</div>
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)

    st.divider()
    section("📆", t("monthly_bill"))
    if st.session_state.get("lang","en") == "pl":
        _mn = TRANSLATIONS["months_short"]["pl"]
        df_calc["month_str"] = df_calc["datetime"].apply(
            lambda d: f"{_mn[d.month-1]} {d.year}"
        )
    else:
        df_calc["month_str"] = df_calc["datetime"].dt.to_period("M").astype(str)
    mo = df_calc.groupby("month_str").agg(kwh=("value","sum"), cost=("cost","sum")).reset_index()
    mo["cost_net"] = mo["cost"] * disc_factor
    mo["days"]     = df_calc.groupby("month_str")["date"].nunique().values[:len(mo)]
    mo["standing"] = mo["days"] * t_stand
    mo["vat"]      = (mo["cost_net"] + mo["standing"]) * VAT_RATE
    mo["total"]    = mo["cost_net"] + mo["standing"] + mo["vat"]

    fig_m = go.Figure()
    fig_m.add_trace(go.Bar(x=mo["month_str"], y=mo["cost_net"],  name=t("trace_energy"),   marker_color=COLORS["day"],   marker_line_width=0))
    fig_m.add_trace(go.Bar(x=mo["month_str"], y=mo["standing"],  name=t("standing_charges"), marker_color=COLORS["muted"], marker_line_width=0))
    fig_m.add_trace(go.Bar(x=mo["month_str"], y=mo["vat"],       name="VAT 9%",   marker_color=COLORS["peak"],  marker_line_width=0))
    fig_m.add_trace(go.Scatter(x=mo["month_str"], y=mo["total"], name=t("trace_total"),
                               mode="lines+markers", line=dict(color=COLORS["total"], width=2),
                               marker=dict(size=7)))
    apply_layout(fig_m, "", height=360)
    fig_m.update_layout(
        barmode="stack", yaxis_title="€",
        legend=dict(
            orientation="h", yanchor="top", y=-0.22,
            xanchor="left", x=0,
            font=dict(size=10, color=COLORS["text"]),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=10, r=10, t=20, b=100),
    )
    st.plotly_chart(fig_m, use_container_width=True)


# ════════════════════════════════════════════
#  TAB 5 — ADVANCED INSIGHTS
# ════════════════════════════════════════════
with tabs[5]:
    if df_calc is None:
        alert(t("upload_calc_first"), "info"); st.stop()

    section("🌡️", t("seasonal_trend"))
    monthly_avg = df_calc.groupby("month")["daily_kwh"].mean().reset_index()
    monthly_avg.columns = ["month","avg"]
    bar_colors = [COLORS["total"] if v<12 else COLORS["yellow"] if v<18 else COLORS["peak"]
                  for v in monthly_avg["avg"]]
    fig = go.Figure(go.Bar(x=monthly_avg["month"], y=monthly_avg["avg"],
                           marker_color=bar_colors, marker_line_width=0))
    apply_layout(fig, "", height=260)
    fig.update_layout(yaxis_title=t("kwh_day_unit"))
    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    section("📊", t("load_profile"))
    slot_avg = df_calc.groupby(["hour","minute"])["value"].mean().reset_index()
    slot_avg["time"] = slot_avg["hour"].astype(str).str.zfill(2)+":"+slot_avg["minute"].astype(str).str.zfill(2)
    slot_avg = slot_avg.sort_values(["hour","minute"])
    sc = [COLORS["peak"] if 17<=r["hour"]<19
          else COLORS["night"] if (r["hour"]>=23 or r["hour"]<8)
          else COLORS["day"]
          for _,r in slot_avg.iterrows()]
    fig2 = go.Figure(go.Bar(x=slot_avg["time"], y=slot_avg["value"],
                            marker_color=sc, marker_line_width=0))
    fig2.add_vrect(x0="17:00", x1="19:00", fillcolor=_rgba(COLORS["peak"], 0.13), line_width=0,
                   annotation_text=t("peak_rate"), annotation_font_color=COLORS["peak"])
    fig2.add_vrect(x0="00:00", x1="07:30", fillcolor=_rgba(COLORS["night"], 0.13), line_width=0,
                   annotation_text=t("night_rate"), annotation_font_color=COLORS["night"])
    fig2.add_vrect(x0="08:00", x1="17:00", fillcolor=_rgba(COLORS["day"], 0.07), line_width=0,
                   annotation_text=t("day_rate"), annotation_font_color=COLORS["day"],
                   annotation_position="top left")
    apply_layout(fig2, "", height=300)
    fig2.update_layout(
        xaxis=dict(
            tickmode="array",
            tickvals=[slot_avg["time"].iloc[i] for i in range(0, len(slot_avg), 2)],
            ticktext=[slot_avg["time"].iloc[i] if i % 6 == 0 else " " for i in range(0, len(slot_avg), 2)],
            ticks="outside",
            ticklen=4,
            tickwidth=1,
            tickcolor=COLORS["text"],
            tickfont=dict(size=9, color=COLORS["text"]),
            tickangle=-45,
            gridcolor=COLORS["grid"],
        ),
        yaxis_title=t("avg_kwh_axis"),
    )
    st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    section("📅", t("weekday_weekend"))
    daily_df = df_calc.groupby("date")["value"].sum().reset_index()
    daily_df["dow"]  = pd.to_datetime(daily_df["date"]).dt.weekday
    _wd_en = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    _wd_pl = [t("mon"),t("tue"),t("wed"),t("thu"),t("fri"),t("sat"),t("sun")]
    _wd_map = dict(zip(_wd_en, _wd_pl))
    daily_df["name"] = pd.to_datetime(daily_df["date"]).dt.day_name().map(
        lambda d: _wd_map.get(d, d) if st.session_state.get("lang","en") == "pl" else d
    )
    dow_avg = daily_df.groupby(["dow","name"])["value"].mean().reset_index().sort_values("dow")
    fig3 = go.Figure(go.Bar(
        x=dow_avg["name"], y=dow_avg["value"],
        marker_color=[COLORS["peak"] if d>=5 else COLORS["day"] for d in dow_avg["dow"]],
        marker_line_width=0))
    apply_layout(fig3, "", height=250)
    fig3.update_layout(yaxis_title=t("kwh_day_unit"))
    st.plotly_chart(fig3, use_container_width=True)

    st.divider()
    section("🔋", t("standby_baseline"))
    standby_avg = df_calc[df_calc["hour"].isin([2,3])]["value"].mean()
    standby_kw  = standby_avg * 2
    annual_kwh  = standby_kw * 8760
    annual_cost = annual_kwh * t_night * disc_factor
    ca, cb, cc = st.columns(3)
    with ca: st.markdown(kpi_html(t("standby_power"),      f"{standby_kw*1000:.0f}", t("w_standby"), "purple"), unsafe_allow_html=True)
    with cb: st.markdown(kpi_html(t("annual_standby_kwh"), f"{annual_kwh:.0f}", t("kwh_year_est"), "blue"),     unsafe_allow_html=True)
    with cc: st.markdown(kpi_html(t("annual_cost"),        f"€{annual_cost:.2f}", t("at_night_rate"), "orange"), unsafe_allow_html=True)

    st.divider()
    section("💡", t("peak_shifting"))
    peak_kwh = df_calc[df_calc["period"]=="peak"]["value"].sum()
    max_save = peak_kwh * (t_peak - t_night) * disc_factor
    shift    = st.slider(t("shift_pct_label"), 0, 100, 50, step=5)
    ca, cb, cc = st.columns(3)
    with ca: st.markdown(kpi_html(t("total_peak_kwh"),   f"{peak_kwh:.1f}", t("all_time"), "orange"),          unsafe_allow_html=True)
    with cb: st.markdown(kpi_html(t("max_saving"),f"€{max_save:.2f}", t("all_to_night"), "green"),       unsafe_allow_html=True)
    with cc: st.markdown(kpi_html(t("at_shift_label").format(pct=shift),f"€{max_save*shift/100:.2f}",
                                  f"{t('night_label_chart')} {(1-t_night/t_peak)*100:.0f}% {t('at_night_rate')}", "cyan"),               unsafe_allow_html=True)

    st.divider()
    section("🚨", t("anomaly_days"))
    daily_all = df_calc.groupby("date")["value"].sum().reset_index()
    mean_d = daily_all["value"].mean(); std_d = daily_all["value"].std()
    thresh = mean_d + 2*std_d
    anom   = daily_all[daily_all["value"]>thresh].sort_values("value", ascending=False).head(10)
    fig5 = go.Figure()
    fig5.add_trace(go.Bar(x=daily_all["date"], y=daily_all["value"], name=t("trace_kwh"),
                          marker_color=COLORS["day"], marker_line_width=0, opacity=0.7))
    fig5.add_trace(go.Scatter(x=anom["date"], y=anom["value"], mode="markers",
                              name=t("mean_2sigma"), marker=dict(color=COLORS["red"], size=10)))
    fig5.add_hline(y=thresh, line_dash="dash", line_color=COLORS["red"],
                   annotation_text=f"mean+2σ = {thresh:.1f} kWh",
                   annotation_font_color=COLORS["red"])
    apply_layout(fig5, "", height=300)
    fig5.update_layout(yaxis_title=t("kwh_day_unit"))
    st.plotly_chart(fig5, use_container_width=True)
    if len(anom):
        st.dataframe(
            anom.rename(columns={"date":"Date","value":"kWh"})
                .assign(**{t("vs_avg"): lambda d: (d["kWh"]-mean_d).map(lambda x: f"+{x:.1f} kWh")}),
            use_container_width=True, hide_index=True,
        )



# ════════════════════════════════════════════
#  TAB 6 — BILL PREDICTION
# ════════════════════════════════════════════
with tabs[6]:
    from datetime import date as dt_date, timedelta

    b_start = st.session_state.get("billing_start")
    b_end   = st.session_state.get("billing_end")
    b_days  = st.session_state.get("billing_days", 60)

    # ── No billing period configured ──
    if not b_start or not b_end:
        st.markdown("""
        <div style="text-align:center;padding:3rem 2rem;background:#161b22;border-radius:16px;
                    border:1px dashed #30363d;margin-top:1rem">
            <div style="font-size:2.5rem">📅</div>
            <h3 style="color:#e6edf3;margin:.5rem 0">No billing period configured</h3>
            <p style="color:#7d8590;max-width:400px;margin:.5rem auto">
                To enable bill prediction, add your current billing period start date
                in the setup screen.
            </p>
        </div>""", unsafe_allow_html=True)
        if st.button("⚙️ Go to Setup"):
            st.session_state["setup_done"] = False
            st.rerun()
        st.stop()

    if df_calc is None:
        alert("Upload the <strong>calckWh</strong> file for bill prediction.", "info"); st.stop()

    today        = dt_date.today()
    days_elapsed = max((min(today, b_end) - b_start).days, 1)
    days_total   = (b_end - b_start).days
    days_remain  = max((b_end - today).days, 0)
    pct_elapsed  = days_elapsed / days_total * 100

    section("🔮", t("current_progress"),
            badge=f"{fmt_date(b_start, '%d %b')} → {fmt_date(b_end)}")

    # ── Progress bar ──
    st.markdown(f"""
    <div style="background:#161b22;border:1px solid #30363d;border-radius:12px;
                padding:1.2rem 1.4rem;margin-bottom:1rem">
        <div style="display:flex;justify-content:space-between;font-size:.78rem;
                    color:#7d8590;margin-bottom:6px">
            <span>{fmt_date(b_start)}</span>
            <span style="color:#58a6ff;font-weight:600">{pct_elapsed:.0f}% {t("elapsed_lbl")}</span>
            <span>{fmt_date(b_end)}</span>
        </div>
        <div style="background:#1c2330;border-radius:6px;height:10px;overflow:hidden">
            <div style="height:10px;border-radius:6px;width:{min(pct_elapsed,100):.1f}%;
                        background:linear-gradient(90deg,#58a6ff,#39d0d8);
                        transition:width .5s ease"></div>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:.74rem;
                    color:#7d8590;margin-top:6px">
            <span>{days_elapsed} {t("days_elapsed")}</span>
            <span>{days_remain} {t("days_remaining")}</span>
        </div>
    </div>""", unsafe_allow_html=True)

    # ── Actual consumption so far in current period ──
    period_mask = df_calc["date"] >= b_start
    if days_remain < 0:
        period_mask = (df_calc["date"] >= b_start) & (df_calc["date"] <= b_end)

    df_period = df_calc[period_mask].copy()
    actual_kwh  = df_period["value"].sum()
    actual_cost = df_period["cost_net"].sum()
    actual_days = df_period["date"].nunique()
    daily_avg   = actual_kwh / actual_days if actual_days > 0 else 0

    # ── Build prediction using multiple methods ──
    # Method 1: Simple extrapolation from current period avg
    pred_kwh_simple = daily_avg * days_total

    # Method 2: Seasonal weighted — use historical monthly averages
    monthly_hist = df_calc.groupby("month")["daily_kwh"].mean()

    # Calculate weighted avg for remaining days (by calendar month)
    import calendar
    remaining_kwh_seasonal = 0.0
    cursor = today + timedelta(days=1)
    counted = 0
    while cursor <= b_end and counted < days_remain:
        m_str = cursor.strftime("%Y-%m")
        hist_avg = monthly_hist.get(m_str, daily_avg)
        # if no exact month match, try same month different year
        if m_str not in monthly_hist.index:
            same_month_keys = [k for k in monthly_hist.index if k.endswith(f"-{cursor.month:02d}")]
            hist_avg = monthly_hist[same_month_keys].mean() if same_month_keys else daily_avg
        remaining_kwh_seasonal += hist_avg
        cursor += timedelta(days=1)
        counted += 1

    pred_kwh_seasonal = actual_kwh + remaining_kwh_seasonal

    # Method 3: 14-day rolling avg extrapolation
    last14_start = today - timedelta(days=14)
    df_last14    = df_calc[df_calc["date"] >= last14_start]
    daily_14d    = df_last14.groupby("date")["value"].sum().mean() if len(df_last14) > 0 else daily_avg
    pred_kwh_14d = actual_kwh + daily_14d * days_remain

    # ── Cost predictions ──
    def calc_bill(kwh_total, period_days):
        """Estimate full bill: energy (split day/peak/night by historical ratio) + standing + VAT"""
        by_p = df_calc.groupby("period")["value"].sum()
        tot  = by_p.sum() or 1
        day_r   = by_p.get("day",   0) / tot
        peak_r  = by_p.get("peak",  0) / tot
        night_r = by_p.get("night", 0) / tot
        energy = kwh_total * (day_r*t_day + peak_r*t_peak + night_r*t_night) * disc_factor
        standing = period_days * t_stand
        vat  = (energy + standing) * VAT_RATE
        return energy, standing, vat, energy + standing + vat

    e1, s1, v1, total1 = calc_bill(pred_kwh_simple,   days_total)
    e2, s2, v2, total2 = calc_bill(pred_kwh_seasonal, days_total)
    e3, s3, v3, total3 = calc_bill(pred_kwh_14d,      days_total)

    # ── KPI strip ──
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(t("consumed_so_far"),    f"{actual_kwh:.1f} kWh",  f"€{actual_cost:.2f} {t('net_label')}")
    k2.metric(t("daily_avg_period"), f"{daily_avg:.2f} kWh/d")
    k3.metric(t("days_remaining_lbl"),     f"{days_remain}")
    k4.metric(t("period_end_lbl"),         fmt_date(b_end),
              t("in_n_days_lbl").format(n=days_remain) if days_remain > 0 else t("period_passed") if "period_passed" in TRANSLATIONS else "passed")

    st.divider()
    section("💰", t("bill_prediction"))
    alert(t("prediction_accuracy").format(pct=f"{pct_elapsed:.0f}"),"info")

    c1, c2, c3 = st.columns(3)
    method_data = [
        (c1, t("simple_extrap"), pred_kwh_simple, total1, t("curr_period_desc"), "blue"),
        (c2, t("seasonal_m"),       pred_kwh_seasonal,total2,t("hist_monthly_desc"),"cyan"),
        (c3, t("rolling_14d_m"),   pred_kwh_14d,   total3, t("recent_14d_desc"), "purple"),
    ]
    for col, label, kwh, total, desc, color in method_data:
        with col:
            st.markdown(f"""
            <div style="background:#161b22;border:1px solid #30363d;border-radius:12px;
                        padding:1.1rem;border-top:3px solid {color}">
                <div style="font-size:.78rem;font-weight:600;color:#7d8590;margin-bottom:.5rem">
                    {label}
                </div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:1.6rem;font-weight:700;
                            color:#e6edf3">€{total:.2f}</div>
                <div style="font-size:.78rem;color:#7d8590;margin:.2rem 0">
                    ~{kwh:.0f} {t("projected")}
                </div>
                <div style="font-size:.7rem;color:#7d8590;margin-top:.4rem;
                            padding-top:.4rem;border-top:1px solid #30363d">
                    {desc}
                </div>
            </div>""", unsafe_allow_html=True)

    # ── Prediction range visual ──
    st.markdown("<br>", unsafe_allow_html=True)
    low_bill  = min(total1, total2, total3)
    high_bill = max(total1, total2, total3)
    mid_bill  = (total1 + total2 + total3) / 3
    st.markdown(f"""
    <div style="background:#161b22;border:1px solid #30363d;border-radius:12px;
                padding:1.2rem 1.4rem">
        <div style="font-size:.78rem;color:#7d8590;margin-bottom:.8rem">
            {t("predicted_range")}
        </div>
        <div style="display:flex;align-items:center;gap:12px">
            <div style="font-family:'JetBrains Mono',monospace;font-size:1.1rem;color:#3fb950">
                €{low_bill:.2f}
            </div>
            <div style="flex:1;background:#1c2330;border-radius:6px;height:12px;
                        position:relative;overflow:hidden">
                <div style="position:absolute;left:0;right:0;height:12px;
                            background:linear-gradient(90deg,#3fb950,#d29922,#f85149);
                            border-radius:6px;opacity:.3"></div>
                <div style="position:absolute;
                            left:{(mid_bill-low_bill)/(high_bill-low_bill+0.01)*80:.0f}%;
                            width:4px;height:12px;background:#58a6ff;border-radius:2px"></div>
            </div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:1.1rem;color:#f85149">
                €{high_bill:.2f}
            </div>
        </div>
        <div style="text-align:center;margin-top:.5rem;font-size:.78rem;color:#7d8590">
            {t("most_likely_full")}: <strong style="color:#58a6ff">€{mid_bill:.2f}</strong>
            &nbsp;·&nbsp; {t("range_full")}: €{high_bill-low_bill:.2f}
        </div>
    </div>""", unsafe_allow_html=True)

    st.divider()

    # ── Day-by-day projection chart ──
    section("📈", t("cumulative_cost"))

    # Actual cumulative cost by day
    daily_cost = df_period.groupby("date")["cost_net"].sum().reset_index()
    daily_cost["date"] = pd.to_datetime(daily_cost["date"])
    daily_cost = daily_cost.sort_values("date")
    daily_cost["cumcost"] = daily_cost["cost_net"].cumsum()

    # Add standing charge to cumulative
    daily_cost["cumtotal"] = (
        daily_cost["cumcost"] +
        (daily_cost["date"] - pd.Timestamp(b_start)).dt.days * t_stand
    )

    # Projection lines from last actual point
    last_actual_date = daily_cost["date"].max() if len(daily_cost) > 0 else pd.Timestamp(b_start)
    last_actual_val  = float(daily_cost["cumtotal"].iloc[-1]) if len(daily_cost) > 0 else 0.0
    proj_dates = pd.date_range(last_actual_date, b_end, freq="D")

    fig_proj = go.Figure()

    # Actual
    if len(daily_cost) > 0:
        fig_proj.add_trace(go.Scatter(
            x=daily_cost["date"], y=daily_cost["cumtotal"],
            name="Actual (incl. standing)", mode="lines",
            line=dict(color=COLORS["total"], width=2.5),
        ))

    # Three projection lines
    for label, daily_rate, color, dash in [
        (t("trace_simple_short"),   daily_avg,  COLORS["blue"],   "dash"),
        (t("trace_seasonal_short"), remaining_kwh_seasonal/max(days_remain,1), COLORS["cyan"],   "dot"),
        ("14d avg",  daily_14d,  COLORS["purple"], "dashdot"),
    ]:
        proj_cost_daily = (daily_rate * (t_day * 0.6 + t_peak * 0.1 + t_night * 0.3) * disc_factor + t_stand)
        proj_y = [last_actual_val + proj_cost_daily * i for i in range(len(proj_dates))]
        fig_proj.add_trace(go.Scatter(
            x=proj_dates, y=proj_y, name=f"{t('forecast_lbl')} ({label})",
            mode="lines", line=dict(color=color, width=1.5, dash=dash),
        ))

    # Period end marker
    fig_proj.add_vline(x=pd.Timestamp(b_end).timestamp() * 1000, line_dash="dot",
                       line_color=COLORS["muted"],
                       annotation_text=t("bill_date"), annotation_font_color=COLORS["muted"])

    apply_layout(fig_proj, "", height=380)
    fig_proj.update_layout(yaxis_title=t("euro_cumul"))
    st.plotly_chart(fig_proj, use_container_width=True)

    st.divider()

    # ── Bill breakdown estimate ──
    section("🧾", t("est_bill_breakdown"), badge=t("based_on_seasonal"))
    e, s, v, tot = calc_bill(pred_kwh_seasonal, days_total)
    rewards = 5.0  # typical rewards saving (generic)
    items = [
        (t("energy_charges"),  f"€{e:.2f}", COLORS["day"]),
        (t("standing_charges_lbl"),        f"€{s:.2f}", COLORS["muted"]),
        ("VAT 9%",                  f"€{v:.2f}", COLORS["peak"]),
        (t("est_total_due"),          f"€{tot:.2f}", COLORS["text"]),
    ]
    for label, val, color in items:
        is_total = label.startswith("Est.")
        st.markdown(f"""
        <div style="display:flex;justify-content:space-between;align-items:center;
                    padding:{'.9rem' if is_total else '.55rem'} 1rem;
                    background:{'#1c2330' if is_total else 'transparent'};
                    border-radius:{'10px' if is_total else '0'};
                    border-bottom:{'none' if is_total else '1px solid #30363d'};
                    {'margin-top:.5rem' if is_total else ''}">
            <span style="color:{'#e6edf3' if is_total else '#7d8590'};
                         font-weight:{'700' if is_total else '400'};font-size:.88rem">
                {label}
            </span>
            <span style="font-family:'JetBrains Mono',monospace;font-weight:{'700' if is_total else '400'};
                         font-size:{'1.1rem' if is_total else '.9rem'};color:{color}">
                {val}
            </span>
        </div>""", unsafe_allow_html=True)

    # ── Update billing period in sidebar ──
    st.divider()
    section("⚙️", t("billing_period_sett"))
    col_a, col_b = st.columns(2)
    with col_a:
        new_start = st.date_input(t("period_start"), value=b_start, key="bp_start")
        new_days  = st.number_input(t("cycle_length"), value=b_days, min_value=14, max_value=120, key="bp_days")
    with col_b:
        new_end = new_start + timedelta(days=int(new_days))
        st.markdown(f"""
        <div style="background:#1c2330;border:1px solid #30363d;border-radius:10px;
                    padding:1rem;margin-top:1.8rem">
            <div style="font-size:.7rem;text-transform:uppercase;color:#7d8590">{t("next_bill_full")}</div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:1.3rem;color:#58a6ff;margin:.3rem 0">
                {fmt_date(new_end)}
            </div>
            <div style="font-size:.78rem;color:#7d8590">{t("days_from_today_lbl").format(n=(new_end - today).days)}</div>
        </div>""", unsafe_allow_html=True)

    if st.button(t("update_billing")):
        st.session_state["billing_start"] = new_start
        st.session_state["billing_end"]   = new_end
        st.session_state["billing_days"]  = int(new_days)
        save_config()
        st.success(t("period_saved"))
        st.rerun()


# ════════════════════════════════════════════
#  TAB 7 — RAW DATA
# ════════════════════════════════════════════
with tabs[7]:
    section("📋", t("raw_data"))

    # ── Data quality report ──
    section("🔍", t("quality_report"), badge=t("auto_checked"))

    qr_map = {
        "calckWh": st.session_state.get("_qr_calc"),
        "kW":      st.session_state.get("_qr_kw"),
        "DNP":     st.session_state.get("_qr_dnp"),
        "Daily":   st.session_state.get("_qr_daily"),
    }
    any_qr = any(v is not None for v in qr_map.values())
    if any_qr:
        for fname, qr in qr_map.items():
            if qr is None:
                continue
            dupes    = qr.get("exact_dupes_removed", 0)
            dst      = qr.get("dst_slots", 0)
            outliers = qr.get("outliers_removed", 0)
            status   = "good" if dupes == 0 and outliers == 0 else "warn"
            icon     = "✅" if status == "good" else "⚠️"
            details  = []
            if dupes:
                details.append(f"{t('dupes_removed').format(n=f'<strong>{dupes}</strong>')}")
            if dst:
                details.append(f"{t('dst_slots_kept').format(n=f'<strong>{dst//2}</strong>')}")
            if outliers:
                details.append(f"{t('outliers_removed_lbl').format(n=f'<strong>{outliers}</strong>')}")
            if not details:
                details.append(t("no_issues"))
            st.markdown(f"""
            <div style="display:flex;align-items:flex-start;gap:10px;
                        background:#161b22;border:1px solid #30363d;
                        border-radius:10px;padding:.7rem 1rem;margin:.3rem 0">
                <span style="font-size:1rem;margin-top:1px">{icon}</span>
                <div>
                    <div style="font-weight:600;font-size:.84rem;color:#e6edf3">{fname}</div>
                    <div style="font-size:.76rem;color:#7d8590">
                        {t("rows_summary").format(raw=qr['rows_raw'], clean=qr['rows_clean'])}
                        &nbsp;·&nbsp; {" · ".join(details)}
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)

        st.markdown(f"""
        <div class="alert-box alert-info" style="margin-top:.6rem">
            ℹ️ <strong>{t("how_updates_work")}:</strong> {t("how_updates_info")}
        </div>""", unsafe_allow_html=True)
    else:
        alert(t("upload_files_to_see"), "info")

    st.divider()

    ds = st.selectbox(t("browse_dataset"), ["calckWh (30-min)", "kW Demand", t("daily_dnp_label"), "kWh"])
    df_map = {"calckWh (30-min)":df_calc, "kW Demand":df_kw, t("daily_dnp_label"):df_dnp, "kWh":df_daily}
    df_show = df_map.get(ds)
    if df_show is not None:
        st.dataframe(df_show.head(500), use_container_width=True, height=420)
        st.download_button(t("download_csv"),
                           df_show.to_csv(index=False).encode("utf-8"),
                           f"{ds.replace(' ','_')}_export.csv", "text/csv")
    else:
        alert(f"Upload the <strong>{ds}</strong> file first.", "warn")
