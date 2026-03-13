# Changelog

All notable changes to the **energy-viz** project will be documented in this file.

## [1.1.0] - 2026-03-13

### Added
- **Unit View Toggle:** Dynamic switching between kWh and Euro in the consumption panel.
- **Contextual Documentation:** Source-specific guides and interpretation labels under section headers.
- **Extended Analytics:** Added Monthly/Daily averages for both cost and usage metrics.
- **Global Range Controls:** Added Range Sliders and scroll-zoom to all interactive charts.

### Changed
- **Interface Architecture:** Flat layout utilizing transparent component containers.
- **Typography:** Standardized to thin, technical font weights across the dashboard.
- **Rate Engine:** 4-decimal precision with Standing Charge and VAT integration.
- **Sidebar:** Updated layout with border-based layout separation.

### Fixed
- **Block 4 Logic:** Corrected delta/register calculation errors.
- **Outlier Filtering:** Improved ESB glitch protection for data ingestion.

### Known Issues
- Power Demand Range Slider mini-graph rendering issues in some browsers.

## [1.0.0] - 2026-03-11

### Added
- **Smart File Detection:** Automatic recognition of 4 ESB file types.
- **Power Demand Mode:** High-visibility HV-line charts for kW spikes.
- **24h Tariff Label:** Unified labeling for basic daily total files.
- **Professional UX:** Updated all guides to an impersonal, technical tone.

### Changed
- **UI Styling:** Enhanced KPI metrics and main branding components.
- **Tax Logic:** Improved 9% VAT calculation accuracy.

### Known Issues
- Power Demand Range Slider mini-graph rendering issues in some browsers.
