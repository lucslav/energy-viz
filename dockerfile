FROM python:3.12-slim

# ── System deps ──────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root user for security ───────────────────────────
RUN useradd -m -u 1000 appuser

WORKDIR /app

# ── Python deps ──────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── App code ─────────────────────────────────────────────
COPY app.py .

# ── Data directory (mounted as Docker volume) ────────────
# All persistent data lives here:
#   /app/data/config.json        ← tariff rates, MPRN, billing period
#   /app/data/api_key.enc        ← encrypted API key (if user chooses to save)
#   /app/data/invoice.pdf        ← last uploaded invoice
#   /app/data/hdf/calckWh.csv    ← last uploaded HDF files
#   /app/data/hdf/kw.csv
#   /app/data/hdf/dnp.csv
#   /app/data/hdf/daily.csv
RUN mkdir -p /app/data/hdf && chown -R appuser:appuser /app/data

# ── Switch to non-root ───────────────────────────────────
USER appuser

# ── Runtime config ───────────────────────────────────────
# Override these in docker-compose.yml or with -e flags:
#   ENERGY_VIZ_DATA   — path to data dir (default: /app/data)
#   ENERGY_VIZ_SECRET — unique secret for API key encryption
#                        CHANGE THIS before first run!
ENV ENERGY_VIZ_DATA=/app/data \
    ENERGY_VIZ_SECRET=change-me-to-a-long-random-string \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ENABLE_CORS=false \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0"]
