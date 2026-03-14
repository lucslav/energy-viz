# Energy Viz — Privacy & Data Storage

## What is stored and where

All data lives exclusively in the Docker volume mounted at `/app/data`.
**Nothing leaves your server.** No analytics, no telemetry, no cloud sync.

```
/app/data/
├── config.json        ← tariff rates, discount %, MPRN, supplier,
│                          billing period dates — plain JSON, readable
├── api_key.enc        ← AI provider key (ONLY if you choose "Save to disk")
│                          AES-256 Fernet encrypted, unreadable without the secret
├── invoice.pdf        ← last uploaded electricity bill
└── hdf/
    ├── calckWh.csv    ← last uploaded 30-min kWh file
    ├── kw.csv         ← last uploaded kW demand file
    ├── dnp.csv        ← last uploaded Daily DNP file
    └── daily.csv      ← last uploaded Daily kWh file
```

## API Key — two storage options

| Option | Where stored | Survives restart? | Who can read it? |
|--------|-------------|-------------------|------------------|
| 🔒 Session only (default) | Browser memory | ❌ No | Only current browser tab |
| 💾 Save to disk | `/app/data/api_key.enc` | ✅ Yes | Only this server |

The saved key is encrypted with AES-256 (Fernet). The encryption key is
derived from `ENERGY_VIZ_SECRET` — **set this to a unique random value**
in `docker-compose.yml` before first run. Without the secret, the file
is unreadable even if someone copies it.

Generate a secret:
```bash
openssl rand -hex 32
```

## What is NOT stored

- Your name or address (visible in the invoice PDF you upload, but not extracted)
- Historical usage beyond what's in the HDF files you upload
- Any data on Anthropic/OpenAI/Google/Mistral servers beyond the API call
- Browser cookies or tracking

## Deleting all data

In the sidebar: **🗑️ Clear all saved data** (requires double confirmation).

Or manually:
```bash
# Remove the named volume entirely
docker volume rm energy-viz-data

# Or just clear the contents (keeps the volume)
docker run --rm -v energy-viz-data:/data alpine sh -c "rm -rf /data/*"
```

## Backing up

```bash
# Create backup archive
docker run --rm \
  -v energy-viz-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/energy-viz-backup-$(date +%Y%m%d).tar.gz /data

# Restore from backup
docker run --rm \
  -v energy-viz-data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/energy-viz-backup-20260314.tar.gz -C /
```
