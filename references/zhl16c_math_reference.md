# Bühlmann ZH-L16C, Gradient Factors, and Diver Utility Mathematical Reference

This reference document specifies the exact constants, tables, and equations implemented by `scripts/zhl16c_planner.py` and the embedded solver inside `dashboard.html`.

---

## 1. Bühlmann ZH-L16C 16-Compartment Coefficient Table

Coefficients $a$ are expressed in absolute pressure ($\text{bar}$), $b$ are dimensionless slope multipliers, and half-times $T_{1/2}$ are in minutes ($\text{min}$).

- **Compartment `1b` (Default):** $T_{1/2,\text{N}_2} = 5.0\text{ min}$, $a_{\text{N}_2} = 1.1696\text{ bar}$, $b_{\text{N}_2} = 0.5578$, $T_{1/2,\text{He}} = 1.88\text{ min}$, $a_{\text{He}} = 1.6189\text{ bar}$, $b_{\text{He}} = 0.4770$.
- **Compartment `1` (Toggle):** $T_{1/2,\text{N}_2} = 4.0\text{ min}$, $a_{\text{N}_2} = 1.2599\text{ bar}$, $b_{\text{N}_2} = 0.5050$, $T_{1/2,\text{He}} = 1.51\text{ min}$, $a_{\text{He}} = 1.7424\text{ bar}$, $b_{\text{He}} = 0.4245$.

| Compartment | $T_{1/2,\text{N}_2}$ ($\text{min}$) | $a_{\text{N}_2}$ ($\text{bar}$) | $b_{\text{N}_2}$ | $T_{1/2,\text{He}}$ ($\text{min}$) | $a_{\text{He}}$ ($\text{bar}$) | $b_{\text{He}}$ |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `1b` | 5.0 | 1.1696 | 0.5578 | 1.88 | 1.6189 | 0.4770 |
| `1` | 4.0 | 1.2599 | 0.5050 | 1.51 | 1.7424 | 0.4245 |
| `2` | 8.0 | 1.0000 | 0.6514 | 3.02 | 1.3830 | 0.5747 |
| `3` | 12.5 | 0.8618 | 0.7222 | 4.72 | 1.1919 | 0.6527 |
| `4` | 18.5 | 0.7562 | 0.7825 | 6.99 | 1.0458 | 0.7223 |
| `5` | 27.0 | 0.6200 | 0.8126 | 10.21 | 0.9220 | 0.7582 |
| `6` | 38.3 | 0.5043 | 0.8434 | 14.48 | 0.8205 | 0.7957 |
| `7` | 54.3 | 0.4410 | 0.8693 | 20.53 | 0.7305 | 0.8279 |
| `8` | 77.0 | 0.4000 | 0.8910 | 29.11 | 0.6502 | 0.8553 |
| `9` | 109.0 | 0.3750 | 0.9092 | 41.20 | 0.5950 | 0.8757 |
| `10` | 146.0 | 0.3500 | 0.9222 | 55.19 | 0.5545 | 0.8903 |
| `11` | 187.0 | 0.3295 | 0.9319 | 70.69 | 0.5333 | 0.8997 |
| `12` | 239.0 | 0.3065 | 0.9403 | 90.34 | 0.5189 | 0.9073 |
| `13` | 305.0 | 0.2835 | 0.9477 | 115.29 | 0.5181 | 0.9122 |
| `14` | 390.0 | 0.2610 | 0.9544 | 147.42 | 0.5176 | 0.9171 |
| `15` | 498.0 | 0.2480 | 0.9602 | 188.24 | 0.5172 | 0.9217 |
| `16` | 635.0 | 0.2327 | 0.9653 | 240.03 | 0.5119 | 0.9267 |

---

## 2. Haldane, Schreiner, and Erik Baker Gradient Factor Equations

### 2.1 Rate Constant
$$k_{i,g} = \frac{\ln(2)}{T_{1/2,g,i}}$$

### 2.2 Haldane Equation (Isobaric / Constant Depth, $R_g = 0$)
$$P_{i,g}(\Delta t) = P_{i0,g} + \left(P_{0,i,g} - P_{i0,g}\right) \cdot e^{-k_{i,g}\Delta t}$$

### 2.3 Schreiner Equation (Linear Ascent or Descent, $R_g = \frac{d P_{i,g}}{dt} \ne 0$)
$$P_{i,g}(\Delta t) = P_{i0,g} + R_g \cdot \left(\Delta t - \frac{1}{k_{i,g}}\right) - \left(P_{i0,g} - P_{0,i,g} - \frac{R_g}{k_{i,g}}\right) \cdot e^{-k_{i,g}\Delta t}$$

### 2.4 Trimix Weighted Coefficients and Gradient Factor Ceiling
$$P_{\text{total}, i} = P_{\text{N}_2, i} + P_{\text{He}, i}$$
$$a_i = \frac{a_{\text{N}_2, i} P_{\text{N}_2, i} + a_{\text{He}, i} P_{\text{He}, i}}{P_{\text{total}, i}}, \quad b_i = \frac{b_{\text{N}_2, i} P_{\text{N}_2, i} + b_{\text{He}, i} P_{\text{He}, i}}{P_{\text{total}, i}}$$
$$P_{\text{amb, tol}, i}(GF) = \frac{\left(P_{\text{total}, i} - a_i \cdot GF\right) \cdot b_i}{GF + b_i \cdot \left(1 - GF\right)}$$

---

## 3. NOAA CNS % Slope-Intercept Table and Lambertsen OTU Equations

| Range Index | $P_{\text{O}_2}$ Interval ($\text{ATA}$) | Endpoint $T_{\text{lim}}$ ($\text{min}$) | Slope $m_k$ ($\text{min/ATA}$) | Intercept $b_k$ ($\text{min}$) |
| :---: | :---: | :---: | :---: | :---: |
| 1 | $(0.50, 0.60]$ | $900 \to 720$ | $-1800.0$ | $1800.0$ |
| 2 | $(0.60, 0.70]$ | $720 \to 570$ | $-1500.0$ | $1620.0$ |
| 3 | $(0.70, 0.80]$ | $570 \to 450$ | $-1200.0$ | $1410.0$ |
| 4 | $(0.80, 0.90]$ | $450 \to 360$ | $-900.0$ | $1170.0$ |
| 5 | $(0.90, 1.10]$ | $360 \to 240$ | $-600.0$ | $900.0$ |
| 6 | $(1.10, 1.50]$ | $240 \to 120$ | $-300.0$ | $570.0$ |
| 7 | $(1.50, 1.60]$ | $120 \to 45$ | $-750.0$ | $1245.0$ |

---

## 4. Standard Cylinder Specification Reference

| Preset ID | Description | Rated Capacity ($\text{cuft}$) | Rated Pressure ($\text{psi}$) | Water Volume ($\text{L}$) | Working Pressure ($\text{bar}$) |
|---|---|---:|---:|---:|---:|
| `AL40` | Aluminum 40 Stage | 40.0 | 3000 | 5.7 | 207 |
| `AL80` | Aluminum 80 Stage / Single | 77.4 | 3000 | 11.1 | 207 |
| `LP85` | Low Pressure Steel 85 | 85.0 | 2640 | 13.4 | 182 |
| `LP108` | Low Pressure Steel 108 | 108.0 | 2640 | 17.0 | 182 |
| `HP100` | High Pressure Steel 100 | 100.0 | 3442 | 12.9 | 237 |
| `HP120` | High Pressure Steel 120 | 120.0 | 3442 | 15.3 | 237 |
| `2xAL80` | Doubles Aluminum 80 | 154.8 | 3000 | 22.2 | 207 |
| `2xLP85` | Doubles Steel LP85 | 170.0 | 2640 | 26.8 | 182 |
| `2xLP108` | Doubles Steel LP108 | 216.0 | 2640 | 34.0 | 182 |
| `2xHP100` | Doubles Steel HP100 | 200.0 | 3442 | 25.8 | 237 |
| `3L_200` | 3L CCR Cylinder | 21.2 | 2900 | 3.0 | 200 |
| `7L_232` | 7L Stage Cylinder | 57.3 | 3365 | 7.0 | 232 |
| `12L_232` | Single 12L Euro Cylinder | 98.3 | 3365 | 12.0 | 232 |
| `D12_232` | Twin 2x12L Manifolded Doubles | 196.6 | 3365 | 24.0 | 232 |
