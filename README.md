# ⚡ Energy Viz

Professional Smart Meter Analytics Dashboard for ESB Networks (Ireland) HDF files. 
Track your energy consumption and estimated costs with a modern, responsive interface.

![Logo](https://raw.githubusercontent.com/lucslav/energy-viz/main/img/logo.png)

## 🚀 Docker Hub
The project is automatically built and pushed to Docker Hub:
**[lucslav/energy-viz](https://hub.docker.com/r/lucslav/energy-viz)**

---

## 🛠️ NAS / CasaOS Installation

To deploy this on your TerraMaster or any NAS using CasaOS:

1. Open **App Store** in CasaOS.
2. Click **Custom Install** (top right).
3. Click the **Import** icon and paste this YAML:

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
    x-casaos:
      icon: [https://raw.githubusercontent.com/lucslav/energy-viz/main/img/logo.png](https://raw.githubusercontent.com/lucslav/energy-viz/main/img/logo.png)
