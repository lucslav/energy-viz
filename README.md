# <img src="https://raw.githubusercontent.com/lucslav/energy-viz/main/img/logo.png" alt="Energy Viz logo" width="32" style="vertical-align:middle"> Energy Viz

[![Version](https://img.shields.io/badge/version-2.2.0-58a6ff?style=flat-square)](https://github.com/lucslav/energy-viz/releases)
[![Docker](https://img.shields.io/badge/docker-lucslav%2Fenergy--viz-0db7ed?style=flat-square&logo=docker&logoColor=white)](https://hub.docker.com/r/lucslav/energy-viz)
[![Built with Streamlit](https://img.shields.io/badge/built%20with-Streamlit-ff4b4b?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io)
[![Python](https://img.shields.io/badge/python-3.12-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-3fb950?style=flat-square)](LICENSE.txt)
[![Vibe Coded](https://img.shields.io/badge/vibe%20coded-%F0%9F%8E%B8-bc8cff?style=flat-square)](https://github.com/lucslav/energy-viz)
[![Ireland](https://img.shields.io/badge/made%20for-Ireland%20%F0%9F%87%AE%F0%9F%87%AA-169b62?style=flat-square)](https://github.com/lucslav/energy-viz)

> **Hobby project — vibe coded with AI assistance (thanks @badger-dev).** A personal smart meter analytics dashboard for Irish electricity customers using ESB Networks HDF export files. Built with Streamlit and Plotly for self-hosting on a home server or NAS. Not affiliated with ESB Networks or any energy supplier.

---

## 🤔 What is this?

Irish smart meters export your half-hourly electricity data as CSV files from the [ESB Networks portal](https://myaccount.esbnetworks.ie/Api/HistoricConsumption). These files are accurate and detailed — but pretty useless without something to visualise them.

Energy Viz takes those raw CSV exports and turns them into an interactive dashboard: consumption charts, cost breakdowns, bill prediction, standby load analysis and more. Everything runs locally in Docker. No data leaves your server.

---

## 🔒 Privacy & Security

**Your data never leaves your server.** Energy Viz is designed for complete privacy:

### What gets stored locally
All data is saved to a Docker volume at `/app/data`:

| File | What it contains | Encrypted? |
|------|------------------|------------|
| `config.json` | Language preference, tariff rates, billing period, MPRN | ❌ Plain text |
| `hdf/*.csv` | Your uploaded HDF files (consumption data) | ❌ Plain text |
| `invoice.pdf` | Your uploaded electricity bill PDF (optional) | ❌ Plain text |
| `api_key.enc` | AI provider API key (if you choose to save it) | ✅ AES-256 |
| `esb_cookies.txt` | Browser cookies for ESB Auto-Sync (optional) | ❌ Plain text |
| `sync_status.json` | ESB Auto-Sync status and timestamps | ❌ Plain text |

### ESB Auto-Sync (optional)
Skip manual file uploads — let Energy Viz fetch your latest data automatically:

- **How it works**: You provide browser cookies from `myaccount.esbnetworks.ie` (exported via browser extension)
- **What it does**: Weekly automatic sync to download latest HDF files
- **Authentication**: Uses your existing ESB session (no password storage)
- **Rate limits**: Respects ESB's 2 logins per 24h limit
- **Your control**: Disable anytime by clearing cookies

### AI invoice parser (optional)
If you use the PDF invoice parser:
- API calls go directly to your chosen provider (Anthropic, Google, OpenRouter, OpenAI)
- **Session-only mode** (default): API key stored in memory, cleared on restart
- **Encrypted mode** (opt-in): API key encrypted with AES-256 and saved to disk
- Encryption key derived from `ENERGY_VIZ_SECRET` environment variable
- **You control the key**: Change `ENERGY_VIZ_SECRET` before first run

### Network access
- **Inbound**: Only your browser connects to the Streamlit web UI (port 8501)
- **Outbound**: Only if you enable ESB Auto-Sync or use AI invoice parser
- **Docker network**: Isolated bridge mode (no host network exposure)

---

## ✨ Features

### 8 analysis tabs

| Tab | What you get |
|-----|-------------|
| 📊 **Overview** | Key metrics with custom date range or presets (Week/Month/Total), daily tariff energy chart, Day/Peak/Night split |
| 🔌 **Consumption** | Half-hourly kWh or € with full date range, hourly heatmap (newest data at top) |
| ⚡ **Power Demand** | Instantaneous kW chart, spike detection (>p99), load duration curve, average demand by hour |
| 📅 **Daily Analysis** | Night/Day/Peak register deltas, cumulative totals, invoice register cross-check |
| 💶 **Cost Breakdown** | Donut chart by tariff period, monthly bill estimate, **year-to-year comparison** with grouped bar charts |
| 🔍 **Advanced Insights** | Seasonal & monthly trend, weekday vs weekend, standby load calculator, peak-shifting savings estimator |
| 🔮 **Bill Prediction** | Billing period progress bar, 3 forecast methods (simple / seasonal / 14-day rolling), cumulative projection |
| 📋 **Raw Data** | Data quality report, DST handling notes, browse & download all datasets |

### Year-to-year cost analysis (NEW in 2.2.0)
Compare your electricity costs across years:
- **Select any two years** to compare side-by-side
- **Monthly comparison**: Grouped bar charts showing same month across different years
- **Annual summary cards**: Total cost, kWh consumed, and % change with visual indicators
- **Identify trends**: Spot seasonal patterns and long-term cost changes

### ESB Auto-Sync (NEW in 2.2.0)
Automatic weekly downloads from ESB Networks portal:
- **No manual uploads**: Energy Viz fetches your latest HDF files automatically
- **Browser cookie auth**: Export cookies once using [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) extension
- **Sync log viewer**: See sync history and status in sidebar
- **Rate limit aware**: Respects ESB's 2 logins per 24h limit

### AI invoice parser
Automatically extracts tariff rates, standing charge, discount % and billing period from your PDF electricity bill:

| Provider | PDF support | Free tier |
|----------|------------|-----------|
| **Anthropic Claude 3.5 Sonnet** | ✅ Native | $5 credit on signup |
| **Google Gemini 2.5 / 2.0 Flash** | ✅ Native | Yes (quota limits apply) |
| **OpenRouter** | ✅ Via routing | Many free models |
| **OpenAI GPT-4o** | ⚠️ As image | Paid |

---

## 📂 HDF file types

Download your data from the [smart meter portal](https://myaccount.esbnetworks.ie/Api/HistoricConsumption) or enable ESB Auto-Sync.

| File prefix | Contains | Required? |
|-------------|---------|-----------|
| `HDF_calckWh_…csv` | 30-min kWh intervals with Day/Peak/Night tariff split | ⭐ Primary |
| `HDF_kW_…csv` | Instantaneous power demand in kW | Optional |
| `HDF_DailyDNP_kWh_…csv` | Cumulative daily Night/Day/Peak registers | Optional |
| `HDF_Daily_kWh_…csv` | Single 24h cumulative register (no tariff split) | Optional |

> ESB exports your **full history** (up to 13 months) in every download — just upload the latest file, no manual merging needed.

---

## 🛠️ Installation

### Self-hosted NAS / home server

**⚠️ IMPORTANT**: Set a unique `ENERGY_VIZ_SECRET` before first run:
```bash
openssl rand -hex 32
```

### Docker Compose

```yaml
name: energy-viz
services:
  energy-viz:
    image: lucslav/energy-viz:latest
    container_name: energy-viz
    restart: unless-stopped
    ports:
      - "8501:8501"
    volumes:
      - energy-viz-data:/app/data
    environment:
      - ENERGY_VIZ_SECRET=change-me-to-a-long-random-string  # Use openssl rand -hex 32
      - ENERGY_VIZ_DATA=/app/data
    network_mode: bridge

volumes:
  energy-viz-data:
```

### Local development

```bash
git clone https://github.com/lucslav/energy-viz.git
cd energy-viz
pip install -r requirements.txt
export ENERGY_VIZ_SECRET=$(openssl rand -hex 32)
ENERGY_VIZ_DATA=./data streamlit run app.py
```

---

## ⚙️ Configuration

On first run you'll see a setup screen to configure your tariff. You can either:
- **Upload a PDF bill** — AI extracts rates, standing charge, discount and billing period automatically
- **Enter rates manually** — if you know your tariff or don't have an API key

All settings are saved to `/app/data/config.json` and restored automatically on restart.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENERGY_VIZ_DATA` | `/app/data` | Path to the persistent data directory (Docker volume mount point) |
| `ENERGY_VIZ_SECRET` | `change-me-…` | **Must be changed!** Used for AES-256 API key encryption. Generate with `openssl rand -hex 32` |

---

## 📦 Requirements

```
streamlit >= 1.35.0
pandas >= 2.0.0
plotly >= 5.18.0
numpy >= 1.26.0
cryptography >= 42.0.0
google-genai >= 1.0.0
anthropic >= 0.40.0
openai >= 1.30.0
```

---

## 🙏 Credits

The automated data synchronization module in this project is based on the research and session management techniques developed by **[badger707](https://github.com/badger707/esb-smart-meter-reading-automation)**. 

His work on navigating the ESB Networks portal architecture provided the foundational logic for the authentication and download processes implemented in this dashboard.

---

## ⚠️ Disclaimer

This is a hobby project built for personal use and shared as-is. Cost and bill calculations are estimates based on manually entered tariff rates — always verify against your actual electricity bill. Not affiliated with ESB Networks, Electric Ireland, or any energy supplier or regulator.

---

## 📄 License

[MIT](LICENSE.txt) © 2026 lucslav
