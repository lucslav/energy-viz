# Changelog

All notable changes to **energy-viz** are documented here.

---

## [2.2.0] - 2026-04-09

### Added
- **ESB Auto-Sync** — automatic weekly downloads from ESB Networks portal using browser cookies (exported via [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) extension); respects ESB's 2 logins per 24h rate limit
- **Year-to-Year comparison** in Cost Breakdown tab — select any two years to compare monthly costs side-by-side with grouped bar charts and annual summary cards showing % change
- **Custom date range selector** in Overview tab — replaced "Bill" preset with custom date picker (From/To dates)
- **GitHub link** in sidebar — clickable icon next to logo linking to project repository
- **Flag icons** for language selector — SVG flags from [uxwing.com](https://uxwing.com) displayed above English/Polski buttons

### Changed
- **Consumption heatmap orientation** — newest data now displayed at top (reversed Y-axis)
- **Cookies.txt section redesigned** — removed expandable section; all fields always visible to fix persistent white button issues on desktop
- **Language selector visual refresh** — clean SVG flag images above buttons (IE for English, PL for Polski)
- **Sidebar UI polish** — improved spacing, clearer visual hierarchy

### Fixed
- **White button states** — comprehensive CSS fixes for all button states (hover, focus, active) across sidebar and main content
- **Button styling consistency** — enforced blue gradient background and white text across all interactive states
- **ESB sync UI issues** — simplified cookies.txt interface to eliminate CSS conflicts

---

## [2.1.0] - 2026-03-16

### Added
- **Bilingual support (EN / PL)** — full Polish and English translations across all 8 tabs, setup screen, sidebar and alerts. Language selected on first run and persisted in `config.json`
- **Language toggle** — English / Polski buttons at the top of the sidebar and on the setup screen
- **Tariff split follows period selector** — the Day/Peak/Night split section in Overview now filters by the selected period (Week / Month / Bill / Total) instead of always showing full history
- **Polish month names** — chart axes show Polish month abbreviations (sty, lut, mar…) when Polish is active

### Changed
- **Consumption tab redesigned** — stripped to date range selector + hourly heatmap only; the half-hourly line chart and metric cards removed as redundant with Overview
- **Discount removed** — the discount (%) field has been removed entirely; invoice-imported rates are already post-discount, so applying a separate discount multiplier was incorrect
- Monthly bill estimate legend moved below chart to avoid overlapping x-axis labels
- Load profile — added Day zone annotation (08:00–17:00); fixed annotation position

### Fixed
- **Language not persisted across restarts** — `load_config()` was skipping `lang` key; now always restored from config
- **HDF files not loading after restart** — `@st.cache_data` could not hash `BytesIO` objects; fixed with path-based caching
- **Period selector reset on language change** — radio stored text value which changed when language switched; now stores index

---

## [2.0.3] - 2026-03-15

### Fixed
- **Heatmap, Average Daily Load Profile, Average Demand by Hour** — x-axis tick marks now visible for every hour
- All three hourly charts now share identical axis style: tick marks every hour, labels every 3 hours

---

## [2.0.2] - 2026-03-15

### Changed
- **Consumption & Power Demand charts** — removed Plotly legend which conflicted with rangeselector buttons; replaced with colour-key row below the chart
- **All chart titles removed** from inside Plotly figures
- **Consumption tab** — removed kWh/€ per-interval toggle
- **Power Demand tab** — default date range changed from last 14 days to full HDF range

### Fixed
- `KeyError: 'blue'` / `KeyError: 'cyan'` / `KeyError: 'purple'` — added missing colour aliases to `COLORS` dict
- Power Demand showing values in thousands of kW (MW range) — added sanity check warning when peak > 50 kW

---

## [2.0.1] - 2026-03-15

### Fixed
- Welcome screen (no files uploaded) rendered raw HTML instead of cards
- `KeyError: 'blue'` / `KeyError: 'cyan'` / `KeyError: 'purple'` on Bill Prediction and other tabs
- `TypeError: unsupported operand type(s) for +: 'int' and 'str'` on Bill Prediction tab
- Orphaned "⚙️ Settings" section header and two stacked dividers

### Changed
- Sidebar file cards redesigned — persisted filename shown as custom HTML badge
- `COLORS` dict extended with `blue`, `cyan`, `purple` aliases

---

## [2.0.0] - 2026-03-14

Major rewrite with AI assistance. Core app architecture rebuilt.

### Added

**Persistence layer**
- All user data (HDF files, tariff config, billing period, invoice PDF) survive container restarts via Docker volume at `/app/data`

**AI invoice parser**
- Upload a PDF electricity bill to auto-extract tariff rates, standing charge, discount and billing period
- Multi-provider support: Anthropic Claude, Google Gemini, OpenRouter, OpenAI GPT-4o
- API key privacy options: session-only (default) or AES-256 encrypted on disk

**Overview tab redesign**
- Period selector: Week / Month / Bill / Total — filters all metrics and chart dynamically

**Sidebar redesign**
- Compact file cards showing persisted filename from disk
- Per-slot status: 💾 saved or ○ not loaded

**Data quality**
- DST clock-back (Oct 26) correctly handled
- Daily kWh outlier filter (meter rollover artifacts auto-removed)

### Changed
- Plotly `fillcolor` — all 8-char hex+alpha strings replaced with `rgba()` helper
- Legend position moved below chart — no longer overlaps range selector buttons
- `google-generativeai` (deprecated Nov 2025) replaced with `google-genai` SDK

### Fixed
- `StreamlitAPIException: multiple identical forms` — unique form keys per context
- Setup screen "Confirm & Continue" button had no effect
- Gemini 404 errors from deprecated model names
- Truncated JSON from AI invoice parser

---

## [1.1.0] - 2026-03-13

### Added
- Unit view toggle: dynamic switching between kWh and € in consumption panel
- Contextual documentation: source-specific guides under section headers
- Extended analytics: monthly/daily averages for cost and usage
- Global range controls: range sliders and scroll-zoom on all charts

### Changed
- Interface architecture: flat layout with transparent containers
- Typography: standardised to thin, technical font weights
- Rate engine: 4-decimal precision with standing charge and VAT integration

### Fixed
- Block 4 logic: corrected delta/register calculation errors
- Outlier filtering: improved ESB glitch protection

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
