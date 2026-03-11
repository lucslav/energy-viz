# ⚡ Energy Viz

Professional Smart Meter Analytics Dashboard designed for ESB Networks (Ireland) HDF files. This application provides a comprehensive interface to track energy consumption and estimate electricity costs based on Irish utility standards.

![Logo](https://raw.githubusercontent.com/lucslav/energy-viz/main/img/logo.png)

## 🚀 Docker Hub
The project is automatically built and available on Docker Hub:
**[lucslav/energy-viz](https://hub.docker.com/r/lucslav/energy-viz)**

---

## ✨ Features & Capabilities

* **Interactive Visualizations:** Toggle between energy consumption (kWh) and real-time cost analysis (€).
* **Intelligent Data Correction:** Automatically detects and fixes inconsistent meter readings (e.g., Wh vs kWh unit jumps) often found in ESB export files.
* **Irish Billing Standard:** Built-in support for the 9% VAT rate applied to electricity in Ireland.
* **Dynamic Cost Estimation:** Calculates totals including energy usage, standing charges, and taxes.
* **Time-Series Analysis:** View data by daily bars or aggregate trends by week and month.
* **Mobile Optimized:** Features interactive range sliders for easy navigation on touchscreens and mobile devices.

## ⚙️ Configurable Options
Using the integrated sidebar, you can customize the analytics to match your specific utility plan:
* **Day Rate:** Standard price per kWh.
* **Peak Rate:** Premium price for usage between 17:00 - 19:00.
* **Night Rate:** Reduced price for usage between 23:00 - 08:00.
* **Daily Standing Charge:** Fixed daily cost for maintaining the connection.

---

## 🛠️ Installation (NAS / Server)

To deploy this application on any NAS or Linux server supporting Docker, use the following configuration:

### Docker Compose / YAML
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
