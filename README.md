# ⚡ Energy Viz

Professional Smart Meter Analytics Dashboard designed for ESB Networks (Ireland) HDF files.

![Logo](https://raw.githubusercontent.com/lucslav/energy-viz/main/img/logo.png)

## 🚀 Docker Hub
Project available at: **[lucslav/energy-viz](https://hub.docker.com/r/lucslav/energy-viz)**

---

## ✨ Main Features

* **Smart File Detection:** Automatically recognizes different ESB file types (30-min kWh, kW demand, Daily DNP, or Cumulative) and adapts the dashboard.
* **Detailed Tariff Analysis:** Precise breakdown of usage and costs into **Day, Night, and Peak** periods based on 30-minute intervals.
* **Power Demand Monitoring:** Detects and visualizes power "spikes" (kW) to identify high-load moments in your household.
* **Automatic Cost Calculation:** Includes the Irish 9% VAT and daily standing charges for realistic bill estimation.
* **Usage Trends:** Interactive charts showing energy consumption and costs across daily, weekly, and monthly scales.
* **Data Auto-Correction:** Fixes common inconsistencies in ESB export files, such as unit jumps (Wh vs kWh).



---

## 📂 Data Recommendation
For the best experience, use the **"30-minute readings in calculated kWh"** file from the ESB Networks portal.

---

## 🛠️ Installation (Docker Compose)

```yaml
name: energy-viz
services:
  app:
    image: lucslav/energy-viz:latest
    container_name: energy-viz-prod
    network_mode: bridge
    ports:
      - "8501:8501"
    restart: unless-stopped
