"""
Energy Viz — Universal Smart Meter Dashboard
ESB Networks (Ireland) HDF file analysis
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
# ─────────────────────────────────────────────
DATA_DIR   = Path(os.environ.get("ENERGY_VIZ_DATA", "/app/data"))
HDF_DIR    = DATA_DIR / "hdf"
CONFIG_FILE    = DATA_DIR / "config.json"
API_KEY_FILE   = DATA_DIR / "api_key.enc"
INVOICE_FILE   = DATA_DIR / "invoice.pdf"

for d in [DATA_DIR, HDF_DIR]:
    d.mkdir(parents=True, exist_ok=True)

HDF_SLOTS = {
    "calc":  HDF_DIR / "calckWh.csv",
    "kw":    HDF_DIR / "kw.csv",
    "dnp":   HDF_DIR / "dnp.csv",
    "daily": HDF_DIR / "daily.csv",
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
#  AI EXTRACTION ENGINE (MODELS UPDATED)
# ─────────────────────────────────────────────
def get_ai_model(api_key, provider="Google Gemini"):
    if provider == "Google Gemini":
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        # Updated to stable production model names
        # Use 'gemini-1.5-flash' for best balance or 'gemini-1.5-flash-8b' if hitting limits
        return genai.GenerativeModel('gemini-1.5-flash')
    elif provider == "OpenAI GPT-4":
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    return None

# Rest of the application logic remains strictly unchanged...
# [ZACHOWANO CAŁĄ RESZTĘ TWOJEGO KODU BEZ ZMIAN]
