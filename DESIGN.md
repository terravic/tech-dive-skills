# Dashboard Design Specification

This document defines the visual, structural, accessibility, and technical specifications for the standalone interactive Bühlmann ZH-L16C + Gradient Factors Technical Dive Planner dashboard (`dashboard.html`).

---

## 1. Visual Hierarchy and Typography Rules

| Design Dimension | Specification | Implementation Standard |
|---|---|---|
| **Typography** | Distinct typographic hierarchy across prose, headers, and tabular telemetry. | Pair a clean sans-serif UI font (`DM Sans`, `system-ui`, `sans-serif`), a serif display font (`Instrument Serif`, `Georgia`, `serif`), and a tabular monospaced font (`IBM Plex Mono`, `monospace`) with `font-variant-numeric: tabular-nums`. Load local/system font stacks without external font network requests. |
| **Surfaces and Depth** | Flat, solid surface tokens with clear structural boundaries. | Use solid background tokens and `1px solid` borders (`6px` to `8px` radius) for card separation instead of decorative multi-stop card gradients. |
| **Container Layout** | Responsive 2x2 configuration grid paired with a stacked telemetry output region. | Partition configuration panes (`Dive Profile`, `Gas Mixes`, `Gradient Factors & Algorithm`, `Stops, Rates & RMV`) in `.planner-inputs-grid` above the KPI strip, profile chart, and schedule tables in `.planner-outputs-stack`. |
| **Status Indicators** | Text-explicit state reporting compliant with WCAG 2.2 AA. | Pair color cues with explicit bracketed text tags (`[NOMINAL]`, `[DECO REQUIRED]`, `[CAUTION >80%]`, `[CRITICAL >100%]`, `[OK]`, `[OVER GF]`) rather than relying on color alone or decorative icons. |
| **Background Surfaces** | Uncluttered viewport backgrounds across planner and utility workspaces. | Reserve dashed gridlines strictly for the quantitative dual Y-axis dive profile chart (`Depth` and `PO2 (ATA)`). |
| **Control Surfaces** | Clear header grouping with explicit labels and accessible icon-only theme buttons. | Stack the **Profile** selector and profile action buttons (`.navbar-profile-row`) above a dedicated single-line settings row (`.navbar-settings-row`) housing the `OC`/`CCR` toggle, `FT / CUFT` vs. `M / LITERS` toggle, and icon-only Light/Dark/System theme controls. |

---

## 2. Runtime Environment and Technical Architecture

* **Self-Contained Offline Execution:** `dashboard.html` runs directly from local disk (`file://`) or any static webview using standard HTML5, CSS custom properties, SVG, and vanilla JavaScript with zero external network requests.
* **Content Security Policy:** The document head enforces a strict offline `<meta http-equiv="Content-Security-Policy">` (`default-src 'none'; connect-src 'none'; img-src 'none'; font-src 'self' data:`) and `<meta name="referrer" content="no-referrer" />`.
* **Dynamic State Updates:** Client-side recalculation via the embedded Bühlmann ZH-L16C + Gradient Factors solver updates KPI cards, the dual Y-axis SVG profile chart, tables, and utility calculators without resetting scroll position or active tab selection.
* **Local Persistence and Data Controls:** Custom profiles (`zhl16c-custom-profiles`) and theme mode (`theme-preference`) persist exclusively in browser `localStorage`, with JSON `Export`, validated JSON `Import`, per-profile `Delete`, and single-action `Clear Local Data`.

---

## 3. Light, Dark, and System Theme Specifications

The dashboard natively supports Light Mode, Dark Mode, and System Mode tracking the operating system color-scheme preference.

* **Three-Button Theme Selector:** Placed on the dedicated global settings row (`.navbar-settings-row`) directly underneath the **Profile** selector alongside `OC`/`CCR` and `FT / CUFT` / `M / LITERS`, the theme switcher is a segmented control containing three icon-only inline SVG buttons (`30x30px` circular hit targets, `aria-hidden="true"` on the SVG elements, with explicit `title`, `aria-label`, and `aria-pressed` attributes and no visible text labels):
  * **Light Mode (`#theme-btn-light`):** Sun SVG icon (`title="Light Theme"`, `aria-label="Light Theme"`, `data-theme-mode="light"`).
  * **Dark Mode (`#theme-btn-dark`):** Crescent Moon SVG icon (`title="Dark Theme"`, `aria-label="Dark Theme"`, `data-theme-mode="dark"`).
  * **System Mode (`#theme-btn-system`):** Monitor/Display SVG icon (`title="System Theme"`, `aria-label="System Theme"`, `data-theme-mode="system"`).
  * The active button receives the `active` class and `aria-pressed="true"`, and persists `theme-preference` (`light`, `dark`, or `system`) in `localStorage`.
* **System Theme Detection:** When `system` mode is active, `window.matchMedia('(prefers-color-scheme: dark)')` resolves the effective theme and listens for `'change'` events to track OS appearance updates in real time.
* **Surface, Divider, and WCAG 2.2 AA Contrast Tokens:**
  * **Light Mode:**
    * Background (`--bg-surface`): `#FAFAF9`
    * Cards & Surfaces (`--bg-card`): `#FFFFFF`
    * Subtle Fill (`--bg-subtle`): `#F5F5F4`
    * Card Dividers (`--border-color`): `#E7E5E4` (`1px solid`, `6px` to `8px` radius)
    * Interactive Control Borders (`--border-control`): `#787774` (>= 4.1:1 UI contrast)
    * Text Primary (`--text-primary`): `#1C1917` (>= 16.7:1 contrast)
    * Text Secondary (`--text-secondary`): `#57534E` (>= 6.9:1 contrast)
    * AA Accent/Status Foregrounds: `#0F766E` (Teal, 5.47:1), `#B45309` (Amber, 5.02:1), `#4338CA` (Indigo, 7.65:1), `#047857` (Emerald, 5.48:1), `#BE123C` (Rose, 6.29:1)
  * **Dark Mode:**
    * Background (`--bg-surface`): `#0D0E11`
    * Cards & Surfaces (`--bg-card`): `#16171D`
    * Subtle Fill (`--bg-subtle`): `#1E2028`
    * Card Dividers (`--border-color`): `#292A30` (`1px solid`, `6px` to `8px` radius)
    * Interactive Control Borders (`--border-control`): `#6E707A` (>= 3.6:1 UI contrast)
    * Text Primary (`--text-primary`): `#ECE8E2` (>= 14.6:1 contrast)
    * Text Secondary (`--text-secondary`): `#9A9895` (>= 5.6:1 contrast)
    * AA Accent/Status Foregrounds: `#2DD4BF` (Teal, 9.61:1), `#F59E0B` (Amber, 8.33:1), `#818CF8` (Indigo, 5.99:1), `#34D399` (Emerald, 9.30:1), `#FB7185` (Rose, 6.64:1)

---

## 4. Dashboard Layout, Accessibility, and Component Rules

* **Semantic Landmarks and Heading Hierarchy:** Enforce `<header>`, `<nav>`, `<main id="main-content">`, and `<footer class="site-footer">` with a single `<h1>` title and logical `<h2>` card headings.
* **Keyboard Navigation and Focus Management:** Provide a `Skip to main content` link, high-contrast `:focus-visible` outlines on all interactive controls, WAI-ARIA `tablist`/`tab`/`tabpanel` arrow-key navigation across workspace/schedule/utility tabs, and keyboard scrubbing (`ArrowLeft`, `ArrowRight`, `Home`, `End`, `Escape`) on the dive profile SVG chart.
* **Tables:** Render decompression stops, cylinder gas logistics, 16-compartment tissue tensions, and utility outputs in monospaced tabular numerals (`IBM Plex Mono`, `tabular-nums`) with `<th scope="col">` column headers.
* **Dual Y-Axis Dive Profile Chart:** Plot actual depth, Gradient Factor decompression ceiling, decompression stop markers, and inspired `PO2 (ATA)` deterministically in inline SVG with mouse hover and keyboard crosshair telemetry inspection (`#chart-hover-tooltip`).

---

## 5. Data Visualization Color Palette

Charts and tissue loading indicators use a consistent semantic color palette paired with high-contrast text tokens in both themes:

| Color Role | Hex Code | Visual Application |
|---|---|---|
| **Vibrant Teal** | `#0D9488` | Actual dive depth profile path, nominal tissue loading fill. |
| **Energetic Amber** | `#D97706` | Decompression stop markers, elevated tissue loading warning fill. |
| **Vivid Indigo** | `#4F46E5` | Inspired `PO2 (ATA)` secondary series path. |
| **Functional Emerald** | `#059669` | Nominal physiological and reserve status graphics. |
| **Deep Rose** | `#E11D48` | Gradient Factor decompression ceiling path, critical threshold fill. |

---

## 6. Verification Checklist

1. Does `scripts/build_dashboard.py` produce a self-contained offline `dashboard.html` enforcing CSP `default-src 'none'; connect-src 'none'` with zero external network or font calls?
2. Does the theme selector render the three accessible icon-only inline SVG buttons (`#theme-btn-light`, `#theme-btn-dark`, `#theme-btn-system`) with real-time OS `prefers-color-scheme: dark` tracking?
3. Do Light Mode and Dark Mode satisfy WCAG 2.2 AA contrast ratios (>= 4.5:1 normal text, >= 3.0:1 UI control borders) across default, hover, and `:focus-visible` states?
4. Are all dynamic DOM insertions HTML-escaped and imported JSON profiles validated against size, schema, and unsafe object keys?
5. Are all workspace tabs, tables, form inputs, tissue progress bars, and the SVG profile chart fully keyboard-accessible with explicit textual status indicators?