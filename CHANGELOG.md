# Changelog

All notable changes to **energy-viz** are documented here.

---

## [2.0.0] - 2026-03-14

Major rewrite. The core app architecture was rebuilt with AI assistance (vibe coding session). Most of the codebase changed.

### Added

**Persistence layer**
- All user data (HDF files, tariff config, billing period, invoice PDF) now survive container restarts and image rebuilds via Docker volume at `/app/data`
- Config saved as `config.json`, HDF files stored as named CSVs, invoice as `invoice.pdf`
- First-run setup screen auto-skipped if valid config is found on startup

**AI invoice parser**
- Upload a PDF electricity bill to auto-extract tariff rates, standing charge, discount and billing period
- Multi-provider support: Anthropic Claude (recommended), Google Gemini (2.5/2.0 Flash), OpenRouter, OpenAI GPT-4o
- Uses official SDKs (`google-genai`, `anthropic`, `openai`) — replaces raw `urllib` calls
- API key privacy options: session-only (default) or AES-256 Fernet encrypted on disk
- Per-provider key storage — switching providers pre-fills the correct saved key
- OpenRouter support with custom model ID input (access to 200+ models including free ones)

**Overview tab redesign**
- Period selector: Week / Month / Bill / Total — filters all metrics and chart dynamically
- New KPI: Avg Daily Cost (€/day)
- Removed "Last 30 days" hardcoded filter

**Consumption tab**
- Default date range now starts from the beginning of the HDF file (was last 14 days)
- kWh / € view toggle moved inline next to date range
- Range selector buttons: 1d / 1w / 2w / 1m / 3m / 1y / All

**Power Demand tab**
- Default date range now full HDF range
- Same range selector buttons as Consumption

**Sidebar redesign**
- Compact file cards showing persisted filename from disk
- Per-slot status: 💾 saved (with filename) or ○ not loaded
- Removed non-functional "Primary view" (kWh/€) toggle
- Removed "Apply discount" toggle — discount from config always applied
- Removed orphaned "Settings" section header

**Data quality**
- DST clock-back (Oct 26) correctly handled — both 01:00 and 01:30 slots preserved
- Daily kWh outlier filter (meter rollover artifacts like 9,311,406 kWh auto-removed)
- Quality report shown in Raw Data tab per file

### Changed

- Plotly `fillcolor` — all 8-char hex+alpha strings (e.g. `#bc8cff22`) replaced with `rgba()` via `_rgba()` helper — fixes Plotly `ValueError` on all chart tabs
- `COLORS` dict — added aliases: `blue`, `cyan`, `purple` — fixes `KeyError` on Bill Prediction tab
- `add_vline(x=...)` — fixed `TypeError` from passing `str(date)` to Plotly; converted to millisecond timestamp
- `cumtotal` calculation — fixed `TypeError: cannot perform __mul__ with DatetimeArray`; replaced `.apply(lambda)` with vectorised pandas arithmetic
- Legend position moved below chart (`y=-0.15`) — no longer overlaps range selector buttons
- Legend and axis tick fonts explicitly set to `COLORS["text"]` — fixes invisible grey legend labels
- KPI card values set to `#ffffff` — white instead of muted grey
- `st.metric` values set to `#ffffff`
- Subtitle no longer shows supplier name from session state
- All inline HTML CSS variables (`var(--text-muted)` etc.) replaced with hardcoded hex — fixes invisible text in sidebar
- `google-generativeai` (deprecated Nov 2025) replaced with `google-genai` SDK

### Fixed

- `StreamlitAPIException: multiple identical forms with key='manual_setup'` — unique form keys per context
- Setup screen "Confirm & Continue" button had no effect — fixed with `_show_review` session state flag and `st.rerun()`
- Gemini 404 errors from deprecated model names (`gemini-1.5-flash`, `gemini-2.0-flash`) — updated to current model IDs
- OpenRouter 404 from retired `google/gemini-2.0-flash-exp:free` — updated default to `google/gemini-2.5-flash-lite`
- Truncated JSON from AI invoice parser — added `response_mime_type="application/json"` for Gemini, increased `max_tokens` to 2048

---

## [1.1.0] - 2026-03-13

### Added
- Unit view toggle: dynamic switching between kWh and € in consumption panel
- Contextual documentation: source-specific guides and interpretation labels under section headers
- Extended analytics: monthly/daily averages for cost and usage
- Global range controls: range sliders and scroll-zoom on all interactive charts

### Changed
- Interface architecture: flat layout with transparent component containers
- Typography: standardised to thin, technical font weights
- Rate engine: 4-decimal precision with standing charge and VAT integration
- Sidebar: updated layout with border-based separation

### Fixed
- Block 4 logic: corrected delta/register calculation errors
- Outlier filtering: improved ESB glitch protection for data ingestion

---

## [1.0.0] - 2026-03-11

### Added
- Smart file detection: automatic recognition of 4 ESB HDF file types
- Power demand mode: high-visibility charts for kW spikes
- 24h tariff label: unified labelling for daily total files
- Professional UX: technical tone throughout

### Changed
- UI styling: enhanced KPI metrics and branding
- Tax logic: improved 9% VAT calculation accuracy
