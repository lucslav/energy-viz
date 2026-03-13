# ⚡ Energy Viz

Professional Smart Meter Analytics Dashboard designed for ESB Networks (Ireland) HDF files.

![Logo](https://raw.githubusercontent.com/lucslav/energy-viz/main/img/logo.png)

## 🚀 Docker Hub
Project available at: **[lucslav/energy-viz](https://hub.docker.com/r/lucslav/energy-viz)**

---

## ✨ Main Features

* **Dynamic Unit Switching:** Live toggle between **Usage (kWh)** and **Cost (€)** views within the primary consumption panel.
* **Extended Analytics Suite:** Detailed summary cards providing Total, Daily Average, and Monthly Average metrics for both energy and cost.
* **Interactive Navigation:** Range sliders and scroll-to-zoom enabled on all charts for high-precision historical data browsing.
* **Contextual Documentation:** Source-specific guides and interpretation labels integrated directly under section headers.
* **Smart File Detection:** Automatically recognizes ESB file types (30-min kWh, kW demand, Daily DNP, or Cumulative) and adapts the dashboard logic.
* **Detailed Tariff Analysis:** Precise breakdown into **Day, Night, and Peak** periods based on Irish utility standards.
* **Power Demand Monitoring:** High-visibility visualization of power spikes (kW) to identify peak household loads.
* **Automatic Financial Calculation:** Integrated Irish 9% VAT and 4-decimal rate precision including daily standing charges.
* **Flat Architecture:** Minimalist interface utilizing transparent containers and thin technical typography.

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
    volumes:
      - /path/to/your/data:/app/data
    restart: unless-stopped
