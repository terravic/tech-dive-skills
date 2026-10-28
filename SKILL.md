---
name: tech-dive-planner
description: Plans Open Circuit (OC), Closed Circuit Rebreather (CCR), and OC Bailout technical decompression dives using the Bühlmann ZH-L16C (1b/1) algorithm with Erik Baker Gradient Factors, NOAA CNS %, Lambertsen OTU, and four integrated diver gas utility calculators (EAD/END/MOD, Best Mix, Nitrox/Trimix/Top-Up/Fill Capacity Gas Blender, and Gas Density).
---

# Technical Dive Planner Skill (`tech-dive-planner`)

## 1. Purpose and Scope

This skill provides deterministic decompression scheduling, oxygen toxicity tracking, gas logistics calculation, and breathing gas utility tools for Open Circuit (`OC`) and Closed Circuit Rebreather (`CCR`) scuba diving.

All calculations are executed through the deterministic Python CLI engine at `scripts/zhl16c_planner.py`.

### Core Capabilities
1. **Bühlmann ZH-L16C + Gradient Factors (`GF Low` / `GF High`)**:
   - Supports Compartment `1b` (`5.0 min` N2 / `1.88 min` He, default) and Compartment `1` (`4.0 min` N2 / `1.51 min` He) via `--comp1 1b|1`.
   - Exact Haldane (isobaric) and Schreiner (linear depth change) differential gas transport equations across all 16 compartments.
   - Configurable stop increments (`--stop-size`), last stop depth (`--last-oc-stop`, `--last-ccr-stop`, default `10 ft`), minimum stop time quantum (`--min-stop-sec`, `1` to `60` seconds), kinematic rates (`--descent-rate`, `--ascent-rate`, `--deco-ascent-rate`, `--surface-ascent-rate`), and altitude barometric pressure correction (`--elevation-ft`).
2. **Oxygen Toxicity & Physiological Limits**:
   - Tracks NOAA 7-segment piecewise linear `CNS %` (including 90-minute half-time surface interval decay) and Lambertsen/Baker pulmonary `OTU`.
   - Configurable oxygen narcosis (`--o2-narcotic true|false`) and breathing gas density ($\text{g/L}$) with `5.2 g/L` and `6.2 g/L` UHMS/DAN thresholds.
3. **Eight Diver Query Variants & Four Diver Utility Tools**:
   - **Variant 1**: Given depth and time at depth, automatically compute the optimal bottom and decompression gases and full decompression schedule (`plan --auto-best-gas`).
   - **Variant 2**: Given cylinder size and gas mix, calculate how deep the diver can safely go across `MOD`, `MND`, `MDD`, and usable tank volume (`max-depth`).
   - **Variant 3A**: Solve for No-Decompression Limit (`NDL`), Tank-Limited Max Bottom Time, and CNS-Limited Bottom Time (`max-time`).
   - **Variant 3B**: Calculate Minimum Reserve Gas ("Rock Bottom") and Turn Pressure for two divers sharing gas (`rock-bottom`).
   - **Variant 3C**: Compare `GF Low / GF High` pairs and Lost Decompression Gas emergency scenarios (`what-if`).
   - **Variant 3D**: Chain Dive 1, Surface Interval off-gassing, and Dive 2 (`repetitive`).
   - **Variant 3E**: Calculate `CCR -> OC` emergency bailout decompression schedule and stage cylinder sizing (`bailout-sizing`).
   - **Tool 1 & Tool 4**: Calculate `EAD`, `END`, `MOD`, `MinOD`, `MND`, Gas Density ($\text{g/L}$), and `MDD` (`gas-tools`).
   - **Tool 2**: Calculate Best Nitrox, Best Trimix, closest standard agency blend (`Tx 18/45`, `Tx 15/55`, `EAN32`), and recommended deco gases (`best-mix`).
   - **Tool 3**: Calculate Nitrox/Trimix partial-pressure blending, bleed-down, top-up resulting mix, real-gas Virial $Z$-factor corrections, and cylinder fill capacity (`blend`).

---

## 2. Operational Workflow

When a user submits a dive planning or gas calculation request:

1. **Classify the Request**:
   Identify which of the CLI subcommands in `scripts/zhl16c_planner.py` matches the user's intent (`plan`, `max-depth`, `max-time`, `rock-bottom`, `what-if`, `repetitive`, `bailout-sizing`, `best-mix`, `gas-tools`, or `blend`).
2. **Normalize Units and Defaults**:
   Apply standard defaults when parameters are omitted by the user:
   - `GF Low / GF High`: `30 / 85`
   - `Compartment 1 Variant`: `1b`
   - `O2 Narcotic`: `true`
   - `Stop Size / Last Stop`: `10 ft` (`3 m` in metric mode)
   - `Minimum Stop Interval`: `60 s` (`1 min`)
   - `Rates`: Descent `60 fpm` (`18 m/min`), Ascent `30 fpm` (`9 m/min`), Deco Ascent `30 fpm` (`9 m/min`), Surface Ascent `10 fpm` (`3 m/min`)
   - `RMV / SAC`: Bottom `0.75 cuft/min` (`20 L/min`), Deco `0.60 cuft/min` (`16 L/min`)
3. **Execute the Deterministic Engine**:
   Run `python3 scripts/zhl16c_planner.py <subcommand> [options]` from the project root directory.
4. **Regenerate the Interactive Dashboard (When Requested)**:
   If the user asks to view or update the interactive HTML dashboard (`dashboard.html`), run:
   ```bash
   python3 scripts/build_dashboard.py
   ```
5. **Present Verified Results**:
   Report the exact numerical outputs from `scripts/zhl16c_planner.py` in structured markdown tables, and highlight any physiological or gas logistics warnings (`HYPOXIC_WARNING`, `HYPEROXIC_WARNING`, `GAS_DENSITY_ALERT`, `GAS_RESERVE_WARNING`).

---

## 3. CLI Subcommand Reference

All commands are executed relative to the repository root directory:

### 3.1 Variant 1: Decompression Dive Plan & Auto-Best-Gas (`plan`)
```bash
# Plan a 200 ft / 25 min dive and automatically select the best bottom and deco gases
python3 scripts/zhl16c_planner.py plan --depth 200 --time 25 --auto-best-gas

# Plan a custom OC Trimix 18/45 dive with EAN50 and O2 100% deco gases
python3 scripts/zhl16c_planner.py plan \
  --mode OC --depth 180 --time 25 --f-o2 0.18 --f-he 0.45 \
  --deco-gases "EAN50:0.50:0.0:70,O2 100%:1.00:0.0:20" \
  --gf-low 30 --gf-high 85 --comp1 1b

# Plan a CCR dive with automatic OC bailout schedule from a JSON profile
python3 scripts/zhl16c_planner.py --json plan \
  --profile-id syn-ccr-bailout-240ft

# Plan a dive and save it directly into the UI Profile dropdown selector
python3 scripts/zhl16c_planner.py plan \
  --depth 165 --time 30 --f-o2 0.21 --f-he 0.35 --gf-low 30 --gf-high 85 \
  --save-profile-id custom-wreck-165ft \
  --save-profile-title "OC Tx 21/35 - 165 ft for 30 min (GF 30/85)"
```

### 3.1b Profile Management Subcommand (`profiles`)
```bash
# List all saved profiles available in the UI dropdown selector
python3 scripts/zhl16c_planner.py profiles --action list

# Save or update a named dive profile and automatically rebuild dashboard.html
python3 scripts/zhl16c_planner.py profiles \
  --action save --profile-id custom-trimix-200ft \
  --title "OC Best Trimix - 200 ft for 25 min" \
  --depth 200 --time 25 --auto-best-gas

# Delete a saved profile by ID and rebuild dashboard.html
python3 scripts/zhl16c_planner.py profiles \
  --action delete --profile-id custom-trimix-200ft
```

### 3.2 Variant 2: Tank & Gas Mix -> Maximum Safe Operating Depth (`max-depth`)
```bash
python3 scripts/zhl16c_planner.py max-depth \
  --cylinder AL80 --fill-psi 3000 --f-o2 0.32 --f-he 0.0 \
  --max-po2 1.40 --max-end 100 --reserve-rule thirds
```

### 3.3 Variant 3A: NDL & Tank-Limited Maximum Bottom Time (`max-time`)
```bash
python3 scripts/zhl16c_planner.py max-time \
  --depth 100 --f-o2 0.32 --f-he 0.0 --cylinder AL80 --fill-psi 3000
```

### 3.4 Variant 3B: Minimum Reserve Gas / Rock Bottom (`rock-bottom`)
```bash
python3 scripts/zhl16c_planner.py rock-bottom \
  --depth 180 --time 25 --cylinder 2xLP85 --fill-psi 2640 \
  --switch-depth 70 --stressed-rmv 1.00
```

### 3.5 Variant 3C: What-If GF & Lost Decompression Gas Comparison (`what-if`)
```bash
python3 scripts/zhl16c_planner.py what-if \
  --depth 180 --time 25 --f-o2 0.18 --f-he 0.45
```

### 3.6 Variant 3D: Repetitive Dive & Surface Interval Off-Gassing (`repetitive`)
```bash
python3 scripts/zhl16c_planner.py repetitive \
  --d1-depth 130 --d1-time 25 --surface-interval 90 \
  --d2-depth 100 --d2-time 25 --f-o2 0.32
```

### 3.7 Variant 3E: CCR Loop Failure Bailout Stage Sizing (`bailout-sizing`)
```bash
python3 scripts/zhl16c_planner.py bailout-sizing \
  --depth 240 --time 30 --f-o2 0.13 --f-he 0.54 \
  --setpoint-bottom 1.20 --setpoint-deco 1.30 --bailout-rmv 0.90
```

### 3.8 Tool 1 & Tool 4: EAD, END, MOD, MinOD, MND & Gas Density (`gas-tools`)
```bash
python3 scripts/zhl16c_planner.py gas-tools \
  --depth 200 --f-o2 0.18 --f-he 0.45 --o2-narcotic true \
  --max-po2 1.40 --max-end 100 --elevation-ft 0 --depth-units feet
```

### 3.9 Tool 2: Best Mix for Depth (`best-mix`)
```bash
python3 scripts/zhl16c_planner.py best-mix \
  --depth 200 --max-po2 1.40 --max-end 100 --max-density 5.20 \
  --o2-narcotic true --depth-units feet
```

### 3.10 Tool 3: Nitrox/Trimix Gas Blender, Top-Up & Fill Capacity (`blend`)
```bash
# Mode A: Partial-pressure cascade blending (He + O2 + Air top-up with bleed-down check)
python3 scripts/zhl16c_planner.py blend \
  --mode partial_pressure --cylinder 2xLP85 \
  --start-pressure 500 --start-f-o2 0.18 --start-f-he 0.45 \
  --target-pressure 2640 --target-f-o2 0.21 --target-f-he 0.35

# Mode B: Top-up resulting mix when adding a known gas over residual cylinder pressure
python3 scripts/zhl16c_planner.py blend \
  --mode topup_result --cylinder AL80 \
  --start-pressure 1000 --start-f-o2 0.32 --start-f-he 0.0 \
  --target-pressure 3000 --topup-f-o2 0.21 --topup-f-he 0.0
```

---

## 4. Reference Materials and Assets

- `documents/prd.md` and `PRD.md`: Full Product Requirement Document detailing scope, architecture, mathematical equations, and error handling matrix.
- `references/zhl16c_math_reference.md`: Bühlmann ZH-L16C (`1b` and `1`) coefficient tables, Haldane/Schreiner derivations, Erik Baker Gradient Factors, NOAA CNS table, and Lambertsen OTU equations.
- `assets/dive_plan_schema.json`: JSON Schema validating input dive configurations and output schedules.
- `assets/skill_overview.png`: Architectural and dashboard overview diagram illustrating the skill execution pipeline, data inputs/outputs, and interactive UI preview.
- `assets/synthetic_dive_profiles.json`: Reference technical dive benchmark profiles and cylinder configurations.
- `DESIGN.md`: Architectural UI design system rules enforced by `scripts/build_dashboard.py` when generating `dashboard.html`.
- `LICENSE`: Apache License, Version 2.0 governing the project.
