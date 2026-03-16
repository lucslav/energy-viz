# Changelog

All notable changes to **energy-viz** are documented here.

---

## [2.1.0] - 2026-03-16

### Added
- **Bilingual support (EN / PL)** — full Polish and English translations across all 8 tabs, setup screen, sidebar and alerts. Language selected on first run and persisted in `config.json`
- **Language toggle** — `🇮🇪 English` / `🇵🇱 Polski` buttons at the top of the sidebar and on the setup screen
- **Tariff split follows period selector** — the Day/Peak/Night split section in Overview now filters by the selected period (Week / Month / Bill / Total) instead of always showing full history
- **Polish month names** — chart axes show Polish month abbreviations (sty, lut, mar…) when Polish is active, via `st.components.v1.html` JS injection

### Changed
- **Consumption tab redesigned** — stripped to date range selector + hourly heatmap only; the half-hourly line chart and metric cards removed as redundant with Overview
- **Tariff Split section renamed** — "Full-Period Tariff Split" → "Tariff Split" / "Podział taryfy"; current period shown in badge instead of in the title
- **Discount removed** — the discount (%) field has been removed entirely; invoice-imported rates are already post-discount, so applying a separate discount multiplier was incorrect. `DISC_FACTOR` is now always 1.0
- **Consumption tab metrics replaced** — removed Gross cost and Net cards; replaced with Total kWh, Daily avg and Peak day
- **"Standby" → "Czuwanie"** in all Polish labels
- **"kWh/rok (est.)"** → **"kWh/rok (szac.)"** in Polish
- **"Weekday vs Weekend"** → **"Dni robocze / Weekend"** in Polish
- **"net"** → **"netto"** in all Polish labels
- Monthly bill estimate legend moved below chart to avoid overlapping x-axis labels
- Cumulative register values legend moved below chart
- Load profile — added Day zone annotation (08:00–17:00); fixed annotation position so Day and Peak labels don't overlap
- README Installation section made platform-agnostic (removed CasaOS-specific instructions)

### Fixed
- **Language not persisted across restarts** — `load_config()` was skipping `lang` key because `"en"` didn't match the `(None, "", [], {})` empty-value check; now always restored from config
- **HDF files not loading after restart** — `@st.cache_data` could not hash `BytesIO` objects; `_resolve()` now returns a path string for persisted files, and `_open_hdf()` opens it as `BytesIO` at call time; added `hash_funcs={io.BytesIO: lambda x: x.getvalue()}` to all load functions
- **Period selector reset on language change** — radio stored text value which changed when language switched; now stores index in `session_state["ov_period_i"]`
- Various `{t("key")}` strings appearing as literal text in HTML blocks due to missing `f` prefix on `st.markdown()` calls
- `t()` called inside `TRANSLATIONS` dict definition (before function was defined), causing `NameError` on startup — fixed across multiple rounds

---

## [2.0.3] - 2026-03-15

### Fixed
- **Heatmap, Average Daily Load Profile, Average Demand by Hour** — x-axis tick marks now visible for every hour; previously empty string `""` in `ticktext` suppressed tick marks entirely; replaced with `" "` (space) + `ticks="outside"` + `ticklen=4` to force rendering of unlabeled ticks
- **Average Demand by Hour** — x-axis changed from numeric integers (`0–23`) to string labels (`"00:00"–"23:00"`) to match the same `tickvals` approach as the other two charts
- All three hourly charts now share identical axis style: tick marks every hour, labels every 3 hours (`00:00, 03:00 … 21:00`), font size 9, angle −45°

---

## [2.0.2] - 2026-03-15

### Changed
- **Consumption & Power Demand charts** — removed Plotly legend which conflicted with rangeselector buttons on all screen sizes; replaced with a colour-key row below the chart using a flex spacer (`min-width:55px`) that aligns exactly with the plot area start
- **All chart titles removed** from inside Plotly figures — section headers above each chart already provide context; removing titles frees space and eliminates overlap with rangeselector buttons on mobile
- **Consumption tab** — removed kWh/€ per-interval toggle; half-hourly cost in cents-per-slot was confusing; cost analysis belongs in Cost Breakdown tab
- **Power Demand tab** — default date range changed from last 14 days to full HDF range
- **Sidebar buttons** — "Re-parse invoice / Change rates" and "Clear all saved data" now use `use_container_width=True` to prevent text wrapping on narrow sidebar

### Fixed
- `KeyError: 'blue'` / `KeyError: 'cyan'` / `KeyError: 'purple'` — added missing colour aliases to `COLORS` dict
- Power Demand showing values in thousands of kW (MW range) — was caused by stale `df_f` pointing to `df_calc` from a previous session; added sanity check warning when peak > 50 kW
- Plotly annotation-based colour key (`xref="paper", y=1.01`) overlapped rangeselector buttons — removed in favour of HTML approach below the chart
- Average Daily Load Profile x-axis — 48 half-hourly labels overlapping; reduced to hourly ticks with `tickmode="array"` every 4 slots, font size 9, angle −45°

---

## [2.0.1] - 2026-03-15

### Fixed
- Welcome screen (no files uploaded) rendered raw HTML instead of cards — replaced large multi-line `st.markdown()` block with small per-column calls that Streamlit renders reliably
- `KeyError: 'blue'` / `KeyError: 'cyan'` / `KeyError: 'purple'` on Bill Prediction and other tabs — added missing aliases to `COLORS` dict
- `TypeError: unsupported operand type(s) for +: 'int' and 'str'` on Bill Prediction tab — `add_vline(x=str(b_end))` replaced with millisecond timestamp `pd.Timestamp(b_end).timestamp() * 1000`
- `TypeError: cannot perform __mul__ with this index type: DatetimeArray` on Bill Prediction / Advanced Insights — vectorised pandas arithmetic replaces `.apply(lambda)` for cumulative standing charge calculation
- Orphaned "⚙️ Settings" section header and two stacked dividers remaining after discount toggle removal
- "Apply 0% discount" toggle had no visible effect — removed; discount from tariff config is now always applied via `DISC_FACTOR`

### Changed
- Sidebar file cards redesigned — persisted filename shown as a custom HTML badge instead of relying on Streamlit's `stFileUploaderFile` component (which rendered on a white background that CSS could not override)
- `COLORS` dict extended with `blue`, `cyan`, `purple` aliases for forward compatibility

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
