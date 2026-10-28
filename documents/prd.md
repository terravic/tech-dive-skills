# Product Requirements Document (PRD): Technical Scuba Dive Planner Skill (`tech-dive-planner`)

**Version:** 2.3  
**Skill Identifier:** `tech-dive-planner`  
**Primary Instruction File:** `SKILL.md`  
**Design Specification:** `DESIGN.md`  
**Core Engine Script:** `scripts/zhl16c_planner.py`  
**Dashboard Generator Script:** `scripts/build_dashboard.py`  
**Standalone Dashboard Output:** `dashboard.html`  
**License:** Apache License 2.0 (`LICENSE`)

---

## 1. User Stories and Scope

### 1.1 Target Audience
The `tech-dive-planner` skill serves two primary user groups across command-line and conversational agent environments:

1. **Technical and Recreational Scuba Divers, Gas Blenders, and Instructors (Domain Users):**
   - Open Circuit (OC) technical divers planning multi-gas nitrox or trimix decompression dives.
   - Closed Circuit Rebreather (CCR) divers planning constant-setpoint loop dives alongside emergency open-circuit bailout schedules.
   - Gas blenders calculating partial-pressure nitrox/trimix fill cascades, residual tank bleed-downs, top-up mixes, and real-gas ($Z$-factor) cylinder fill capacities.
2. **Non-Technical Conversational Users:**
   - Users interacting via natural-language prompts who require deterministic answers to practical questions such as *"How deep can I go on an AL80 with EAN32?"* or *"I want to dive to 200 feet for 25 minutes; pick the best bottom and deco gases and build my decompression schedule."*

### 1.2 User Stories
- **US-01 (Depth and Time to Best Gas and Decompression Plan):** As a diver specifying a target depth and bottom time, I want the skill to calculate the optimal bottom gas mix and decompression gas mixes and generate a complete Bühlmann ZH-L16C + Gradient Factors ascent schedule.
- **US-02 (Tank Size and Gas Type to Maximum Depth Envelope):** As a diver specifying my cylinder size (for example, `AL80`, `LP85`, `2xLP85`, `12L`, `D12`) and gas mix (`Air`, `EAN32`, `Trimix`, or custom), I want to know the maximum safe depth and bottom time bounded by oxygen toxicity (MOD), narcosis (MND), gas density (MDD), and usable tank volume.
- **US-03 (No-Decompression Limit and Maximum Bottom Time):** As a diver specifying a target depth and gas mix, I want to know my exact No-Decompression Limit (NDL), tank-limited maximum bottom time, and CNS oxygen toxicity limit.
- **US-04 (Minimum Gas / Rock Bottom and Turn Pressure):** As a diver planning a team dive, I want to calculate the exact cylinder turn pressure and minimum reserve ("rock bottom") required for two divers sharing gas at a stressed ventilation rate during emergency ascent to the first decompression gas switch or surface.
- **US-05 (Gradient Factor and Lost-Gas Sensitivity Analysis):** As a technical diver, I want to compare decompression schedules across different Gradient Factor pairs (`GF Low / GF High`) or lost-decompression-gas failure modes.
- **US-06 (Repetitive Dive and Surface Interval Tracking):** As a diver executing multiple dives in a day, I want the skill to track 16-compartment Nitrogen and Helium off-gassing and CNS toxicity decay across a surface interval and apply residual tissue loading to the subsequent dive.
- **US-07 (CCR Constant Setpoint and Bailout Cylinder Sizing):** As a rebreather diver configuring my loop diluent, setpoint (in `ATA` or `BAR`), and open-circuit bailout gas list, I want both my primary CCR decompression schedule and a worst-case open-circuit bailout decompression and cylinder volume sufficiency plan.
- **US-08 (Diver Utility and Gas Blender Calculators):** As a diver or gas blender, I want dedicated tools for Equivalent Air Depth (EAD), Equivalent Narcotic Depth (END), Maximum Operating Depth (MOD), Best Mix for Depth, Gas Density ($\text{g/L}$), and Nitrox/Trimix Partial-Pressure Blending, Top-Up, and Cylinder Fill Capacity.
- **US-09 (Interactive Standalone Dashboard and Profile Management):** As a user reviewing or saving dive plans, I want a self-contained `dashboard.html` file that renders my dive profile, ceiling curve, 16-compartment tissue tensions, decompression table, and utility calculators with live interactive recalculation, plus the ability to save, name, recall, delete, export, and import custom dive profiles via both the browser UI and CLI flags.

### 1.3 Scope Definition

| Category | In-Scope Capabilities | Out-of-Scope Capabilities |
|---|---|---|
| **Decompression Model** | Deterministic Bühlmann ZH-L16C (16 compartments, default `1b` with toggle to `1`) + Erik Baker Gradient Factors (`GF Low` / `GF High`), Haldane constant-depth and Schreiner linear depth-change equations. | Bubble mechanics models (VPM-B, RGBM) and empirical recreational table lookups. |
| **Breathing Systems** | Open Circuit (`OC`), Constant-Setpoint Closed Circuit Rebreather (`CCR`), and `CCR -> OC Bailout` emergency ascent planning. | Semi-closed rebreathers (SCR/pSCR) with variable orifice-dependent loop fractions. |
| **Physiological Metrics** | NOAA 7-segment piecewise linear `CNS %` (with 90-min surface decay), Lambertsen/Baker `OTU`, `EAD`, `END` (with `o2_narcotic` boolean toggle), `MOD`, `MinOD`, `MND`, and Gas Density ($\text{g/L}$) with $5.2\text{ g/L}$ and $6.2\text{ g/L}$ thresholds. | Real-time biometric sensor telemetry ingestion or medical diagnosis of decompression sickness (DCS). |
| **Gas Logistics & Blending** | Bottom and Deco RMV/SAC volume calculation, standard cylinder library, Rule of Thirds / Rock Bottom turn pressures, Partial-Pressure Nitrox/Trimix blending, bleed-down calculation, Any-Gas Top-Up, and Real-Gas Virial $Z$-factor compressibility. | Automated hardware compressor valve actuation. |
| **Profile Persistence & UI** | CLI tabular + JSON outputs, CLI profile store management (`profiles --action list|save|delete` and `plan --save-profile-id`), and a standalone `dashboard.html` with in-browser profile saving (`localStorage`), JSON export/import, and Light/Dark/System theme switching. | External cloud database persistence or remote third-party runtime dependencies. |

---

## 2. Technical Architecture

### 2.1 System Component Diagram (Plaintext ASCII)

```text
+-----------------------------------------------------------------------------------+
|                              AGENT HARNESS / CLI USER                             |
|                     (Conversational Interface / Terminal Shell)                   |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          | 1. Natural Language Prompt or CLI Args
                                          v
+-----------------------------------------------------------------------------------+
|                                     SKILL.md                                      |
|  - Parses user intent into 1 of 8 Query Variants, 4 Utility Tools, or Profile Ops |
|  - Routes parameters to deterministic Python scripts via relative paths           |
+-----------------------------------------+-----------------------------------------+
                                          |
                     +--------------------+--------------------+
                     |                                         |
                     v                                         v
+----------------------------------------+   +--------------------------------------+
|       scripts/zhl16c_planner.py        |   |      scripts/build_dashboard.py      |
|  - Bühlmann ZH-L16C (1b / 1) Tables    |   |  - Invokes zhl16c_planner engine     |
|  - Haldane & Schreiner Integrators     |   |  - Injects precomputed profile state |
|  - Erik Baker GF Ceiling Solver        |   |  - Embeds client-side ZH-L16C solver |
|  - OC, CCR Loop, & Bailout Solvers     |   |  - Applies Light/Dark/System themes  |
|  - NOAA CNS % & Lambertsen OTU         |   +-----------------+--------------------+
|  - Best Mix, Max Depth, Rock Bottom    |                     |
|  - EAD/END/MOD, Gas Density, Blender   |                     |
|  - CLI Profile Store (list/save/del)   |                     |
+--------------------+-------------------+                     |
                     |                                         |
                     v                                         v
+----------------------------------------+   +--------------------------------------+
|     assets/ & references/              |   |            dashboard.html            |
|  - assets/dive_plan_schema.json        |   |  - Standalone HTML5 + CSS + SVG Plot |
|  - assets/skill_overview.png           |   |  - Theme Mode Switcher (L/D/Sys)     |
|  - assets/synthetic_dive_profiles.json |   |  - In-Browser Profile Save & Recall  |
|  - references/zhl16c_math_reference.md |   |  - Live Bento Grid & 4 Utility Tools |
|  - DESIGN.md & LICENSE                 |   |                                      |
+----------------------------------------+   +--------------------------------------+
```

### 2.2 Operational Sequence Flow (Plaintext ASCII)

```text
User / Harness          SKILL.md             zhl16c_planner.py        build_dashboard.py       dashboard.html
      |                     |                        |                        |                      |
      |--- Dive Request --->|                        |                        |                      |
      |                     |-- Select Subcommand -->|                        |                      |
      |                     |   (plan / profiles /   |                        |                      |
      |                     |    max-depth / blend)  |-- Validate Inputs ---->|                      |
      |                     |                        |-- Run ZH-L16C + GF --->|                      |
      |                     |                        |-- Compute CNS/OTU/Gas->|                      |
      |                     |                        |-- Save Profile (opt) ->|                      |
      |                     |<-- JSON + Table -------|                        |                      |
      |                     |                        |                        |                      |
      |                     |-- Build Dashboard ----------------------------->|                      |
      |                     |                                                 |-- Emit HTML -------->|
      |<-- Report + Link ---|                                                 |                      |
```

### 2.3 Repository Structure

All project files are organized using relative paths from the repository root:

```text
.
|-- DESIGN.md
|-- LICENSE
|-- PRD.md
|-- README.md
|-- SKILL.md
|-- dashboard.html
|-- requirements.txt
|-- assets/
|   |-- dive_plan_schema.json
|   |-- skill_overview.png
|   `-- synthetic_dive_profiles.json
|-- documents/
|   `-- prd.md
|-- references/
|   `-- zhl16c_math_reference.md
|-- scripts/
|   |-- __init__.py
|   |-- build_dashboard.py
|   `-- zhl16c_planner.py
`-- tests/
    |-- __init__.py
    |-- run_tests.py
    |-- test_smoke.py
    |-- test_system_e2e.py
    `-- test_unit_zhl16c.py
```

---

## 3. Functional Requirements and Verified Mathematical Model

### 3.1 Supported Query Variants, Utility Tools, and Profile Management Subcommands

The engine (`scripts/zhl16c_planner.py`) exposes 11 deterministic subcommands:

1. `plan`: Computes a complete Open Circuit (`OC`), Closed Circuit Rebreather (`CCR`), or `CCR + Bailout` decompression schedule for one or more depth-time segments. Supports `--auto-best-gas` (Variant 1) to automatically compute optimal bottom and decompression gases, `--profile-id` to recall a saved profile, and `--save-profile-id` / `--save-profile-title` to persist the planned configuration to `assets/synthetic_dive_profiles.json` and refresh `dashboard.html`.
2. `max-depth`: Given a cylinder specification and gas mix (`Air`, `EAN32`, `Trimix`, or custom), computes the maximum safe operating depth bounded by `MOD` ($\text{PO}_2$), `MND` ($\text{END}$), `MDD` ($5.2\text{ g/L}$ and $6.2\text{ g/L}$ gas density), and usable cylinder volume across bottom times (Variant 2).
3. `max-time`: Given a target depth, gas mix, and cylinder, solves via bisection for the exact No-Decompression Limit (`NDL`), tank-limited maximum bottom time, and `CNS 100%` time limit (Variant 3A).
4. `rock-bottom`: Calculates the minimum emergency reserve gas volume and cylinder Turn Pressure ($\text{psi}$ or $\text{bar}$) for two divers sharing gas at stressed RMV during bottom problem resolution and ascent to the first gas switch or surface (Variant 3B).
5. `what-if`: Executes comparative batch simulations across multiple Gradient Factor pairs (`GF Low / GF High`) or lost-decompression-gas scenarios (Variant 3C).
6. `repetitive`: Chains Dive 1, a surface interval $\Delta t_{\text{SI}}$ (evolving all 16 compartments via Haldane off-gassing and decaying CNS % with a 90-minute half-time), and Dive 2 (Variant 3D).
7. `bailout-sizing`: Evaluates whether a CCR diver's open-circuit bailout cylinders provide sufficient volume for a worst-case bailout at the end of the bottom segment (Variant 3E).
8. `best-mix`: Calculates optimal Nitrox ($F_{\text{O}_2}$) and optimal Trimix ($F_{\text{O}_2}, F_{\text{He}}, F_{\text{N}_2}$) for a target depth constrained by $\text{PO}_2$, $\text{END}$, and Gas Density, plus the closest standard agency mix (Tool 2).
9. `gas-tools`: Calculates `EAD`, `END` (with `o2_narcotic` toggle), `MOD`, `MinOD`, `MND`, Gas Density $\rho(D)$ in $\text{g/L}$, and `MDD` (Tools 1 and 4).
10. `blend`: Calculates Partial-Pressure Nitrox/Trimix fill cascades (including automatic residual tank bleed-down calculation), Any-Gas Top-Up resulting mixes, Continuous Nitrox stick blending, and Cylinder Fill Capacity using both Ideal Dalton and Real-Gas Virial $Z$-factor compressibility (Variant 3F and Tool 3).
11. `profiles`: Manages saved dive profiles (`--action list`, `--action save`, `--action delete`) in `assets/synthetic_dive_profiles.json` and synchronizes the dropdown selector in `dashboard.html`.

---

### 3.2 Complete Configuration Parameter Specification

| Parameter Key | Type / Allowed Values | Default Value | Validation Rule |
|---|---|---|---|
| `dive_mode` | `"OC"`, `"CCR"` | `"OC"` | Must be `"OC"` or `"CCR"`. |
| `include_bailout` | Boolean | `true` | Active when `dive_mode == "CCR"`. |
| `zhl16c_comp1_variant` | `"1b"`, `"1"` | `"1b"` | `"1b"` ($5.0\text{ min}$ $\text{N}_2$) default; `"1"` ($4.0\text{ min}$ $\text{N}_2$) toggle. |
| `gf_low` | Float ($1.0 \text{ to } 100.0$) | `30.0` | $1.0 \le \text{gf\_low} \le \text{gf\_high} \le 100.0$. |
| `gf_high` | Float ($1.0 \text{ to } 100.0$) | `85.0` | $1.0 \le \text{gf\_low} \le \text{gf\_high} \le 100.0$. |
| `o2_narcotic` | Boolean | `true` | `true`: $\text{O}_2$ and $\text{N}_2$ narcotic; `false`: $\text{N}_2$ only narcotic. |
| `depth_units` | `"feet"`, `"meters"` | `"feet"` | `"feet"` ($\text{fsw}$) or `"meters"` ($\text{msw}$). |
| `volume_units` | `"cuft"`, `"liters"` | `"cuft"` | `"cuft"` ($\text{ft}^3$) or `"liters"` ($\text{L}$). |
| `pressure_units` | `"psi"`, `"bar"` | `"psi"` | `"psi"` or `"bar"`. |
| `setpoint_units` | `"ATA"`, `"BAR"` | `"ATA"` | `"ATA"` ($1\text{ ATA} = 1.01325\text{ bar}$) or `"BAR"`. |
| `elevation_ft` | Float ($0.0 \text{ to } 15000.0$) | `0.0` | $0.0 \le \text{elevation\_ft} \le 15000.0\text{ ft}$ ($4572.0\text{ m}$). |
| `water_type` | `"salt"`, `"fresh"` | `"salt"` | `"salt"` or `"fresh"`. |
| `stop_size` | Float ($> 0$) | `10.0` $\text{ft}$ (`3.0` $\text{m}$) | Must be $> 0$ (typically $10\text{ ft}$ or $3\text{ m}$). |
| `last_oc_stop` | Float ($> 0$) | `10.0` $\text{ft}$ (`3.0` $\text{m}$) | Default $10\text{ ft}$ ($3\text{ m}$). Must be $> 0$. |
| `last_ccr_stop` | Float ($> 0$) | `10.0` $\text{ft}$ (`3.0` $\text{m}$) | Default $10\text{ ft}$ ($3\text{ m}$). Must be $> 0$. |
| `min_stop_time_sec` | Integer ($1 \text{ to } 60$) | `60` | Strictly bounded: $1\text{ s} \le \text{min\_stop\_time\_sec} \le 60\text{ s}$ ($1\text{ min}$). |
| `descent_rate` | Float ($> 0$) | `60.0` $\text{fpm}$ (`18.0` $\text{m/min}$) | Must be $> 0$. |
| `ascent_rate` | Float ($> 0$) | `30.0` $\text{fpm}$ (`9.0` $\text{m/min}$) | Bottom-to-first-stop ascent speed; must be $> 0$. |
| `deco_ascent_rate` | Float ($> 0$) | `30.0` $\text{fpm}$ (`9.0` $\text{m/min}$) | Inter-stop deco ascent speed; must be $> 0$. |
| `surface_ascent_rate` | Float ($> 0$) | `10.0` $\text{fpm}$ (`3.0` $\text{m/min}$) | Last-stop-to-surface ascent speed; must be $> 0$. |
| `bottom_rmv` | Float ($> 0$) | `0.75` $\text{cuft/min}$ (`21.2` $\text{L/min}$) | Must be $> 0$. |
| `deco_rmv` | Float ($> 0$) | `0.60` $\text{cuft/min}$ (`17.0` $\text{L/min}$) | Must be $> 0$. |
| `ccr_setpoint_bottom` | Float ($0.40 \text{ to } 1.60$) | `1.20` | Bounded within $[0.40, 1.60]$ in `ATA` or `BAR`. |
| `ccr_setpoint_deco` | Float ($0.40 \text{ to } 1.60$) | `1.30` | Bounded within $[0.40, 1.60]$ in `ATA` or `BAR`. |

---

### 3.3 Verified Mathematical Model and Equations

#### A. Physical Constants, Altitude Barometrics, and Hydrostatics
1. **Standard Sea-Level Pressure:**
   $$P_0 = 1.01325\text{ bar} = 1.00000\text{ ATA} = 14.69595\text{ psi}$$
2. **Hydrostatic Pressure Gradients:**
   - Seawater: $K_{\text{msw}} = 0.10000\text{ bar/msw}$, $K_{\text{fsw}} = \frac{1.01325}{33.0} \approx 0.030704545\text{ bar/fsw}$
   - Freshwater: $K_{\text{mfw}} = 0.0980665\text{ bar/mfw}$, $K_{\text{ffw}} = 0.02989067\text{ bar/ffw}$
3. **Alveolar Water Vapor Pressure ($37^\circ\text{C}$, $RQ = 1.0$):**
   $$P_{\text{H}_2\text{O}} = 0.0627\text{ bar}$$
4. **Dive Site Elevation Barometric Formula ($h_{\text{m}} = E_{\text{ft}} \times 0.3048$):**
   $$P_{\text{surf}}(h_{\text{m}}) = 1.01325 \times \left(1 - 2.25577 \times 10^{-5} \cdot h_{\text{m}}\right)^{5.25588}\text{ bar}$$
5. **Ambient Pressure and Initial Tissue Equilibration ($t = 0$):**
   $$P_{\text{amb}}(D) = P_{\text{surf}} + D \cdot K_{\text{depth}}, \quad D(P_{\text{tol}}) = \max\left(0, \frac{P_{\text{tol}} - P_{\text{surf}}}{K_{\text{depth}}}\right)$$
   $$\forall i \in \{1..16\}: \quad P_{\text{N}_2, i}(0) = \left(P_{\text{surf}} - P_{\text{H}_2\text{O}}\right) \times 0.79, \quad P_{\text{He}, i}(0) = 0.0\text{ bar}$$

#### B. Bühlmann ZH-L16C 16-Compartment Parameter Table (`1b` Default and `1` Toggle)

| Comp $i$ | $T_{1/2,\text{N}_2}$ ($\text{min}$) | $a_{\text{N}_2}$ ($\text{bar}$) | $b_{\text{N}_2}$ (dim.) | $T_{1/2,\text{He}}$ ($\text{min}$) | $a_{\text{He}}$ ($\text{bar}$) | $b_{\text{He}}$ (dim.) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1b (Default)** | **5.0** | **1.1696** | **0.5578** | **1.88** | **1.6189** | **0.4770** |
| *1 (Toggle)* | *4.0* | *1.2599* | *0.5050* | *1.51* | *1.7424* | *0.4245* |
| **2** | 8.0 | 1.0000 | 0.6514 | 3.02 | 1.3830 | 0.5747 |
| **3** | 12.5 | 0.8618 | 0.7222 | 4.72 | 1.1919 | 0.6527 |
| **4** | 18.5 | 0.7562 | 0.7825 | 6.99 | 1.0458 | 0.7223 |
| **5** | 27.0 | 0.6200 | 0.8126 | 10.21 | 0.9220 | 0.7582 |
| **6** | 38.3 | 0.5043 | 0.8434 | 14.48 | 0.8205 | 0.7957 |
| **7** | 54.3 | 0.4410 | 0.8693 | 20.53 | 0.7305 | 0.8279 |
| **8** | 77.0 | 0.4000 | 0.8910 | 29.11 | 0.6502 | 0.8553 |
| **9** | 109.0 | 0.3750 | 0.9092 | 41.20 | 0.5950 | 0.8757 |
| **10** | 146.0 | 0.3500 | 0.9222 | 55.19 | 0.5545 | 0.8903 |
| **11** | 187.0 | 0.3295 | 0.9319 | 70.69 | 0.5333 | 0.8997 |
| **12** | 239.0 | 0.3065 | 0.9403 | 90.34 | 0.5189 | 0.9073 |
| **13** | 305.0 | 0.2835 | 0.9477 | 115.29 | 0.5181 | 0.9122 |
| **14** | 390.0 | 0.2610 | 0.9544 | 147.42 | 0.5176 | 0.9171 |
| **15** | 498.0 | 0.2480 | 0.9602 | 188.24 | 0.5172 | 0.9217 |
| **16** | 635.0 | 0.2327 | 0.9653 | 240.03 | 0.5119 | 0.9267 |

#### C. Inspired Alveolar Partial Pressures ($P_i$) and Haldane/Schreiner Transport
- **Open Circuit (`OC`) and CCR Bailout:**
   $$P_{i, \text{N}_2} = \left(P_{\text{amb}} - P_{\text{H}_2\text{O}}\right) F_{\text{N}_2}, \quad P_{i, \text{He}} = \left(P_{\text{amb}} - P_{\text{H}_2\text{O}}\right) F_{\text{He}}$$
- **Closed Circuit Rebreather (`CCR` Constant Setpoint $SP_{\text{bar}}$):**
   $$P_{\text{O}_2, \text{loop}} = \min\left(SP_{\text{bar}}, P_{\text{amb}}\right), \quad F_{\text{inert, dil}} = F_{\text{N}_2,\text{dil}} + F_{\text{He},\text{dil}}$$
   $$P_{i, \text{N}_2}^{\text{CCR}} = \max\left(0, P_{\text{amb}} - P_{\text{H}_2\text{O}} - P_{\text{O}_2, \text{loop}}\right) \frac{F_{\text{N}_2,\text{dil}}}{F_{\text{inert, dil}}}, \quad P_{i, \text{He}}^{\text{CCR}} = \max\left(0, P_{\text{amb}} - P_{\text{H}_2\text{O}} - P_{\text{O}_2, \text{loop}}\right) \frac{F_{\text{He},\text{dil}}}{F_{\text{inert, dil}}}$$
- **Haldane Equation (Constant Depth, $R_g = 0$):**
   $$P_{i,g}(\Delta t) = P_{i0,g} + \left(P_{0,i,g} - P_{i0,g}\right) e^{-k_{i,g} \Delta t}, \quad k_{i,g} = \frac{\ln(2)}{T_{1/2,g,i}}$$
- **Schreiner Equation (Linear Depth Change, $R_g = \frac{P_{i,\text{end},g} - P_{i0,g}}{\Delta t}$):**
   $$P_{i,g}(\Delta t) = P_{i0,g} + R_g \left(\Delta t - \frac{1}{k_{i,g}}\right) - \left(P_{i0,g} - P_{0,i,g} - \frac{R_g}{k_{i,g}}\right) e^{-k_{i,g} \Delta t}$$

#### D. Weighted Trimix M-Values and Erik Baker Gradient Factor Equations
$$P_{\text{total}, i} = P_{\text{N}_2, i} + P_{\text{He}, i}, \quad a_i = \frac{a_{\text{N}_2, i} P_{\text{N}_2, i} + a_{\text{He}, i} P_{\text{He}, i}}{P_{\text{total}, i}}, \quad b_i = \frac{b_{\text{N}_2, i} P_{\text{N}_2, i} + b_{\text{He}, i} P_{\text{He}, i}}{P_{\text{total}, i}}$$
$$P_{\text{amb, tol}, i}(GF) = \frac{\left(P_{\text{total}, i} - a_i \cdot GF\right) \cdot b_i}{GF + b_i \cdot \left(1 - GF\right)}, \quad P_{\text{ceiling}}(GF) = \max_{i \in \{1..16\}} P_{\text{amb, tol}, i}(GF)$$
$$GF\left(D_{\text{next}}\right) = GF_{\text{low}} + \left(GF_{\text{high}} - GF_{\text{low}}\right) \cdot \frac{D_{\text{first}} - D_{\text{next}}}{D_{\text{first}}}$$

#### E. Oxygen Toxicity (`CNS %` and `OTU`)
- **NOAA / Erik Baker 7-Segment Piecewise Linear `CNS %` ($T_{\text{lim}} = m_k P_{\text{O}_2,\text{ATA}} + b_k$):**
  - $(0.50, 0.60]$: $m_1 = -1800, b_1 = 1800$
  - $(0.60, 0.70]$: $m_2 = -1500, b_2 = 1620$
  - $(0.70, 0.80]$: $m_3 = -1200, b_3 = 1410$
  - $(0.80, 0.90]$: $m_4 = -900, b_4 = 1170$
  - $(0.90, 1.10]$: $m_5 = -600, b_5 = 900$
  - $(1.10, 1.50]$: $m_6 = -300, b_6 = 570$
  - $(1.50, 1.60]$: $m_7 = -750, b_7 = 1245$
  - Constant depth: $\Delta \text{CNS}\% = \frac{\Delta t}{T_{\text{lim}}(P_{\text{O}_2})} \times 100\%$.
  - Linear depth change within segment $k$: $\Delta \text{CNS}\% = \frac{100\%}{m_k R_{\text{O}_2}} \ln\left(\frac{T_{\text{lim}}(P_{\text{O}_2,\text{end}})}{T_{\text{lim}}(P_{\text{O}_2,\text{start}})}\right)$.
  - Surface interval decay: $\text{CNS}\%(t + \Delta t_{\text{SI}}) = \text{CNS}\%(t) \cdot e^{-\frac{\ln(2)}{90.0} \Delta t_{\text{SI}}}$.
- **Lambertsen / Baker `OTU` ($P_{\text{O}_2,\text{ATA}} > 0.50$):**
  - Constant depth: $\Delta \text{OTU} = \Delta t \cdot \left(\frac{P_{\text{O}_2,\text{ATA}} - 0.5}{0.5}\right)^{5/6}$.
  - Linear depth change: $\Delta \text{OTU} = \frac{3 \Delta t}{11 (P_b - P_a)} \left[\left(\frac{P_b - 0.5}{0.5}\right)^{11/6} - \left(\frac{P_a - 0.5}{0.5}\right)^{11/6}\right]$.

#### F. Diver Utility Suite Equations (`EAD/END/MOD`, `Best Mix`, `Gas Blender`, `Gas Density`)
1. **MOD, MinOD, EAD, END, and MND:**
   $$\text{MOD} = \max\left(0, \frac{(P_{\text{O}_2,\text{max}} / F_{\text{O}_2}) - P_{\text{surf}}}{K_{\text{depth}}}\right), \quad \text{MinOD} = \max\left(0, \frac{(P_{\text{O}_2,\text{min}} / F_{\text{O}_2}) - P_{\text{surf}}}{K_{\text{depth}}}\right)$$
   $$\text{EAD}(D) = \max\left(0, \left(D + D_{\text{surf}}\right) \frac{F_{\text{N}_2}}{0.79} - D_{\text{surf}}\right)$$
   $$\text{END}(D) = \begin{cases} \max\left(0, \left(D + D_{\text{surf}}\right) (1 - F_{\text{He}}) - D_{\text{surf}}\right), & \texttt{o2\_narcotic} = \text{true} \\ \max\left(0, \left(D + D_{\text{surf}}\right) \frac{F_{\text{N}_2}}{0.79} - D_{\text{surf}}\right), & \texttt{o2\_narcotic} = \text{false} \end{cases}$$
2. **Best Mix for Depth ($D$):**
   $$F_{\text{O}_2,\text{best}} = \min\left(1.0, \frac{\lfloor (P_{\text{O}_2,\text{target}} / P_{\text{amb}}(D)) \times 100 \rfloor}{100}\right)$$
   $$F_{\text{He, best}} = \min\left(1.0 - F_{\text{O}_2,\text{best}}, \frac{\lceil \max(F_{\text{He, narc}}, F_{\text{He, dens}}) \times 100 \rceil}{100}\right)$$
3. **Gas Blender (Partial-Pressure, Bleed-Down, Top-Up, and Real-Gas $Z$-Factor):**
   - Bleed-down pressure: $P_{\text{init}} = \min(P_{\text{start}}, P_{\text{max, He}}, P_{\text{max, N}_2}, P_{\text{max, O}_2})$.
   - Helium step: $\Delta P_{\text{He}} = P_{\text{target}} F_{\text{He, target}} - P_{\text{init}} F_{\text{He, start}}$.
   - Top-up step: $\Delta P_{\text{top}} = \frac{P_{\text{target}} F_{\text{N}_2,\text{target}} - P_{\text{init}} F_{\text{N}_2,\text{start}}}{1 - F_{\text{O}_2,\text{top}}}$.
   - Oxygen step: $\Delta P_{\text{O}_2} = P_{\text{target}} - (P_{\text{init}} + \Delta P_{\text{He}}) - \Delta P_{\text{top}}$.
   - Real-gas virial compressibility ($Z_g(P) = 1 + B_g P + C_g P^2$): $V_{\text{real}} = \frac{V_{\text{ideal}}}{Z_{\text{mix}}(P_{\text{bar}})}$.
4. **Gas Density ($\rho$ in $\text{g/L}$) and Maximum Density Depth ($\text{MDD}$):**
   $$\rho_{\text{mix}, 0} = 1.4290 F_{\text{O}_2} + 1.2506 F_{\text{N}_2} + 0.1786 F_{\text{He}}\text{ g/L}, \quad \rho(D) = \rho_{\text{mix}, 0} \cdot \left(\frac{P_{\text{amb}}(D)}{P_0}\right)$$
   $$\text{MDD}\left(\rho_{\text{limit}}\right) = \max\left(0, \frac{(\rho_{\text{limit}} / \rho_{\text{mix}, 0}) P_0 - P_{\text{surf}}}{K_{\text{depth}}}\right)$$

#### G. Interactive HTML Dashboard & Two-Tab Primary Workspace Architecture (`dashboard.html`)
- **Design Specification (`DESIGN.md`)**:
  - **Typography**: `DM Sans` (UI controls and labels), `Instrument Serif` (display titles), and `IBM Plex Mono` with `tabular-nums` (telemetry tables, matrices, and numerical inputs).
  - **Theme Modes (`light`, `dark`, `system`)**: Three-button segmented theme switcher (`#theme-btn-light`, `#theme-btn-dark`, `#theme-btn-system`) persisted in `localStorage` with real-time OS `prefers-color-scheme: dark` tracking.
  - **Surface Tokens**: Light mode (`#FAFAF9` background, `#FFFFFF` cards, `#E7E5E4` borders, `#1C1917` primary text, `#787774` secondary text) and Dark mode (`#0D0E11` background, `#16171D` cards, `#292A30` borders, `#ECE8E2` primary text, `#9A9895` secondary text).
  - **Semantic Visualization Palette**: Vibrant Teal (`#0D9488`), Energetic Amber (`#D97706`), Vivid Indigo (`#4F46E5`), Functional Emerald (`#059669`), and Deep Rose (`#E11D48`).
- **Primary Workspace Navigation Bar (`.workspace-tabs`)**:
  - **Main Tab 1 (`1. Dive Planner` / `#main-view-planner`, active by default)**: Displays the 4-Card KPI Telemetry Summary Strip (`Total Runtime (TTS)`, `Max Depth & Leading Tissue`, `Oxygen Toxicity (CNS / OTU)`, `Peak Gas Density & END`) and the 2-column Bento grid:
    - **Left Configuration Column (`380px`)**: Card 1 (`Bottom Profile & Best-Gas Solver` with `New Profile`, `Save Profile`, target depth/time, and `Auto Best Gas + Plan`), Card 2 (`ZH-L16C & Gradient Factors`), Card 3 (`Stops, Kinematics & RMV / Altitude`), and Card 4 (`Gas Mixes & Bailout Inventory`).
    - **Right Telemetry Column (`1fr`)**: Card R1 (`Interactive Depth, Decompression Ceiling & Gas Switch Profile` dual Y-axis SVG chart with left depth axis, right `PO2 (ATA)` axis, and interactive hover crosshair tooltip `#chart-hover-tooltip`) and Card R2 (`Ascent & Decompression Table`, `Cylinder Gas Logistics`, and `16-Compartment Tissue Matrix` sub-tabs).
  - **Main Tab 2 (`2. Diver Utility Tools` / `#main-view-tools`)**: Displays the full-width `Diver Utility Tools & Query Variants Suite` card on a single screen with four sub-tabs:
    1. `Tool 1 & Var 2: EAD / END / MOD & Tank Max-Depth` (`#util-tab-mod`)
    2. `Tool 2: Best Mix for Depth` (`#util-tab-bestmix`)
    3. `Tool 3: Nitrox / Trimix Blender & Fill Capacity` (`#util-tab-blender`)
    4. `Tool 4 & Var 3: Gas Density, Rock Bottom & What-If` (`#util-tab-density`)

---

## 4. Non-Functional Requirements

1. **Performance and Latency:**
   - Single dive plan or utility CLI calculation completes in under $100\text{ ms}$ on standard hardware.
   - Multi-scenario `what-if` or `max-depth` envelope sweeps complete in under $500\text{ ms}$.
   - Interactive UI recalculations inside `dashboard.html` complete in under $15\text{ ms}$ per input change without resetting scroll position or active tab state.
2. **Data Privacy and Offline Execution:**
   - All reference and benchmark profiles (`assets/synthetic_dive_profiles.json`) contain only technical dive parameters and gas configurations.
   - Neither `scripts/zhl16c_planner.py`, `scripts/build_dashboard.py`, nor `dashboard.html` performs external network requests or remote telemetry transmissions.
3. **Portability and Relative Path Architecture:**
   - All file lookups in `scripts/`, `tests/`, and `SKILL.md` resolve relative to the project root directory using `pathlib.Path(__file__).resolve().parent.parent`.
4. **Algorithmic Completeness:**
   - Every function in `scripts/zhl16c_planner.py` and `dashboard.html` executes the full mathematical specification across all 16 compartments and gas transport equations.

---

## 5. Error Handling and Edge Cases Matrix

| Error Code | Trigger Condition / Invalid Input | Validation Rule | Deterministic System Behavior | Exit Code |
|---|---|---|---|---|
| `ERR_GAS_FRACTIONS` | $F_{\text{O}_2} \le 0$, $F_{\text{He}} < 0$, or $F_{\text{O}_2} + F_{\text{He}} > 1.0001$ | $0.01 \le F_{\text{O}_2} \le 1.0$, $0.0 \le F_{\text{He}} < 1.0$, $F_{\text{O}_2} + F_{\text{He}} \le 1.0$ | Raises `DivePlannerValidationError` detailing exact gas composition violation (`O2% + He% cannot exceed 100%`). | `2` |
| `ERR_GF_RANGE` | `gf_low < 1`, `gf_high > 100`, or `gf_low > gf_high` | $1 \le \text{gf\_low} \le \text{gf\_high} \le 100$ | Raises `DivePlannerValidationError` explaining that `GF Low` must be between 1% and `GF High`, and `GF High` $\le 100\%$. | `2` |
| `ERR_STOP_INTERVAL` | `min_stop_time_sec < 1` or `min_stop_time_sec > 60` | $1\text{ s} \le \text{min\_stop\_time\_sec} \le 60\text{ s}$ | Raises `DivePlannerValidationError` enforcing the $1\text{ second}$ minimum to $1\text{ minute}$ ($60\text{ s}$) maximum stop interval bound. | `2` |
| `ERR_KINEMATIC_RATE` | `descent_rate <= 0`, `ascent_rate <= 0`, `deco_ascent_rate <= 0`, or `surface_ascent_rate <= 0` | All kinematic rates $> 0$ | Raises `DivePlannerValidationError` specifying which ascent/descent rate is non-positive. | `2` |
| `ERR_DEPTH_TIME` | Segment `depth < 0`, `depth > 1000 ft`, or `time <= 0` | $0 \le D \le 1000\text{ ft}$ ($305\text{ m}$), $t > 0$ | Raises `DivePlannerValidationError` identifying the invalid segment index and value. | `2` |
| `ERR_ELEVATION` | `elevation_ft < 0` or `elevation_ft > 15000` | $0 \le E_{\text{ft}} \le 15000\text{ ft}$ | Raises `DivePlannerValidationError` rejecting negative or extreme altitudes. | `2` |
| `ERR_HYPOXIC_SURFACE` | Breathing a hypoxic mix ($P_{\text{O}_2} < 0.16\text{ ATA}$) at shallow depth without an enabled travel gas | $P_{\text{O}_2} \ge 0.16\text{ ATA}$ | Emits explicit `HYPOXIC_WARNING` in plan telemetry and automatically inserts a breathable travel gas if `--auto-best-gas` is enabled. | `0` (with alert) / `2` (if strict) |
| `ERR_BLEND_IMPOSSIBLE` | Target mix requires negative $\Delta P_{\text{O}_2}$ or negative $\Delta P_{\text{top}}$ (for example, target $\text{O}_2\%$ is lower than top-up gas $\text{O}_2\%$ after adding Helium) | $\Delta P_{\text{He}} \ge 0, \Delta P_{\text{O}_2} \ge 0, \Delta P_{\text{top}} \ge 0$ | Returns structured blending feasibility report explaining why Air top-up cannot produce a hyper-hypoxic oxygen ratio without an inert Argon/Nitrogen bank. | `2` |
| `ERR_MALFORMED_JSON` | Corrupted or structurally invalid JSON input file passed via `--input-file` | Valid JSON conforming to `assets/dive_plan_schema.json` | Catches `json.JSONDecodeError` / `KeyError`, logs structured error message, and exits cleanly. | `3` |
