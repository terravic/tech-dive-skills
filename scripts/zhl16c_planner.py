#!/usr/bin/env python3
"""Deterministic Bühlmann ZH-L16C + Gradient Factors Dive Planner and Diver Utility Engine.

Implements:
- Bühlmann ZH-L16C 16-compartment model (Compartment 1b default, Compartment 1 toggle)
- Erik C. Baker Gradient Factors (GF Low / GF High) ceiling and linear ramp solver
- Open Circuit (OC), Constant-Setpoint Rebreather (CCR), and CCR -> OC Bailout planning
- Haldane (isobaric) and Schreiner (linear depth change) inert gas transport equations
- NOAA 7-segment piecewise linear CNS % oxygen toxicity and 90-minute surface decay
- Lambertsen / Baker pulmonary oxygen toxicity (OTU / UPTD) equations
- All 8 Diver Query Variants and 4 Diver Utility Tools (EAD/END/MOD, Best Mix,
  Nitrox/Trimix/Top-Up/Fill Capacity Gas Blender, and Gas Density analyzer)
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
import logging
import math
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

LOGGER = logging.getLogger("zhl16c_planner")

# ---------------------------------------------------------------------------
# Physical Constants
# ---------------------------------------------------------------------------
P0_BAR: float = 1.01325
P0_PSI: float = 14.69595
P_H2O_BAR: float = 0.0627  # Alveolar water vapor pressure at 37 C (47 mmHg)
LN2: float = math.log(2.0)
AIR_F_O2: float = 0.21
AIR_F_N2: float = 0.79

# Hydrostatic pressure gradients (bar per unit depth)
K_MSW_BAR: float = 0.10000
K_FSW_BAR: float = P0_BAR / 33.0  # 33.0 fsw = 1.0 ATA = 1.01325 bar
K_MFW_BAR: float = 0.0980665
K_FFW_BAR: float = 0.0980665 * 0.3048

# Surface dry gas densities at 0 C, 1 ATA (g/L)
RHO_O2_STP: float = 1.4290
RHO_N2_STP: float = 1.2506
RHO_HE_STP: float = 0.1786

# Virial coefficients at 293.15 K (20 C) for Z(P_bar) = 1 + B*P + C*P^2
VIRIAL_COEFFS: Dict[str, Tuple[float, float]] = {
    "O2": (-6.48e-4, 4.20e-6),
    "N2": (-2.01e-4, 4.55e-6),
    "He": (4.85e-4, -1.50e-7),
}

# ---------------------------------------------------------------------------
# Bühlmann ZH-L16C 16-Compartment Parameter Tables
# Format: (label, t_half_n2, a_n2, b_n2, t_half_he, a_he, b_he)
# ---------------------------------------------------------------------------
ZHL16C_COMP_1B: Tuple[str, float, float, float, float, float, float] = (
    "1b", 5.0, 1.1696, 0.5578, 1.88, 1.6189, 0.4770
)
ZHL16C_COMP_1A: Tuple[str, float, float, float, float, float, float] = (
    "1", 4.0, 1.2599, 0.5050, 1.51, 1.7424, 0.4245
)

ZHL16C_COMPARTMENTS_2_TO_16: List[Tuple[str, float, float, float, float, float, float]] = [
    ("2", 8.0, 1.0000, 0.6514, 3.02, 1.3830, 0.5747),
    ("3", 12.5, 0.8618, 0.7222, 4.72, 1.1919, 0.6527),
    ("4", 18.5, 0.7562, 0.7825, 6.99, 1.0458, 0.7223),
    ("5", 27.0, 0.6200, 0.8126, 10.21, 0.9220, 0.7582),
    ("6", 38.3, 0.5043, 0.8434, 14.48, 0.8205, 0.7957),
    ("7", 54.3, 0.4410, 0.8693, 20.53, 0.7305, 0.8279),
    ("8", 77.0, 0.4000, 0.8910, 29.11, 0.6502, 0.8553),
    ("9", 109.0, 0.3750, 0.9092, 41.20, 0.5950, 0.8757),
    ("10", 146.0, 0.3500, 0.9222, 55.19, 0.5545, 0.8903),
    ("11", 187.0, 0.3295, 0.9319, 70.69, 0.5333, 0.8997),
    ("12", 239.0, 0.3065, 0.9403, 90.34, 0.5189, 0.9073),
    ("13", 305.0, 0.2835, 0.9477, 115.29, 0.5181, 0.9122),
    ("14", 390.0, 0.2610, 0.9544, 147.42, 0.5176, 0.9171),
    ("15", 498.0, 0.2480, 0.9602, 188.24, 0.5172, 0.9217),
    ("16", 635.0, 0.2327, 0.9653, 240.03, 0.5119, 0.9267),
]

# NOAA / Erik Baker 7-segment CNS slope-intercept table:
# (po2_min_ata, po2_max_ata, slope_m, intercept_b)
NOAA_CNS_SEGMENTS: List[Tuple[float, float, float, float]] = [
    (0.50, 0.60, -1800.0, 1800.0),
    (0.60, 0.70, -1500.0, 1620.0),
    (0.70, 0.80, -1200.0, 1410.0),
    (0.80, 0.90, -900.0, 1170.0),
    (0.90, 1.10, -600.0, 900.0),
    (1.10, 1.50, -300.0, 570.0),
    (1.50, 1.60, -750.0, 1245.0),
]

# Standard Cylinder Library
STANDARD_CYLINDERS: Dict[str, Dict[str, Any]] = {
    "AL40": {"name": "Aluminum 40 Stage", "rated_cuft": 40.0, "rated_psi": 3000.0, "water_liters": 5.7, "rated_bar": 207.0},
    "AL80": {"name": "Aluminum 80", "rated_cuft": 77.4, "rated_psi": 3000.0, "water_liters": 11.1, "rated_bar": 207.0},
    "LP85": {"name": "Low Pressure Steel 85", "rated_cuft": 85.0, "rated_psi": 2640.0, "water_liters": 13.4, "rated_bar": 182.0},
    "LP108": {"name": "Low Pressure Steel 108", "rated_cuft": 108.0, "rated_psi": 2640.0, "water_liters": 17.0, "rated_bar": 182.0},
    "HP100": {"name": "High Pressure Steel 100", "rated_cuft": 100.0, "rated_psi": 3442.0, "water_liters": 12.9, "rated_bar": 237.0},
    "HP120": {"name": "High Pressure Steel 120", "rated_cuft": 120.0, "rated_psi": 3442.0, "water_liters": 15.3, "rated_bar": 237.0},
    "2xAL80": {"name": "Doubles Aluminum 80", "rated_cuft": 154.8, "rated_psi": 3000.0, "water_liters": 22.2, "rated_bar": 207.0},
    "2xLP85": {"name": "Doubles Steel LP85", "rated_cuft": 170.0, "rated_psi": 2640.0, "water_liters": 26.8, "rated_bar": 182.0},
    "2xLP108": {"name": "Doubles Steel LP108", "rated_cuft": 216.0, "rated_psi": 2640.0, "water_liters": 34.0, "rated_bar": 182.0},
    "2xHP100": {"name": "Doubles Steel HP100", "rated_cuft": 200.0, "rated_psi": 3442.0, "water_liters": 25.8, "rated_bar": 237.0},
    "3L_200": {"name": "3L CCR Cylinder", "rated_cuft": 21.2, "rated_psi": 2900.0, "water_liters": 3.0, "rated_bar": 200.0},
    "7L_232": {"name": "7L Euro Stage", "rated_cuft": 57.3, "rated_psi": 3365.0, "water_liters": 7.0, "rated_bar": 232.0},
    "12L_232": {"name": "Single 12L Euro", "rated_cuft": 98.3, "rated_psi": 3365.0, "water_liters": 12.0, "rated_bar": 232.0},
    "D12_232": {"name": "Twin 2x12L Euro Doubles", "rated_cuft": 196.6, "rated_psi": 3365.0, "water_liters": 24.0, "rated_bar": 232.0},
}

STANDARD_AGENCY_MIXES: List[Dict[str, Any]] = [
    {"name": "EAN32", "f_o2": 0.32, "f_he": 0.00},
    {"name": "EAN30", "f_o2": 0.30, "f_he": 0.00},
    {"name": "Air (21%)", "f_o2": 0.21, "f_he": 0.00},
    {"name": "Tx 21/35", "f_o2": 0.21, "f_he": 0.35},
    {"name": "Tx 18/45", "f_o2": 0.18, "f_he": 0.45},
    {"name": "Tx 15/55", "f_o2": 0.15, "f_he": 0.55},
    {"name": "Tx 13/54", "f_o2": 0.13, "f_he": 0.54},
    {"name": "Tx 12/60", "f_o2": 0.12, "f_he": 0.60},
    {"name": "Tx 10/70", "f_o2": 0.10, "f_he": 0.70},
]


class DivePlannerValidationError(ValueError):
    """Raised when user inputs violate physical or algorithmic constraints."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


def get_zhl16c_table(
    comp1_variant: str = "1b",
) -> List[Tuple[str, float, float, float, float, float, float]]:
    """Returns the 16-compartment Bühlmann ZH-L16C parameter list."""
    if comp1_variant not in ("1b", "1"):
        raise DivePlannerValidationError(
            "ERR_COMP1_VARIANT",
            f"Unsupported ZH-L16C compartment 1 variant '{comp1_variant}'. Must be '1b' or '1'.",
        )
    first = ZHL16C_COMP_1B if comp1_variant == "1b" else ZHL16C_COMP_1A
    return [first] + ZHL16C_COMPARTMENTS_2_TO_16


def get_hydrostatic_gradient_bar(depth_units: str = "feet", water_type: str = "salt") -> float:
    """Returns hydrostatic pressure change in bar per unit of depth."""
    if depth_units not in ("feet", "meters"):
        raise DivePlannerValidationError(
            "ERR_UNITS", f"depth_units must be 'feet' or 'meters', got '{depth_units}'."
        )
    if water_type not in ("salt", "fresh"):
        raise DivePlannerValidationError(
            "ERR_WATER_TYPE", f"water_type must be 'salt' or 'fresh', got '{water_type}'."
        )
    if depth_units == "feet":
        return K_FSW_BAR if water_type == "salt" else K_FFW_BAR
    return K_MSW_BAR if water_type == "salt" else K_MFW_BAR


def surface_pressure_bar(elevation_ft: float = 0.0) -> float:
    """Computes ISA barometric surface pressure in bar for an elevation in feet."""
    if elevation_ft < 0.0 or elevation_ft > 15000.0:
        raise DivePlannerValidationError(
            "ERR_ELEVATION",
            f"Dive site elevation must be between 0 and 15000 ft, got {elevation_ft}.",
        )
    h_m = elevation_ft * 0.3048
    return P0_BAR * math.pow(1.0 - 2.25577e-5 * h_m, 5.25588)


def depth_to_ambient_bar(
    depth: float,
    p_surf_bar: float = P0_BAR,
    depth_units: str = "feet",
    water_type: str = "salt",
) -> float:
    """Converts gauge depth to absolute ambient pressure in bar."""
    if depth < -1e-6:
        raise DivePlannerValidationError("ERR_DEPTH_TIME", f"Depth cannot be negative: {depth}.")
    k = get_hydrostatic_gradient_bar(depth_units, water_type)
    return p_surf_bar + max(0.0, depth) * k


def ambient_bar_to_depth(
    p_amb_bar: float,
    p_surf_bar: float = P0_BAR,
    depth_units: str = "feet",
    water_type: str = "salt",
) -> float:
    """Converts absolute ambient pressure in bar to gauge depth."""
    k = get_hydrostatic_gradient_bar(depth_units, water_type)
    return max(0.0, (p_amb_bar - p_surf_bar) / k)


def validate_gas_fractions(f_o2: float, f_he: float, label: str = "Gas") -> float:
    """Validates O2 and He fractions and returns the N2 fraction."""
    if f_o2 < 0.01 or f_o2 > 1.000001:
        raise DivePlannerValidationError(
            "ERR_GAS_FRACTIONS", f"{label} oxygen fraction must be in [0.01, 1.0], got {f_o2:.4f}."
        )
    if f_he < -1e-6 or f_he > 0.990001:
        raise DivePlannerValidationError(
            "ERR_GAS_FRACTIONS", f"{label} helium fraction must be in [0.0, 0.99], got {f_he:.4f}."
        )
    if f_o2 + f_he > 1.0001:
        raise DivePlannerValidationError(
            "ERR_GAS_FRACTIONS",
            f"{label} O2 ({f_o2*100:.1f}%) + He ({f_he*100:.1f}%) exceeds 100%.",
        )
    return max(0.0, 1.0 - f_o2 - f_he)


def format_gas_name(f_o2: float, f_he: float) -> str:
    """Formats standard gas name (e.g., Air, EAN32, O2 100%, Tx 18/45)."""
    o2_pct = round(f_o2 * 100)
    he_pct = round(f_he * 100)
    if he_pct > 0:
        return f"Tx {o2_pct}/{he_pct}"
    if o2_pct == 21:
        return "Air (21%)"
    if o2_pct == 100:
        return "O2 100%"
    return f"EAN{o2_pct}"


def alveolar_inert_pressures(
    p_amb_bar: float,
    f_o2: float,
    f_he: float,
    dive_mode: str = "OC",
    setpoint_bar: float = 1.2 * P0_BAR,
) -> Tuple[float, float, float, float, float]:
    """Computes alveolar inspired (P_i_N2, P_i_He) and loop fractions (F_O2_eff, F_N2_eff, F_He_eff).

    In OC mode:
      P_i_g = (P_amb - P_H2O) * F_g
    In CCR mode:
      P_O2_loop = min(setpoint_bar, P_amb)
      Remaining pressure (P_amb - P_O2_loop) is filled by the inert gases of the diluent
      in proportion to their diluent ratio.
    """
    f_n2 = validate_gas_fractions(f_o2, f_he)
    p_dry = max(0.0, p_amb_bar - P_H2O_BAR)

    if dive_mode == "OC":
        return p_dry * f_n2, p_dry * f_he, f_o2, f_n2, f_he

    if dive_mode != "CCR":
        raise DivePlannerValidationError("ERR_MODE", f"Unsupported dive_mode: '{dive_mode}'.")

    p_o2_loop = min(setpoint_bar, p_amb_bar)
    f_inert_dil = f_n2 + f_he
    if f_inert_dil <= 1e-9 or p_amb_bar <= 1e-9:
        return 0.0, 0.0, 1.0, 0.0, 0.0

    n2_share = f_n2 / f_inert_dil
    he_share = f_he / f_inert_dil

    p_inert_alv = max(0.0, p_amb_bar - P_H2O_BAR - p_o2_loop)
    p_i_n2 = p_inert_alv * n2_share
    p_i_he = p_inert_alv * he_share

    p_inert_loop = max(0.0, p_amb_bar - p_o2_loop)
    f_o2_eff = p_o2_loop / p_amb_bar
    f_n2_eff = (p_inert_loop / p_amb_bar) * n2_share
    f_he_eff = (p_inert_loop / p_amb_bar) * he_share
    return p_i_n2, p_i_he, f_o2_eff, f_n2_eff, f_he_eff


def haldane_step(p_0: float, p_i0: float, half_time_min: float, dt_min: float) -> float:
    """Computes constant-depth (isobaric) tissue gas tension after dt_min using Haldane's equation."""
    if dt_min <= 0.0:
        return p_0
    k = LN2 / half_time_min
    return p_i0 + (p_0 - p_i0) * math.exp(-k * dt_min)


def schreiner_step(
    p_0: float,
    p_i0: float,
    p_i_end: float,
    half_time_min: float,
    dt_min: float,
) -> float:
    """Computes variable-depth tissue gas tension after dt_min using Schreiner's equation."""
    if dt_min <= 0.0:
        return p_0
    r = (p_i_end - p_i0) / dt_min
    if abs(r) < 1e-12:
        return haldane_step(p_0, p_i0, half_time_min, dt_min)
    k = LN2 / half_time_min
    return p_i0 + r * (dt_min - 1.0 / k) - (p_i0 - p_0 - r / k) * math.exp(-k * dt_min)


def compartment_ceiling_bar(
    p_n2: float,
    p_he: float,
    a_n2: float,
    b_n2: float,
    a_he: float,
    b_he: float,
    gf: float,
) -> Tuple[float, float, float]:
    """Computes Erik Baker's Gradient Factor tolerated ambient pressure (ceiling) in bar.

    Returns (p_amb_tol_bar, a_weighted, b_weighted).
    """
    p_total = p_n2 + p_he
    if p_total <= 1e-12:
        return 0.0, a_n2, b_n2
    a_w = (a_n2 * p_n2 + a_he * p_he) / p_total
    b_w = (b_n2 * p_n2 + b_he * p_he) / p_total
    denom = gf / b_w - gf + 1.0
    p_tol = (p_total - a_w * gf) / denom
    return max(0.0, p_tol), a_w, b_w


def compartment_instantaneous_gf(
    p_n2: float,
    p_he: float,
    a_n2: float,
    b_n2: float,
    a_he: float,
    b_he: float,
    p_amb_bar: float,
) -> float:
    """Computes the current fraction of the raw Bühlmann M-value gradient at p_amb_bar."""
    p_total = p_n2 + p_he
    if p_total <= 1e-12:
        return 0.0
    a_w = (a_n2 * p_n2 + a_he * p_he) / p_total
    b_w = (b_n2 * p_n2 + b_he * p_he) / p_total
    m_val = a_w + p_amb_bar / b_w
    if m_val <= p_amb_bar + 1e-9:
        return 0.0
    return (p_total - p_amb_bar) / (m_val - p_amb_bar)


# ---------------------------------------------------------------------------
# Oxygen Toxicity: NOAA CNS % and Lambertsen / Baker OTU
# ---------------------------------------------------------------------------
def noaa_t_lim_min(po2_ata: float) -> Optional[float]:
    """Returns NOAA single-exposure CNS time limit in minutes for a given PO2 in ATA."""
    if po2_ata <= 0.50:
        return None
    for low, high, m, b in NOAA_CNS_SEGMENTS:
        if po2_ata <= high + 1e-9:
            return max(1.0, m * po2_ata + b)
    # Above 1.60 ATA: severe exponential penalty beyond the 45-minute limit at 1.60 ATA
    return max(1.0, 45.0 * math.exp(-5.0 * (po2_ata - 1.60)))


def calculate_cns_segment(po2_start_ata: float, po2_end_ata: float, dt_min: float) -> float:
    """Calculates CNS % accumulated over a constant or linearly changing PO2 segment."""
    if dt_min <= 0.0:
        return 0.0
    if max(po2_start_ata, po2_end_ata) <= 0.50:
        return 0.0

    # Isobaric / constant PO2 segment
    if abs(po2_end_ata - po2_start_ata) < 1e-7:
        t_lim = noaa_t_lim_min(po2_start_ata)
        return 0.0 if t_lim is None else (dt_min / t_lim) * 100.0

    # Linearly varying PO2 segment: split across NOAA range boundaries
    boundaries = [0.50, 0.60, 0.70, 0.80, 0.90, 1.10, 1.50, 1.60]
    p_min = min(po2_start_ata, po2_end_ata)
    p_max = max(po2_start_ata, po2_end_ata)
    total_dp = p_max - p_min

    # Collect cut points inside [p_min, p_max]
    cuts = [p_min]
    for b_pt in boundaries:
        if p_min + 1e-9 < b_pt < p_max - 1e-9:
            cuts.append(b_pt)
    cuts.append(p_max)

    cns_total = 0.0
    for idx in range(len(cuts) - 1):
        pa = cuts[idx]
        pb = cuts[idx + 1]
        sub_dt = dt_min * ((pb - pa) / total_dp)
        p_mid = 0.5 * (pa + pb)
        if p_mid <= 0.50:
            continue
        # Find matching linear segment
        seg_m = None
        seg_b = None
        for low, high, m, b in NOAA_CNS_SEGMENTS:
            if low - 1e-9 <= p_mid <= high + 1e-9:
                seg_m, seg_b = m, b
                break
        if seg_m is not None and seg_b is not None:
            r_o2 = (pb - pa) / sub_dt
            t_a = max(1.0, seg_m * pa + seg_b)
            t_b = max(1.0, seg_m * pb + seg_b)
            cns_total += (1.0 / (seg_m * r_o2)) * math.log(t_b / t_a) * 100.0
        else:
            t_mid = noaa_t_lim_min(p_mid)
            if t_mid is not None:
                cns_total += (sub_dt / t_mid) * 100.0
    return max(0.0, cns_total)


def decay_cns_surface_interval(cns_pct: float, surface_interval_min: float) -> float:
    """Decays accumulated CNS % across a surface interval using a 90-minute half-time."""
    if surface_interval_min <= 0.0:
        return max(0.0, cns_pct)
    return max(0.0, cns_pct * math.exp(-(LN2 / 90.0) * surface_interval_min))


def calculate_otu_segment(po2_start_ata: float, po2_end_ata: float, dt_min: float) -> float:
    """Calculates Pulmonary Oxygen Toxicity Units (OTU / UPTD) using Lambertsen / Baker equations."""
    if dt_min <= 0.0 or max(po2_start_ata, po2_end_ata) <= 0.50:
        return 0.0

    if abs(po2_end_ata - po2_start_ata) < 1e-7:
        if po2_start_ata <= 0.50:
            return 0.0
        return dt_min * math.pow((po2_start_ata - 0.50) / 0.50, 5.0 / 6.0)

    # If segment crosses 0.50 ATA threshold, clip to the active portion > 0.50 ATA
    p_low = min(po2_start_ata, po2_end_ata)
    p_high = max(po2_start_ata, po2_end_ata)
    active_dt = dt_min
    if p_low < 0.50:
        active_dt = dt_min * ((p_high - 0.50) / (p_high - p_low))
        p_low = 0.50

    if p_high - p_low < 1e-7:
        return active_dt * math.pow((p_high - 0.50) / 0.50, 5.0 / 6.0)

    term_high = math.pow((p_high - 0.50) / 0.50, 11.0 / 6.0)
    term_low = math.pow((p_low - 0.50) / 0.50, 11.0 / 6.0)
    return (3.0 * active_dt) / (11.0 * (p_high - p_low)) * (term_high - term_low)


# ---------------------------------------------------------------------------
# Diver Utility Tools 1, 2, 3, and 4
# ---------------------------------------------------------------------------
def calculate_gas_density_g_per_l(
    f_o2: float,
    f_he: float,
    p_amb_bar: float = P0_BAR,
    dive_mode: str = "OC",
    setpoint_bar: float = 1.2 * P0_BAR,
) -> Tuple[float, float, str]:
    """Calculates surface density (g/L), density at p_amb_bar (g/L), and UHMS/DAN status."""
    _, _, f_o2_eff, f_n2_eff, f_he_eff = alveolar_inert_pressures(
        p_amb_bar, f_o2, f_he, dive_mode=dive_mode, setpoint_bar=setpoint_bar
    )
    rho_surf = f_o2_eff * RHO_O2_STP + f_n2_eff * RHO_N2_STP + f_he_eff * RHO_HE_STP
    rho_depth = rho_surf * (p_amb_bar / P0_BAR)
    if rho_depth <= 5.2001:
        status = "NOMINAL"
    elif rho_depth <= 6.2001:
        status = "WARNING_HIGH_DENSITY"
    else:
        status = "CRITICAL_HYPERCAPNIA_RISK"
    return rho_surf, rho_depth, status


def calculate_ead_end_mod_density(
    depth: float,
    f_o2: float,
    f_he: float,
    o2_narcotic: bool = True,
    max_po2_ata: float = 1.40,
    deco_po2_ata: float = 1.60,
    min_po2_ata: float = 0.16,
    max_end: float = 100.0,
    elevation_ft: float = 0.0,
    depth_units: str = "feet",
    water_type: str = "salt",
    dive_mode: str = "OC",
    setpoint_ata: float = 1.20,
) -> Dict[str, Any]:
    """Tool 1 & Tool 4: Computes MOD, MinOD, EAD, END, MND, Gas Density (g/L), and MDD."""
    f_n2 = validate_gas_fractions(f_o2, f_he)
    p_surf = surface_pressure_bar(elevation_ft)
    k = get_hydrostatic_gradient_bar(depth_units, water_type)
    d_surf = p_surf / k
    p_amb = depth_to_ambient_bar(depth, p_surf, depth_units, water_type)

    setpoint_bar = setpoint_ata * P0_BAR
    _, _, f_o2_eff, f_n2_eff, f_he_eff = alveolar_inert_pressures(
        p_amb, f_o2, f_he, dive_mode=dive_mode, setpoint_bar=setpoint_bar
    )

    # MOD & MinOD (based on cylinder mix for OC, or diluent for CCR)
    p_max_work_bar = max_po2_ata * P0_BAR / f_o2
    p_max_deco_bar = deco_po2_ata * P0_BAR / f_o2
    p_min_bar = min_po2_ata * P0_BAR / f_o2

    mod_working = max(0.0, (p_max_work_bar - p_surf) / k)
    mod_deco = max(0.0, (p_max_deco_bar - p_surf) / k)
    min_od = max(0.0, (p_min_bar - p_surf) / k) if f_o2 < 0.18 else 0.0

    # EAD (Nitrogen equivalent relative to Air 79% N2)
    ead = max(0.0, (depth + d_surf) * (f_n2_eff / AIR_F_N2) - d_surf)

    # END & MND
    if o2_narcotic:
        narc_frac = max(1e-6, 1.0 - f_he_eff)
        end_val = max(0.0, (depth + d_surf) * narc_frac - d_surf)
        mnd_val = max(0.0, ((max_end + d_surf) / max(1e-6, 1.0 - f_he)) - d_surf)
    else:
        end_val = max(0.0, (depth + d_surf) * (f_n2_eff / AIR_F_N2) - d_surf)
        mnd_val = (
            max(0.0, ((max_end + d_surf) * AIR_F_N2 / f_n2) - d_surf)
            if f_n2 > 1e-6
            else 1000.0
        )

    rho_surf, rho_depth, density_status = calculate_gas_density_g_per_l(
        f_o2, f_he, p_amb, dive_mode=dive_mode, setpoint_bar=setpoint_bar
    )
    rho_oc_surf = f_o2 * RHO_O2_STP + f_n2 * RHO_N2_STP + f_he * RHO_HE_STP
    mdd_5_2 = max(0.0, (((5.2 / rho_oc_surf) * P0_BAR) - p_surf) / k)
    mdd_6_2 = max(0.0, (((6.2 / rho_oc_surf) * P0_BAR) - p_surf) / k)

    po2_at_depth_ata = (p_amb * f_o2_eff) / P0_BAR

    return {
        "depth": round(depth, 2),
        "depth_units": depth_units,
        "gas_name": format_gas_name(f_o2, f_he),
        "f_o2": round(f_o2, 4),
        "f_he": round(f_he, 4),
        "f_n2": round(f_n2, 4),
        "o2_narcotic": o2_narcotic,
        "ambient_pressure_bar": round(p_amb, 4),
        "ambient_pressure_ata": round(p_amb / P0_BAR, 4),
        "po2_at_depth_ata": round(po2_at_depth_ata, 3),
        "mod_working": round(mod_working, 1),
        "mod_deco": round(mod_deco, 1),
        "min_operating_depth": round(min_od, 1),
        "ead": round(ead, 1),
        "end": round(end_val, 1),
        "mnd": round(mnd_val, 1),
        "surface_density_g_l": round(rho_surf, 3),
        "density_at_depth_g_l": round(rho_depth, 2),
        "density_status": density_status,
        "mdd_5_2_g_l": round(mdd_5_2, 1),
        "mdd_6_2_g_l": round(mdd_6_2, 1),
    }


def calculate_best_mix_for_depth(
    depth: float,
    max_po2_ata: float = 1.40,
    max_end: float = 100.0,
    max_density_g_l: float = 5.20,
    o2_narcotic: bool = True,
    elevation_ft: float = 0.0,
    depth_units: str = "feet",
    water_type: str = "salt",
) -> Dict[str, Any]:
    """Tool 2: Computes Best Nitrox, Best Trimix, and closest Standard Agency Mix for depth."""
    if depth <= 0.0:
        raise DivePlannerValidationError("ERR_DEPTH_TIME", f"Target depth must be > 0, got {depth}.")
    if max_po2_ata <= 0.16 or max_po2_ata > 2.0:
        raise DivePlannerValidationError("ERR_PO2", f"Invalid max_po2_ata: {max_po2_ata}.")

    p_surf = surface_pressure_bar(elevation_ft)
    k = get_hydrostatic_gradient_bar(depth_units, water_type)
    d_surf = p_surf / k
    p_amb = depth_to_ambient_bar(depth, p_surf, depth_units, water_type)
    p_amb_ata = p_amb / P0_BAR

    # 1. Best O2 fraction (floored to whole percent so PO2 <= max_po2_ata)
    raw_f_o2 = min(1.0, max_po2_ata / p_amb_ata)
    f_o2_best = max(0.05, math.floor(raw_f_o2 * 100.0 + 1e-9) / 100.0)

    # 2. Required Helium fraction for END constraint
    if o2_narcotic:
        f_he_narc = max(0.0, 1.0 - ((max_end + d_surf) / (depth + d_surf)))
    else:
        f_n2_max = min(1.0 - f_o2_best, AIR_F_N2 * ((max_end + d_surf) / (depth + d_surf)))
        f_he_narc = max(0.0, 1.0 - f_o2_best - f_n2_max)

    # 3. Required Helium fraction for Gas Density <= max_density_g_l
    target_rho_surf = max_density_g_l / p_amb_ata
    numer = f_o2_best * (RHO_O2_STP - RHO_N2_STP) + RHO_N2_STP - target_rho_surf
    denom = RHO_N2_STP - RHO_HE_STP
    f_he_dens = max(0.0, numer / denom)

    f_he_best = min(
        round(1.0 - f_o2_best, 2),
        math.ceil(max(f_he_narc, f_he_dens) * 100.0 - 1e-9) / 100.0,
    )
    f_n2_best = round(max(0.0, 1.0 - f_o2_best - f_he_best), 2)

    # Evaluate properties of the computed best mix
    best_props = calculate_ead_end_mod_density(
        depth=depth,
        f_o2=f_o2_best,
        f_he=f_he_best,
        o2_narcotic=o2_narcotic,
        max_po2_ata=max_po2_ata,
        max_end=max_end,
        elevation_ft=elevation_ft,
        depth_units=depth_units,
        water_type=water_type,
    )

    # Find closest standard agency mix that satisfies PO2 <= max_po2_ata + 0.02 and END <= max_end + 10
    recommended_standard = None
    best_score = 1e9
    for candidate in STANDARD_AGENCY_MIXES:
        c_props = calculate_ead_end_mod_density(
            depth=depth,
            f_o2=candidate["f_o2"],
            f_he=candidate["f_he"],
            o2_narcotic=o2_narcotic,
            max_po2_ata=max_po2_ata,
            max_end=max_end,
            elevation_ft=elevation_ft,
            depth_units=depth_units,
            water_type=water_type,
        )
        if c_props["po2_at_depth_ata"] <= max_po2_ata + 0.02 and c_props["end"] <= max_end + (15.0 if depth_units == "feet" else 5.0):
            score = abs(candidate["f_o2"] - f_o2_best) * 2.0 + abs(candidate["f_he"] - f_he_best)
            if score < best_score:
                best_score = score
                recommended_standard = {
                    "name": candidate["name"],
                    "f_o2": candidate["f_o2"],
                    "f_he": candidate["f_he"],
                    "f_n2": round(1.0 - candidate["f_o2"] - candidate["f_he"], 2),
                    "po2_at_depth_ata": c_props["po2_at_depth_ata"],
                    "end": c_props["end"],
                    "density_at_depth_g_l": c_props["density_at_depth_g_l"],
                    "mod_working": c_props["mod_working"],
                }

    # Auto-recommend decompression gases based on depth
    recommended_deco_gases: List[Dict[str, Any]] = []
    stop_inc = 10.0 if depth_units == "feet" else 3.0
    if f_o2_best < 0.18:
        # Hypoxic bottom mix requires a travel/deep deco mix
        recommended_deco_gases.append({
            "name": "EAN32",
            "role": "travel",
            "f_o2": 0.32,
            "f_he": 0.0,
            "max_po2": 1.4,
            "switch_depth": math.floor((1.4 * P0_BAR / 0.32 - p_surf) / k / stop_inc) * stop_inc,
        })
    if depth >= (100.0 if depth_units == "feet" else 30.0):
        recommended_deco_gases.append({
            "name": "EAN50",
            "role": "deco",
            "f_o2": 0.50,
            "f_he": 0.0,
            "max_po2": 1.6,
            "switch_depth": 70.0 if depth_units == "feet" else 21.0,
        })
        recommended_deco_gases.append({
            "name": "O2 100%",
            "role": "deco",
            "f_o2": 1.00,
            "f_he": 0.0,
            "max_po2": 1.6,
            "switch_depth": 20.0 if depth_units == "feet" else 6.0,
        })

    return {
        "target_depth": depth,
        "depth_units": depth_units,
        "best_nitrox_f_o2": f_o2_best if f_he_best == 0.0 else min(0.40, f_o2_best),
        "best_mix_name": format_gas_name(f_o2_best, f_he_best),
        "f_o2": f_o2_best,
        "f_he": f_he_best,
        "f_n2": f_n2_best,
        "is_hypoxic_at_surface": f_o2_best < 0.18,
        "properties_at_depth": best_props,
        "closest_standard_agency_mix": recommended_standard,
        "recommended_deco_gases": recommended_deco_gases,
    }


def virial_z_factor(p_bar: float, f_o2: float, f_he: float) -> float:
    """Computes Real-Gas Compressibility Factor Z(P_bar, mix) at 20 C."""
    f_n2 = max(0.0, 1.0 - f_o2 - f_he)
    b_o2, c_o2 = VIRIAL_COEFFS["O2"]
    b_n2, c_n2 = VIRIAL_COEFFS["N2"]
    b_he, c_he = VIRIAL_COEFFS["He"]
    z_o2 = 1.0 + b_o2 * p_bar + c_o2 * (p_bar ** 2)
    z_n2 = 1.0 + b_n2 * p_bar + c_n2 * (p_bar ** 2)
    z_he = 1.0 + b_he * p_bar + c_he * (p_bar ** 2)
    return f_o2 * z_o2 + f_n2 * z_n2 + f_he * z_he


def calculate_cylinder_fill_capacity(
    cylinder_preset: str = "AL80",
    fill_pressure: float = 3000.0,
    pressure_units: str = "psi",
    f_o2: float = 0.21,
    f_he: float = 0.0,
    custom_rated_cuft: Optional[float] = None,
    custom_rated_psi: Optional[float] = None,
    custom_water_liters: Optional[float] = None,
) -> Dict[str, Any]:
    """Tool 3 Mode D: Calculates Ideal and Real-Gas (Z-factor) deliverable volume of a cylinder."""
    validate_gas_fractions(f_o2, f_he)
    if fill_pressure <= 0.0:
        raise DivePlannerValidationError("ERR_PRESSURE", f"Fill pressure must be > 0, got {fill_pressure}.")

    spec = STANDARD_CYLINDERS.get(cylinder_preset, STANDARD_CYLINDERS["AL80"]).copy()
    if custom_rated_cuft is not None and custom_rated_cuft > 0:
        spec["rated_cuft"] = custom_rated_cuft
    if custom_rated_psi is not None and custom_rated_psi > 0:
        spec["rated_psi"] = custom_rated_psi
    if custom_water_liters is not None and custom_water_liters > 0:
        spec["water_liters"] = custom_water_liters

    if pressure_units == "psi":
        fill_psi = fill_pressure
        fill_bar = fill_pressure / P0_PSI * P0_BAR
    elif pressure_units == "bar":
        fill_bar = fill_pressure
        fill_psi = fill_pressure / P0_BAR * P0_PSI
    else:
        raise DivePlannerValidationError("ERR_UNITS", f"Unsupported pressure_units: {pressure_units}")

    ideal_cuft = spec["rated_cuft"] * (fill_psi / spec["rated_psi"])
    ideal_liters = spec["water_liters"] * (fill_bar / P0_BAR)

    z_fill = virial_z_factor(fill_bar, f_o2, f_he)
    z_rated = virial_z_factor(spec["rated_bar"], f_o2, f_he)
    real_cuft = ideal_cuft * (z_rated / z_fill)
    real_liters = ideal_liters * (1.0 / z_fill)

    return {
        "cylinder_preset": cylinder_preset,
        "cylinder_name": spec["name"],
        "fill_pressure_psi": round(fill_psi, 1),
        "fill_pressure_bar": round(fill_bar, 1),
        "water_volume_liters": spec["water_liters"],
        "z_factor_at_fill": round(z_fill, 4),
        "ideal_volume_cuft": round(ideal_cuft, 1),
        "real_volume_cuft": round(real_cuft, 1),
        "ideal_volume_liters": round(ideal_liters, 1),
        "real_volume_liters": round(real_liters, 1),
    }


def calculate_gas_blender(
    mode: str = "partial_pressure",
    start_pressure: float = 0.0,
    start_f_o2: float = 0.21,
    start_f_he: float = 0.0,
    target_pressure: float = 3000.0,
    target_f_o2: float = 0.32,
    target_f_he: float = 0.0,
    topup_f_o2: float = 0.21,
    topup_f_he: float = 0.0,
    pressure_units: str = "psi",
    cylinder_preset: str = "2xLP85",
) -> Dict[str, Any]:
    """Tool 3 (Modes A, B, C, D): Nitrox/Trimix Partial-Pressure Blender, Top-Up, and Fill Capacity."""
    start_f_n2 = validate_gas_fractions(start_f_o2, start_f_he, "Starting Gas")
    target_f_n2 = validate_gas_fractions(target_f_o2, target_f_he, "Target Gas")
    topup_f_n2 = validate_gas_fractions(topup_f_o2, topup_f_he, "Top-Up Gas")

    if start_pressure < 0.0 or target_pressure <= 0.0:
        raise DivePlannerValidationError(
            "ERR_PRESSURE",
            f"Invalid pressures: start={start_pressure}, target={target_pressure}.",
        )

    if mode == "topup_result":
        if target_pressure <= start_pressure:
            raise DivePlannerValidationError(
                "ERR_PRESSURE",
                f"Top-up final pressure ({target_pressure}) must exceed start pressure ({start_pressure}).",
            )
        dp = target_pressure - start_pressure
        final_o2 = (start_pressure * start_f_o2 + dp * topup_f_o2) / target_pressure
        final_he = (start_pressure * start_f_he + dp * topup_f_he) / target_pressure
        final_n2 = max(0.0, 1.0 - final_o2 - final_he)
        cap = calculate_cylinder_fill_capacity(
            cylinder_preset=cylinder_preset,
            fill_pressure=target_pressure,
            pressure_units=pressure_units,
            f_o2=final_o2,
            f_he=final_he,
        )
        props = calculate_ead_end_mod_density(
            depth=100.0,
            f_o2=final_o2,
            f_he=final_he,
        )
        return {
            "mode": "topup_result",
            "pressure_units": pressure_units,
            "start_pressure": round(start_pressure, 1),
            "final_pressure": round(target_pressure, 1),
            "added_topup_pressure": round(dp, 1),
            "resulting_mix_name": format_gas_name(final_o2, final_he),
            "resulting_f_o2": round(final_o2, 4),
            "resulting_f_he": round(final_he, 4),
            "resulting_f_n2": round(final_n2, 4),
            "mod_working_fsw": props["mod_working"],
            "mod_deco_fsw": props["mod_deco"],
            "cylinder_capacity": cap,
        }

    # Mode A: Partial-Pressure Blending (He + O2 + Top-Up Gas with Bleed-Down check)
    if topup_f_n2 <= 1e-6:
        raise DivePlannerValidationError(
            "ERR_BLEND_IMPOSSIBLE", "Top-up gas must contain nitrogen to balance the blend."
        )

    p_max_he = (
        target_pressure * (target_f_he / start_f_he)
        if start_f_he > 1e-6
        else float("inf")
    )
    p_max_n2 = (
        target_pressure * (target_f_n2 / start_f_n2)
        if start_f_n2 > 1e-6
        else float("inf")
    )
    o2_excess_denom = start_f_o2 - start_f_n2 * (topup_f_o2 / topup_f_n2)
    o2_excess_numer = target_f_o2 - target_f_n2 * (topup_f_o2 / topup_f_n2)
    if o2_excess_denom > 1e-6:
        p_max_o2 = max(0.0, target_pressure * (o2_excess_numer / o2_excess_denom))
    else:
        p_max_o2 = float("inf")

    p_init = max(0.0, min(start_pressure, p_max_he, p_max_n2, p_max_o2))
    bleed_down = max(0.0, start_pressure - p_init)

    dp_he = target_pressure * target_f_he - p_init * start_f_he
    p_after_he = p_init + dp_he

    dp_top = (target_pressure * target_f_n2 - p_init * start_f_n2) / topup_f_n2
    dp_o2 = target_pressure - p_after_he - dp_top
    p_after_o2 = p_after_he + dp_o2

    if dp_he < -0.5 or dp_o2 < -0.5 or dp_top < -0.5:
        raise DivePlannerValidationError(
            "ERR_BLEND_IMPOSSIBLE",
            (
                f"Target mix {format_gas_name(target_f_o2, target_f_he)} cannot be blended using "
                f"top-up gas with {topup_f_o2*100:.1f}% O2 (requires pure N2/Argon or lower-O2 bank; "
                f"computed dP_O2={dp_o2:.1f})."
            ),
        )

    dp_he = max(0.0, dp_he)
    dp_o2 = max(0.0, dp_o2)
    dp_top = max(0.0, target_pressure - p_init - dp_he - dp_o2)

    # Continuous nitrox stick alternative after adding Helium
    rem_after_he = target_pressure - (p_init + dp_he)
    continuous_nitrox_f_o2 = (
        (target_pressure * target_f_o2 - p_init * start_f_o2) / rem_after_he
        if rem_after_he > 1e-6
        else 0.0
    )

    # Real-gas Z-factor corrected step pressures
    to_bar = (P0_BAR / P0_PSI) if pressure_units == "psi" else 1.0
    z_target = virial_z_factor(target_pressure * to_bar, target_f_o2, target_f_he)
    z_he_step = virial_z_factor(max(1.0, p_after_he * to_bar), 0.0, 1.0)
    real_dp_he = dp_he * (z_he_step / z_target)

    cap = calculate_cylinder_fill_capacity(
        cylinder_preset=cylinder_preset,
        fill_pressure=target_pressure,
        pressure_units=pressure_units,
        f_o2=target_f_o2,
        f_he=target_f_he,
    )

    return {
        "mode": "partial_pressure",
        "pressure_units": pressure_units,
        "target_mix_name": format_gas_name(target_f_o2, target_f_he),
        "start_pressure": round(start_pressure, 1),
        "bleed_down_amount": round(bleed_down, 1),
        "usable_initial_pressure": round(p_init, 1),
        "add_helium": round(dp_he, 1),
        "pressure_after_helium": round(p_init + dp_he, 1),
        "add_oxygen": round(dp_o2, 1),
        "pressure_after_oxygen": round(p_init + dp_he + dp_o2, 1),
        "add_topup_air": round(dp_top, 1),
        "final_target_pressure": round(target_pressure, 1),
        "real_gas_z_adjusted_helium": round(real_dp_he, 1),
        "continuous_nitrox_stick_f_o2_needed": round(continuous_nitrox_f_o2, 4),
        "cylinder_capacity": cap,
    }


# ---------------------------------------------------------------------------
# Full ZH-L16C + Gradient Factors Dive Planner Data Structures & Solver
# ---------------------------------------------------------------------------
@dataclass
class GasMix:
    name: str
    f_o2: float
    f_he: float
    role: str = "bottom"  # bottom | travel | deco | diluent | bailout
    max_po2: float = 1.40
    switch_depth: Optional[float] = None
    cylinder_preset: str = "AL80"
    start_pressure_psi: float = 3000.0
    enabled: bool = True

    @property
    def f_n2(self) -> float:
        return validate_gas_fractions(self.f_o2, self.f_he, self.name)


@dataclass
class DiveConfig:
    dive_mode: str = "OC"  # "OC" or "CCR"
    include_bailout: bool = True
    zhl16c_comp1_variant: str = "1b"  # "1b" or "1"
    gf_low: float = 30.0
    gf_high: float = 85.0
    o2_narcotic: bool = True
    depth_units: str = "feet"  # "feet" or "meters"
    volume_units: str = "cuft"  # "cuft" or "liters"
    pressure_units: str = "psi"  # "psi" or "bar"
    setpoint_units: str = "ATA"  # "ATA" or "BAR"
    elevation_ft: float = 0.0
    water_type: str = "salt"  # "salt" or "fresh"
    stop_size: float = 10.0
    last_oc_stop: float = 10.0
    last_ccr_stop: float = 10.0
    min_stop_time_sec: int = 60
    descent_rate: float = 60.0
    ascent_rate: float = 30.0
    deco_ascent_rate: float = 30.0
    surface_ascent_rate: float = 10.0
    bottom_rmv: float = 0.75
    deco_rmv: float = 0.60
    ccr_setpoint_bottom: float = 1.20
    ccr_setpoint_deco: float = 1.30
    segments: List[Dict[str, Any]] = field(default_factory=lambda: [{"depth": 150.0, "time_min": 25.0}])
    oc_gases: List[GasMix] = field(default_factory=list)
    ccr_diluent: Optional[GasMix] = None
    bailout_gases: List[GasMix] = field(default_factory=list)

    def validate(self) -> None:
        if self.dive_mode not in ("OC", "CCR"):
            raise DivePlannerValidationError("ERR_MODE", f"Invalid dive_mode: {self.dive_mode}")
        if self.gf_low < 1.0 or self.gf_high > 100.0 or self.gf_low > self.gf_high:
            raise DivePlannerValidationError(
                "ERR_GF_RANGE",
                f"Invalid Gradient Factors: GF Low ({self.gf_low}%) must be in [1, GF High] and GF High ({self.gf_high}%) <= 100%.",
            )
        if not (1 <= int(self.min_stop_time_sec) <= 60):
            raise DivePlannerValidationError(
                "ERR_STOP_INTERVAL",
                f"min_stop_time_sec must be between 1s minimum and 60s (1 min) maximum, got {self.min_stop_time_sec}.",
            )
        for rate_name, rate_val in [
            ("descent_rate", self.descent_rate),
            ("ascent_rate", self.ascent_rate),
            ("deco_ascent_rate", self.deco_ascent_rate),
            ("surface_ascent_rate", self.surface_ascent_rate),
            ("stop_size", self.stop_size),
            ("last_oc_stop", self.last_oc_stop),
            ("last_ccr_stop", self.last_ccr_stop),
            ("bottom_rmv", self.bottom_rmv),
            ("deco_rmv", self.deco_rmv),
        ]:
            if rate_val <= 0.0:
                raise DivePlannerValidationError(
                    "ERR_KINEMATIC_RATE", f"Parameter '{rate_name}' must be > 0, got {rate_val}."
                )
        if not self.segments:
            raise DivePlannerValidationError("ERR_DEPTH_TIME", "At least one dive segment is required.")
        max_allowed_depth = 1000.0 if self.depth_units == "feet" else 305.0
        for idx, seg in enumerate(self.segments):
            d = float(seg.get("depth", -1))
            t = float(seg.get("time_min", -1))
            if d <= 0.0 or d > max_allowed_depth or t <= 0.0:
                raise DivePlannerValidationError(
                    "ERR_DEPTH_TIME",
                    f"Segment {idx} has invalid depth ({d}) or time_min ({t}).",
                )
        surface_pressure_bar(self.elevation_ft)


def _setpoint_to_bar(sp_val: float, setpoint_units: str) -> float:
    return sp_val * P0_BAR if setpoint_units == "ATA" else sp_val


def _compute_default_switch_depth(
    gas: GasMix,
    p_surf_bar: float,
    k_bar: float,
    stop_size: float,
) -> float:
    if gas.switch_depth is not None and gas.switch_depth > 0:
        return float(gas.switch_depth)
    p_max_bar = gas.max_po2 * P0_BAR / gas.f_o2
    mod_raw = max(0.0, (p_max_bar - p_surf_bar) / k_bar)
    if gas.role == "deco":
        return max(stop_size, math.floor((mod_raw + 1e-6) / stop_size) * stop_size)
    return round(mod_raw, 1)


def _select_best_deco_gas(
    depth: float,
    gases: Sequence[GasMix],
    current_gas: GasMix,
    p_surf_bar: float,
    k_bar: float,
    stop_size: float,
) -> GasMix:
    """Selects the highest-FO2 enabled gas whose switch depth >= depth and is breathable."""
    p_amb = p_surf_bar + depth * k_bar
    candidates: List[GasMix] = []
    for g in gases:
        if not g.enabled:
            continue
        sw = _compute_default_switch_depth(g, p_surf_bar, k_bar, stop_size)
        po2_ata = (p_amb * g.f_o2) / P0_BAR
        if depth <= sw + 1e-6 and 0.16 <= po2_ata <= (g.max_po2 + 0.05):
            candidates.append(g)
    if not candidates:
        return current_gas
    # Prefer highest f_o2, then lowest f_n2
    candidates.sort(key=lambda g: (round(g.f_o2, 4), -round(g.f_n2, 4)), reverse=True)
    return candidates[0]


def _evolve_tissues(
    tissues_n2: List[float],
    tissues_he: List[float],
    table: List[Tuple[str, float, float, float, float, float, float]],
    p_start_bar: float,
    p_end_bar: float,
    dt_min: float,
    gas: GasMix,
    dive_mode: str,
    setpoint_bar: float,
) -> Tuple[List[float], List[float]]:
    """Evolves all 16 compartments over a constant or linear-depth-change segment."""
    pi0_n2, pi0_he, _, _, _ = alveolar_inert_pressures(
        p_start_bar, gas.f_o2, gas.f_he, dive_mode=dive_mode, setpoint_bar=setpoint_bar
    )
    pi1_n2, pi1_he, _, _, _ = alveolar_inert_pressures(
        p_end_bar, gas.f_o2, gas.f_he, dive_mode=dive_mode, setpoint_bar=setpoint_bar
    )
    new_n2: List[float] = []
    new_he: List[float] = []
    is_flat = abs(p_end_bar - p_start_bar) < 1e-9
    for idx, (_, th_n2, _, _, th_he, _, _) in enumerate(table):
        if is_flat:
            new_n2.append(haldane_step(tissues_n2[idx], pi0_n2, th_n2, dt_min))
            new_he.append(haldane_step(tissues_he[idx], pi0_he, th_he, dt_min))
        else:
            new_n2.append(schreiner_step(tissues_n2[idx], pi0_n2, pi1_n2, th_n2, dt_min))
            new_he.append(schreiner_step(tissues_he[idx], pi0_he, pi1_he, th_he, dt_min))
    return new_n2, new_he


def _controlling_ceiling_bar(
    tissues_n2: Sequence[float],
    tissues_he: Sequence[float],
    table: Sequence[Tuple[str, float, float, float, float, float, float]],
    gf: float,
) -> Tuple[float, str, int]:
    """Returns (max_ceiling_bar, leading_comp_label, leading_comp_index)."""
    max_p = 0.0
    lead_label = table[0][0]
    lead_idx = 0
    for idx, (label, _, a_n2, b_n2, _, a_he, b_he) in enumerate(table):
        p_tol, _, _ = compartment_ceiling_bar(
            tissues_n2[idx], tissues_he[idx], a_n2, b_n2, a_he, b_he, gf
        )
        if p_tol > max_p:
            max_p = p_tol
            lead_label = label
            lead_idx = idx
    return max_p, lead_label, lead_idx


def _execute_single_schedule(
    cfg: DiveConfig,
    schedule_mode: str,  # "OC", "CCR", or "BAILOUT"
    initial_n2: Optional[List[float]] = None,
    initial_he: Optional[List[float]] = None,
    initial_cns: float = 0.0,
    initial_otu: float = 0.0,
) -> Dict[str, Any]:
    """Executes the full descent, bottom, ascent, and ZH-L16C + GF decompression schedule."""
    cfg.validate()
    table = get_zhl16c_table(cfg.zhl16c_comp1_variant)
    p_surf = surface_pressure_bar(cfg.elevation_ft)
    k_bar = get_hydrostatic_gradient_bar(cfg.depth_units, cfg.water_type)
    gf_low_dec = cfg.gf_low / 100.0
    gf_high_dec = cfg.gf_high / 100.0

    # Initialize tissue tensions
    if initial_n2 is not None and initial_he is not None:
        tissues_n2 = list(initial_n2)
        tissues_he = list(initial_he)
    else:
        n2_init = (p_surf - P_H2O_BAR) * AIR_F_N2
        tissues_n2 = [n2_init for _ in range(16)]
        tissues_he = [0.0 for _ in range(16)]

    # Set up active gases
    if schedule_mode in ("CCR", "BAILOUT"):
        diluent = cfg.ccr_diluent or GasMix(name="Diluent Tx 13/54", f_o2=0.13, f_he=0.54, role="diluent")
        deco_gases = list(cfg.bailout_gases) if schedule_mode == "BAILOUT" else [diluent]
        if schedule_mode == "BAILOUT" and not deco_gases:
            deco_gases = list(cfg.oc_gases) if cfg.oc_gases else [
                GasMix(name="Bailout Tx 13/54", f_o2=0.13, f_he=0.54, role="bailout", max_po2=1.4, switch_depth=250.0),
                GasMix(name="Bailout EAN50", f_o2=0.50, f_he=0.0, role="bailout", max_po2=1.6, switch_depth=70.0 if cfg.depth_units == "feet" else 21.0),
                GasMix(name="Bailout O2 100%", f_o2=1.00, f_he=0.0, role="bailout", max_po2=1.6, switch_depth=20.0 if cfg.depth_units == "feet" else 6.0),
            ]
        bottom_gas = diluent
        bottom_mode = "CCR"
    else:
        oc_list = list(cfg.oc_gases) if cfg.oc_gases else [
            GasMix(name="EAN32", f_o2=0.32, f_he=0.0, role="bottom", max_po2=1.4)
        ]
        bottom_candidates = [g for g in oc_list if g.enabled and g.role == "bottom"]
        bottom_gas = bottom_candidates[0] if bottom_candidates else oc_list[0]
        deco_gases = [g for g in oc_list if g.enabled]
        bottom_mode = "OC"

    sp_bottom_bar = _setpoint_to_bar(cfg.ccr_setpoint_bottom, cfg.setpoint_units)
    sp_deco_bar = _setpoint_to_bar(cfg.ccr_setpoint_deco, cfg.setpoint_units)

    steps: List[Dict[str, Any]] = []
    profile_points: List[Dict[str, Any]] = []
    gas_consumption: Dict[str, float] = {}
    warnings: List[str] = []

    runtime_min = 0.0
    current_depth = 0.0
    cns_total = initial_cns
    otu_total = initial_otu

    def record_point(d_val: float, t_val: float, gf_ref: float, active_gas: GasMix, mode_str: str, sp_b: float) -> None:
        p_amb = p_surf + d_val * k_bar
        p_ceil, lead_lbl, _ = _controlling_ceiling_bar(tissues_n2, tissues_he, table, gf_ref)
        ceil_depth = ambient_bar_to_depth(p_ceil, p_surf, cfg.depth_units, cfg.water_type)
        _, _, f_o2_e, _, _ = alveolar_inert_pressures(
            p_amb, active_gas.f_o2, active_gas.f_he, dive_mode=mode_str, setpoint_bar=sp_b
        )
        _, rho_d, _ = calculate_gas_density_g_per_l(
            active_gas.f_o2, active_gas.f_he, p_amb, dive_mode=mode_str, setpoint_bar=sp_b
        )
        profile_points.append({
            "time_min": round(t_val, 3),
            "depth": round(d_val, 2),
            "ceiling_depth": round(ceil_depth, 2),
            "po2_ata": round((p_amb * f_o2_e) / P0_BAR, 3),
            "density_g_l": round(rho_d, 2),
            "gas_name": active_gas.name if mode_str == "OC" else f"{active_gas.name} (SP {sp_b/P0_BAR:.2f})",
            "leading_compartment": lead_lbl,
        })

    def append_segment(
        phase: str,
        d_start: float,
        d_end: float,
        dt_min: float,
        active_gas: GasMix,
        mode_str: str,
        sp_b: float,
        rmv_rate: float,
        gf_eval: float,
    ) -> None:
        nonlocal runtime_min, current_depth, tissues_n2, tissues_he, cns_total, otu_total
        if dt_min <= 1e-9:
            return
        p_start = p_surf + d_start * k_bar
        p_end = p_surf + d_end * k_bar
        tissues_n2, tissues_he = _evolve_tissues(
            tissues_n2, tissues_he, table, p_start, p_end, dt_min, active_gas, mode_str, sp_b
        )

        _, _, f_o2_s, _, _ = alveolar_inert_pressures(
            p_start, active_gas.f_o2, active_gas.f_he, dive_mode=mode_str, setpoint_bar=sp_b
        )
        _, _, f_o2_e, f_n2_e, f_he_e = alveolar_inert_pressures(
            p_end, active_gas.f_o2, active_gas.f_he, dive_mode=mode_str, setpoint_bar=sp_b
        )
        po2_s_ata = (p_start * f_o2_s) / P0_BAR
        po2_e_ata = (p_end * f_o2_e) / P0_BAR

        cns_total += calculate_cns_segment(po2_s_ata, po2_e_ata, dt_min)
        otu_total += calculate_otu_segment(po2_s_ata, po2_e_ata, dt_min)

        p_avg = 0.5 * (p_start + p_end)
        vol_used = rmv_rate * (p_avg / P0_BAR) * dt_min if mode_str == "OC" else 0.0
        if mode_str == "OC":
            gas_consumption[active_gas.name] = gas_consumption.get(active_gas.name, 0.0) + vol_used

        runtime_min += dt_min
        current_depth = d_end

        p_ceil, lead_lbl, _ = _controlling_ceiling_bar(tissues_n2, tissues_he, table, gf_eval)
        ceil_depth = ambient_bar_to_depth(p_ceil, p_surf, cfg.depth_units, cfg.water_type)

        props_end = calculate_ead_end_mod_density(
            depth=d_end,
            f_o2=active_gas.f_o2,
            f_he=active_gas.f_he,
            o2_narcotic=cfg.o2_narcotic,
            elevation_ft=cfg.elevation_ft,
            depth_units=cfg.depth_units,
            water_type=cfg.water_type,
            dive_mode=mode_str,
            setpoint_ata=sp_b / P0_BAR,
        )

        if po2_e_ata < 0.16 and d_end > 0:
            warnings.append(f"HYPOXIC_WARNING: PO2 ({po2_e_ata:.2f} ATA) below 0.16 ATA on {active_gas.name} at {d_end:.0f} {cfg.depth_units}.")
        if po2_e_ata > 1.65:
            warnings.append(f"HYPEROXIC_WARNING: PO2 ({po2_e_ata:.2f} ATA) exceeds 1.60 ATA on {active_gas.name} at {d_end:.0f} {cfg.depth_units}.")
        if props_end["density_at_depth_g_l"] > 5.2:
            warnings.append(f"GAS_DENSITY_ALERT: {props_end['density_at_depth_g_l']:.2f} g/L at {d_end:.0f} {cfg.depth_units} on {active_gas.name}.")

        steps.append({
            "phase": phase,
            "start_depth": round(d_start, 1),
            "depth": round(d_end, 1),
            "duration_min": round(dt_min, 2),
            "duration_mmss": f"{int(round(dt_min*60))//60:02d}:{int(round(dt_min*60))%60:02d}",
            "runtime_min": round(runtime_min, 2),
            "runtime_mmss": f"{int(round(runtime_min*60))//60:02d}:{int(round(runtime_min*60))%60:02d}",
            "gas_name": active_gas.name if mode_str == "OC" else f"{active_gas.name} (SP {sp_b/P0_BAR:.2f})",
            "f_o2_eff": round(f_o2_e, 3),
            "f_he_eff": round(f_he_e, 3),
            "f_n2_eff": round(f_n2_e, 3),
            "po2_ata": round(po2_e_ata, 2),
            "ead": props_end["ead"],
            "end": props_end["end"],
            "density_g_l": props_end["density_at_depth_g_l"],
            "ceiling_depth": round(ceil_depth, 1),
            "gf_target": round(gf_eval * 100.0, 1),
            "leading_compartment": lead_lbl,
            "cns_pct": round(cns_total, 1),
            "otu": round(otu_total, 1),
            "gas_volume_used": round(vol_used, 1),
        })
        record_point(d_end, runtime_min, gf_eval, active_gas, mode_str, sp_b)

    # Record surface start point
    record_point(0.0, 0.0, gf_low_dec, bottom_gas, bottom_mode, sp_bottom_bar)

    # 1. Execute Descent and Bottom Segments
    for seg in cfg.segments:
        target_d = float(seg["depth"])
        seg_time = float(seg["time_min"])
        seg_gas_name = seg.get("gas_name")
        seg_gas = bottom_gas
        if seg_gas_name and bottom_mode == "OC":
            for g in cfg.oc_gases:
                if g.name == seg_gas_name:
                    seg_gas = g
                    break

        if abs(target_d - current_depth) > 1e-6:
            rate = cfg.descent_rate if target_d > current_depth else cfg.ascent_rate
            travel_dt = abs(target_d - current_depth) / rate
            phase_lbl = "DESCENT" if target_d > current_depth else "LEVEL_ASCENT"
            append_segment(
                phase_lbl,
                current_depth,
                target_d,
                travel_dt,
                seg_gas,
                bottom_mode,
                sp_bottom_bar,
                cfg.bottom_rmv,
                gf_low_dec,
            )
            bottom_time_rem = max(0.5, seg_time - travel_dt) if len(cfg.segments) == 1 else seg_time
        else:
            bottom_time_rem = seg_time

        append_segment(
            "BOTTOM",
            target_d,
            target_d,
            bottom_time_rem,
            seg_gas,
            bottom_mode,
            sp_bottom_bar,
            cfg.bottom_rmv,
            gf_low_dec,
        )

    # Capture bottom turn tissue state
    bottom_turn_tissues = [
        {
            "compartment": table[i][0],
            "p_n2_bar": round(tissues_n2[i], 4),
            "p_he_bar": round(tissues_he[i], 4),
            "p_total_bar": round(tissues_n2[i] + tissues_he[i], 4),
        }
        for i in range(16)
    ]

    # 2. Ascent & Decompression Phase
    ascent_mode = "CCR" if schedule_mode == "CCR" else "OC"
    last_stop_depth = cfg.last_ccr_stop if ascent_mode == "CCR" else cfg.last_oc_stop
    active_ascent_gas = (
        bottom_gas
        if ascent_mode == "CCR"
        else _select_best_deco_gas(current_depth, deco_gases, bottom_gas, p_surf, k_bar, cfg.stop_size)
    )

    if schedule_mode == "BAILOUT":
        steps.append({
            "phase": "BAILOUT_SWITCH",
            "start_depth": round(current_depth, 1),
            "depth": round(current_depth, 1),
            "duration_min": 0.0,
            "duration_mmss": "00:00",
            "runtime_min": round(runtime_min, 2),
            "runtime_mmss": f"{int(round(runtime_min*60))//60:02d}:{int(round(runtime_min*60))%60:02d}",
            "gas_name": active_ascent_gas.name,
            "f_o2_eff": round(active_ascent_gas.f_o2, 3),
            "f_he_eff": round(active_ascent_gas.f_he, 3),
            "f_n2_eff": round(active_ascent_gas.f_n2, 3),
            "po2_ata": round(((p_surf + current_depth * k_bar) * active_ascent_gas.f_o2) / P0_BAR, 2),
            "ead": 0.0,
            "end": 0.0,
            "density_g_l": 0.0,
            "ceiling_depth": 0.0,
            "gf_target": round(gf_low_dec * 100.0, 1),
            "leading_compartment": table[0][0],
            "cns_pct": round(cns_total, 1),
            "otu": round(otu_total, 1),
            "gas_volume_used": 0.0,
        })

    # Generate candidate stop depths from deepest multiple of stop_size down to last_stop_depth
    max_stop = math.floor(current_depth / cfg.stop_size) * cfg.stop_size
    candidate_stops: List[float] = []
    d_cursor = max_stop
    while d_cursor >= last_stop_depth - 1e-6:
        if d_cursor > 0:
            candidate_stops.append(round(d_cursor, 4))
        d_cursor -= cfg.stop_size
    if not candidate_stops or abs(candidate_stops[-1] - last_stop_depth) > 1e-4:
        if last_stop_depth < current_depth:
            candidate_stops.append(last_stop_depth)
    candidate_stops = sorted(list(set(candidate_stops)), reverse=True)

    # Check if direct ascent to surface (0.0) without any stops violates GF High
    def can_ascend_to(
        d_from: float,
        d_to: float,
        n2_state: List[float],
        he_state: List[float],
        gas_use: GasMix,
        gf_allow: float,
        rate_use: float,
    ) -> bool:
        dt = abs(d_from - d_to) / rate_use
        p_from = p_surf + d_from * k_bar
        p_to = p_surf + d_to * k_bar
        sim_n2, sim_he = _evolve_tissues(
            list(n2_state), list(he_state), table, p_from, p_to, dt, gas_use, ascent_mode, sp_deco_bar
        )
        p_ceil, _, _ = _controlling_ceiling_bar(sim_n2, sim_he, table, gf_allow)
        return p_ceil <= p_to + 1e-5

    first_stop_depth: float = 0.0
    if not can_ascend_to(
        current_depth, 0.0, tissues_n2, tissues_he, active_ascent_gas, gf_high_dec, cfg.ascent_rate
    ):
        # Find the deepest stop depth where ascending to the next shallower level would violate GF Low
        first_stop_depth = last_stop_depth
        for idx, cand_d in enumerate(candidate_stops):
            next_shallower = candidate_stops[idx + 1] if idx + 1 < len(candidate_stops) else 0.0
            gf_check = gf_low_dec if next_shallower > 0 else gf_high_dec
            if not can_ascend_to(
                current_depth,
                next_shallower,
                tissues_n2,
                tissues_he,
                active_ascent_gas,
                gf_check,
                cfg.ascent_rate,
            ):
                first_stop_depth = cand_d
                break

    if first_stop_depth <= 0.0:
        # No-Decompression Ascent directly to surface
        asc_dt = current_depth / cfg.ascent_rate
        append_segment(
            "ASCENT_NO_DECO",
            current_depth,
            0.0,
            asc_dt,
            active_ascent_gas,
            ascent_mode,
            sp_deco_bar,
            cfg.bottom_rmv,
            gf_high_dec,
        )
        total_deco_min = 0.0
    else:
        # Ascend from bottom to first_stop_depth (checking for intermediate travel gas switches)
        active_stops = [s for s in candidate_stops if s <= first_stop_depth + 1e-6]
        asc_dt = (current_depth - first_stop_depth) / cfg.ascent_rate
        append_segment(
            "ASCENT_TO_DECO",
            current_depth,
            first_stop_depth,
            asc_dt,
            active_ascent_gas,
            ascent_mode,
            sp_deco_bar,
            cfg.bottom_rmv,
            gf_low_dec,
        )

        quantum_min = cfg.min_stop_time_sec / 60.0
        total_deco_min = 0.0

        for s_idx, stop_d in enumerate(active_stops):
            next_d = active_stops[s_idx + 1] if s_idx + 1 < len(active_stops) else 0.0
            asc_rate_next = cfg.deco_ascent_rate if next_d > 0 else cfg.surface_ascent_rate

            # Target GF at next_d along the linear ramp from (first_stop_depth, gf_low) to (0, gf_high)
            gf_next = gf_low_dec + (gf_high_dec - gf_low_dec) * ((first_stop_depth - next_d) / first_stop_depth)
            gf_curr = gf_low_dec + (gf_high_dec - gf_low_dec) * ((first_stop_depth - stop_d) / first_stop_depth)

            # Check for optimal deco gas switch at stop_d
            if ascent_mode == "OC":
                best_gas = _select_best_deco_gas(stop_d, deco_gases, active_ascent_gas, p_surf, k_bar, cfg.stop_size)
                if best_gas.name != active_ascent_gas.name:
                    active_ascent_gas = best_gas

            # Calculate required wait time at stop_d in multiples of quantum_min on a tissue copy
            sim_n2 = list(tissues_n2)
            sim_he = list(tissues_he)
            wait_min = 0.0
            p_stop = p_surf + stop_d * k_bar
            while not can_ascend_to(
                stop_d, next_d, sim_n2, sim_he, active_ascent_gas, gf_next, asc_rate_next
            ):
                wait_min += quantum_min
                sim_n2, sim_he = _evolve_tissues(
                    sim_n2,
                    sim_he,
                    table,
                    p_stop,
                    p_stop,
                    quantum_min,
                    active_ascent_gas,
                    ascent_mode,
                    sp_deco_bar,
                )
                if wait_min > 2400.0:
                    break

            if wait_min > 0.0 or s_idx == 0:
                if wait_min == 0.0:
                    wait_min = quantum_min
                append_segment(
                    "DECO_STOP",
                    stop_d,
                    stop_d,
                    wait_min,
                    active_ascent_gas,
                    ascent_mode,
                    sp_deco_bar,
                    cfg.deco_rmv,
                    gf_curr,
                )
                total_deco_min += wait_min

            # Ascend to next_d
            inter_dt = abs(stop_d - next_d) / asc_rate_next
            append_segment(
                "DECO_ASCENT" if next_d > 0 else "SURFACE_ASCENT",
                stop_d,
                next_d,
                inter_dt,
                active_ascent_gas,
                ascent_mode,
                sp_deco_bar,
                cfg.deco_rmv,
                gf_next,
            )
            total_deco_min += inter_dt

    # 3. Compute Final Surface 16-Compartment Matrix
    final_compartments: List[Dict[str, Any]] = []
    for idx, (label, th_n2, a_n2, b_n2, th_he, a_he, b_he) in enumerate(table):
        p_n2 = tissues_n2[idx]
        p_he = tissues_he[idx]
        p_tot = p_n2 + p_he
        p_tol_gf, a_w, b_w = compartment_ceiling_bar(
            p_n2, p_he, a_n2, b_n2, a_he, b_he, gf_high_dec
        )
        m0_raw = a_w + p_surf / b_w
        m0_gf = p_surf + gf_high_dec * (m0_raw - p_surf)
        gf_surf_now = compartment_instantaneous_gf(
            p_n2, p_he, a_n2, b_n2, a_he, b_he, p_surf
        )
        final_compartments.append({
            "compartment": label,
            "t_half_n2_min": th_n2,
            "t_half_he_min": th_he,
            "p_n2_bar": round(p_n2, 4),
            "p_he_bar": round(p_he, 4),
            "p_total_bar": round(p_tot, 4),
            "m0_raw_bar": round(m0_raw, 4),
            "m0_gf_high_bar": round(m0_gf, 4),
            "surface_gf_pct": round(max(0.0, gf_surf_now * 100.0), 1),
            "pct_of_m0_raw": round((p_tot / m0_raw) * 100.0, 1),
            "ceiling_depth": round(ambient_bar_to_depth(p_tol_gf, p_surf, cfg.depth_units, cfg.water_type), 1),
        })

    # 4. Cylinder Gas Logistics Summary
    cylinder_logistics: List[Dict[str, Any]] = []
    relevant_gases = deco_gases if schedule_mode != "CCR" else ([cfg.ccr_diluent] if cfg.ccr_diluent else [bottom_gas])
    for g in relevant_gases:
        used_vol = gas_consumption.get(g.name, 0.0)
        cap = calculate_cylinder_fill_capacity(
            cylinder_preset=g.cylinder_preset,
            fill_pressure=g.start_pressure_psi,
            pressure_units="psi",
            f_o2=g.f_o2,
            f_he=g.f_he,
        )
        total_avail = cap["ideal_volume_cuft"] if cfg.volume_units == "cuft" else cap["ideal_volume_liters"]
        pct_used = (used_vol / total_avail * 100.0) if total_avail > 0 else 0.0
        end_pressure_psi = max(0.0, g.start_pressure_psi * (1.0 - used_vol / max(1e-6, total_avail)))
        turn_pressure_thirds_psi = round(g.start_pressure_psi * (2.0 / 3.0), 0)
        status_str = "OK"
        if g.role == "bottom" and pct_used > 66.7:
            status_str = "EXCEEDS_RULE_OF_THIRDS"
            warnings.append(f"GAS_RESERVE_WARNING: {g.name} consumes {pct_used:.1f}% of cylinder ({g.cylinder_preset}), exceeding Rule of Thirds (66.7%).")
        elif pct_used > 85.0:
            status_str = "CRITICAL_LOW_RESERVE"
            warnings.append(f"GAS_CRITICAL: {g.name} consumes {pct_used:.1f}% of cylinder ({g.cylinder_preset}).")

        cylinder_logistics.append({
            "gas_name": g.name,
            "role": g.role,
            "cylinder_preset": g.cylinder_preset,
            "start_pressure_psi": round(g.start_pressure_psi, 0),
            "end_pressure_psi": round(end_pressure_psi, 0),
            "turn_pressure_thirds_psi": turn_pressure_thirds_psi,
            "volume_available": round(total_avail, 1),
            "volume_consumed": round(used_vol, 1),
            "volume_units": cfg.volume_units,
            "percent_consumed": round(pct_used, 1),
            "status": status_str,
        })

    max_depth_reached = max((s["depth"] for s in steps), default=0.0)
    max_end_reached = max((s["end"] for s in steps), default=0.0)
    max_po2_reached = max((s["po2_ata"] for s in steps), default=0.0)
    max_density_reached = max((s["density_g_l"] for s in steps), default=0.0)
    surf_lead = max(final_compartments, key=lambda c: c["surface_gf_pct"])

    return {
        "schedule_mode": schedule_mode,
        "zhl16c_comp1_variant": cfg.zhl16c_comp1_variant,
        "gf_low": cfg.gf_low,
        "gf_high": cfg.gf_high,
        "o2_narcotic": cfg.o2_narcotic,
        "depth_units": cfg.depth_units,
        "volume_units": cfg.volume_units,
        "setpoint_units": cfg.setpoint_units,
        "elevation_ft": cfg.elevation_ft,
        "surface_pressure_bar": round(p_surf, 4),
        "surface_pressure_ata": round(p_surf / P0_BAR, 4),
        "summary": {
            "max_depth": round(max_depth_reached, 1),
            "total_runtime_min": round(runtime_min, 2),
            "total_runtime_mmss": f"{int(round(runtime_min*60))//60:02d}:{int(round(runtime_min*60))%60:02d}",
            "total_deco_min": round(total_deco_min, 2),
            "total_deco_mmss": f"{int(round(total_deco_min*60))//60:02d}:{int(round(total_deco_min*60))%60:02d}",
            "first_stop_depth": round(first_stop_depth, 1),
            "is_deco_dive": first_stop_depth > 0.0,
            "max_po2_ata": round(max_po2_reached, 2),
            "max_end": round(max_end_reached, 1),
            "max_density_g_l": round(max_density_reached, 2),
            "final_cns_pct": round(cns_total, 1),
            "final_otu": round(otu_total, 1),
            "surfacing_leading_compartment": surf_lead["compartment"],
            "surfacing_gf_pct": surf_lead["surface_gf_pct"],
        },
        "steps": steps,
        "profile_points": profile_points,
        "bottom_turn_tissues": bottom_turn_tissues,
        "final_compartments": final_compartments,
        "cylinder_logistics": cylinder_logistics,
        "warnings": list(dict.fromkeys(warnings)),
        "_final_n2_raw": tissues_n2,
        "_final_he_raw": tissues_he,
    }


def plan_dive(
    cfg: DiveConfig,
    auto_best_gas: bool = False,
    initial_n2: Optional[List[float]] = None,
    initial_he: Optional[List[float]] = None,
    initial_cns: float = 0.0,
    initial_otu: float = 0.0,
) -> Dict[str, Any]:
    """Executes Variant 1 / Primary Dive Planning for OC, CCR, and CCR + Bailout."""
    cfg.validate()
    auto_selected_info: Optional[Dict[str, Any]] = None

    if auto_best_gas:
        max_d = max(float(s["depth"]) for s in cfg.segments)
        best = calculate_best_mix_for_depth(
            depth=max_d,
            max_po2_ata=1.40,
            max_end=100.0 if cfg.depth_units == "feet" else 30.0,
            max_density_g_l=5.20,
            o2_narcotic=cfg.o2_narcotic,
            elevation_ft=cfg.elevation_ft,
            depth_units=cfg.depth_units,
            water_type=cfg.water_type,
        )
        auto_selected_info = best
        bottom_mix = GasMix(
            name=best["best_mix_name"],
            f_o2=best["f_o2"],
            f_he=best["f_he"],
            role="bottom",
            max_po2=1.40,
            cylinder_preset="2xLP85" if max_d >= (130.0 if cfg.depth_units == "feet" else 40.0) else "AL80",
            start_pressure_psi=2640.0 if max_d >= (130.0 if cfg.depth_units == "feet" else 40.0) else 3000.0,
        )
        deco_mixes = [
            GasMix(
                name=dg["name"],
                f_o2=dg["f_o2"],
                f_he=dg["f_he"],
                role=dg["role"],
                max_po2=dg["max_po2"],
                switch_depth=dg["switch_depth"],
                cylinder_preset="AL80" if dg["f_o2"] < 0.99 else "AL40",
                start_pressure_psi=3000.0,
            )
            for dg in best["recommended_deco_gases"]
        ]
        if cfg.dive_mode == "OC":
            cfg.oc_gases = [bottom_mix] + deco_mixes
            for s in cfg.segments:
                s["gas_name"] = bottom_mix.name
        else:
            cfg.ccr_diluent = GasMix(
                name=f"Diluent {best['best_mix_name']}",
                f_o2=best["f_o2"],
                f_he=best["f_he"],
                role="diluent",
                max_po2=1.40,
                cylinder_preset="3L_200",
                start_pressure_psi=2900.0,
            )
            cfg.bailout_gases = [bottom_mix] + deco_mixes

    primary = _execute_single_schedule(
        cfg,
        schedule_mode=cfg.dive_mode,
        initial_n2=initial_n2,
        initial_he=initial_he,
        initial_cns=initial_cns,
        initial_otu=initial_otu,
    )

    bailout_plan: Optional[Dict[str, Any]] = None
    if cfg.dive_mode == "CCR" and cfg.include_bailout:
        bailout_plan = _execute_single_schedule(
            cfg,
            schedule_mode="BAILOUT",
            initial_n2=initial_n2,
            initial_he=initial_he,
            initial_cns=initial_cns,
            initial_otu=initial_otu,
        )
        bailout_plan.pop("_final_n2_raw", None)
        bailout_plan.pop("_final_he_raw", None)

    final_n2 = primary.pop("_final_n2_raw", [])
    final_he = primary.pop("_final_he_raw", [])

    return {
        "config": {
            "dive_mode": cfg.dive_mode,
            "include_bailout": cfg.include_bailout,
            "zhl16c_comp1_variant": cfg.zhl16c_comp1_variant,
            "gf_low": cfg.gf_low,
            "gf_high": cfg.gf_high,
            "o2_narcotic": cfg.o2_narcotic,
            "depth_units": cfg.depth_units,
            "volume_units": cfg.volume_units,
            "pressure_units": cfg.pressure_units,
            "setpoint_units": cfg.setpoint_units,
            "elevation_ft": cfg.elevation_ft,
            "water_type": cfg.water_type,
            "stop_size": cfg.stop_size,
            "last_oc_stop": cfg.last_oc_stop,
            "last_ccr_stop": cfg.last_ccr_stop,
            "min_stop_time_sec": cfg.min_stop_time_sec,
            "descent_rate": cfg.descent_rate,
            "ascent_rate": cfg.ascent_rate,
            "deco_ascent_rate": cfg.deco_ascent_rate,
            "surface_ascent_rate": cfg.surface_ascent_rate,
            "bottom_rmv": cfg.bottom_rmv,
            "deco_rmv": cfg.deco_rmv,
            "ccr_setpoint_bottom": cfg.ccr_setpoint_bottom,
            "ccr_setpoint_deco": cfg.ccr_setpoint_deco,
            "segments": cfg.segments,
            "oc_gases": [asdict(g) for g in cfg.oc_gases],
            "ccr_diluent": asdict(cfg.ccr_diluent) if cfg.ccr_diluent else None,
            "bailout_gases": [asdict(g) for g in cfg.bailout_gases],
        },
        "auto_selected_best_gas": auto_selected_info,
        "primary_plan": primary,
        "bailout_plan": bailout_plan,
        "_final_n2_raw": final_n2,
        "_final_he_raw": final_he,
    }


def solve_max_time_at_depth(
    depth: float,
    f_o2: float = 0.32,
    f_he: float = 0.0,
    cylinder_preset: str = "AL80",
    fill_pressure_psi: float = 3000.0,
    reserve_rule: str = "thirds",  # "thirds" | "half" | "all"
    gf_low: float = 30.0,
    gf_high: float = 85.0,
    bottom_rmv: float = 0.75,
    deco_rmv: float = 0.60,
    elevation_ft: float = 0.0,
    depth_units: str = "feet",
    volume_units: str = "cuft",
    comp1_variant: str = "1b",
) -> Dict[str, Any]:
    """Variant 3A: Solves for NDL, Tank-Limited Max Bottom Time, and CNS-Limited Bottom Time at depth."""
    validate_gas_fractions(f_o2, f_he)
    cap = calculate_cylinder_fill_capacity(
        cylinder_preset=cylinder_preset,
        fill_pressure=fill_pressure_psi,
        pressure_units="psi",
        f_o2=f_o2,
        f_he=f_he,
    )
    total_vol = cap["ideal_volume_cuft"] if volume_units == "cuft" else cap["ideal_volume_liters"]
    usable_fraction = 2.0 / 3.0 if reserve_rule == "thirds" else (0.50 if reserve_rule == "half" else 0.90)
    usable_vol = total_vol * usable_fraction

    def eval_bottom_time(t_min: float) -> Tuple[bool, float, float]:
        cfg = DiveConfig(
            dive_mode="OC",
            zhl16c_comp1_variant=comp1_variant,
            gf_low=gf_low,
            gf_high=gf_high,
            depth_units=depth_units,
            volume_units=volume_units,
            elevation_ft=elevation_ft,
            bottom_rmv=bottom_rmv,
            deco_rmv=deco_rmv,
            segments=[{"depth": depth, "time_min": t_min}],
            oc_gases=[
                GasMix(
                    name=format_gas_name(f_o2, f_he),
                    f_o2=f_o2,
                    f_he=f_he,
                    role="bottom",
                    max_po2=1.6,
                    cylinder_preset=cylinder_preset,
                    start_pressure_psi=fill_pressure_psi,
                )
            ],
        )
        res = _execute_single_schedule(cfg, schedule_mode="OC")
        vol_used = sum(c["volume_consumed"] for c in res["cylinder_logistics"])
        return res["summary"]["is_deco_dive"], vol_used, res["summary"]["final_cns_pct"]

    # 1. Binary search for exact No-Decompression Limit (NDL) in [1, 300] minutes
    low_t, high_t = 1.0, 300.0
    ndl_min = 0.0
    for _ in range(18):
        mid = 0.5 * (low_t + high_t)
        is_deco, _, _ = eval_bottom_time(mid)
        if not is_deco:
            ndl_min = mid
            low_t = mid
        else:
            high_t = mid

    # 2. Binary search for Tank-Limited Max Bottom Time (including required deco gas if single tank)
    low_g, high_g = 1.0, 240.0
    max_gas_time = 1.0
    for _ in range(18):
        mid = 0.5 * (low_g + high_g)
        _, vol_u, _ = eval_bottom_time(mid)
        if vol_u <= usable_vol:
            max_gas_time = mid
            low_g = mid
        else:
            high_g = mid

    props = calculate_ead_end_mod_density(
        depth=depth,
        f_o2=f_o2,
        f_he=f_he,
        elevation_ft=elevation_ft,
        depth_units=depth_units,
    )
    t_lim_cns = noaa_t_lim_min(props["po2_at_depth_ata"])

    return {
        "depth": depth,
        "depth_units": depth_units,
        "gas_name": format_gas_name(f_o2, f_he),
        "cylinder_preset": cylinder_preset,
        "total_cylinder_volume": round(total_vol, 1),
        "usable_gas_volume": round(usable_vol, 1),
        "volume_units": volume_units,
        "reserve_rule": reserve_rule,
        "no_decompression_limit_min": round(ndl_min, 1),
        "tank_limited_max_bottom_time_min": round(max_gas_time, 1),
        "cns_100_pct_limit_min": round(t_lim_cns, 1) if t_lim_cns else None,
        "po2_at_depth_ata": props["po2_at_depth_ata"],
        "end_at_depth": props["end"],
        "density_at_depth_g_l": props["density_at_depth_g_l"],
    }


def solve_max_depth_envelope(
    cylinder_preset: str = "AL80",
    fill_pressure_psi: float = 3000.0,
    f_o2: float = 0.32,
    f_he: float = 0.0,
    max_po2_ata: float = 1.40,
    max_end: float = 100.0,
    o2_narcotic: bool = True,
    reserve_rule: str = "thirds",
    min_practical_bottom_time_min: float = 10.0,
    bottom_rmv: float = 0.75,
    deco_rmv: float = 0.60,
    gf_low: float = 30.0,
    gf_high: float = 85.0,
    elevation_ft: float = 0.0,
    depth_units: str = "feet",
    volume_units: str = "cuft",
) -> Dict[str, Any]:
    """Variant 2: Given tank size and gas type, calculates how deep the diver can safely go."""
    validate_gas_fractions(f_o2, f_he)
    props = calculate_ead_end_mod_density(
        depth=100.0 if depth_units == "feet" else 30.0,
        f_o2=f_o2,
        f_he=f_he,
        o2_narcotic=o2_narcotic,
        max_po2_ata=max_po2_ata,
        max_end=max_end,
        elevation_ft=elevation_ft,
        depth_units=depth_units,
    )
    mod_limit = props["mod_working"]
    mnd_limit = props["mnd"]
    mdd_5_2 = props["mdd_5_2_g_l"]
    mdd_6_2 = props["mdd_6_2_g_l"]

    cap = calculate_cylinder_fill_capacity(
        cylinder_preset=cylinder_preset,
        fill_pressure=fill_pressure_psi,
        pressure_units="psi",
        f_o2=f_o2,
        f_he=f_he,
    )
    total_vol = cap["ideal_volume_cuft"] if volume_units == "cuft" else cap["ideal_volume_liters"]
    usable_fraction = 2.0 / 3.0 if reserve_rule == "thirds" else (0.50 if reserve_rule == "half" else 0.90)
    usable_vol = total_vol * usable_fraction

    # Find maximum depth where usable_vol supports at least min_practical_bottom_time_min
    step_d = 10.0 if depth_units == "feet" else 3.0
    max_search_d = min(350.0 if depth_units == "feet" else 105.0, mod_limit + step_d * 2)
    envelope_table: List[Dict[str, Any]] = []
    gas_volume_max_depth = 0.0

    d_cur = step_d * 3
    while d_cur <= max_search_d + 1e-6:
        t_info = solve_max_time_at_depth(
            depth=d_cur,
            f_o2=f_o2,
            f_he=f_he,
            cylinder_preset=cylinder_preset,
            fill_pressure_psi=fill_pressure_psi,
            reserve_rule=reserve_rule,
            gf_low=gf_low,
            gf_high=gf_high,
            bottom_rmv=bottom_rmv,
            deco_rmv=deco_rmv,
            elevation_ft=elevation_ft,
            depth_units=depth_units,
            volume_units=volume_units,
        )
        if t_info["tank_limited_max_bottom_time_min"] >= min_practical_bottom_time_min:
            gas_volume_max_depth = d_cur
        envelope_table.append({
            "depth": round(d_cur, 0),
            "ndl_min": t_info["no_decompression_limit_min"],
            "max_tank_bottom_time_min": t_info["tank_limited_max_bottom_time_min"],
            "po2_ata": t_info["po2_at_depth_ata"],
            "end": t_info["end_at_depth"],
            "density_g_l": t_info["density_at_depth_g_l"],
            "within_mod": d_cur <= mod_limit + 0.5,
            "within_mnd": d_cur <= mnd_limit + 0.5,
            "within_density_5_2": t_info["density_at_depth_g_l"] <= 5.20,
        })
        d_cur += step_d

    ceilings = {
        "MOD_PO2_LIMIT": mod_limit,
        "MND_NARCOSIS_LIMIT": mnd_limit,
        "MDD_DENSITY_5_2_LIMIT": mdd_5_2,
        "TANK_VOLUME_LIMIT": gas_volume_max_depth,
    }
    limiting_factor = min(ceilings, key=lambda k: ceilings[k])
    max_safe_depth = ceilings[limiting_factor]

    return {
        "cylinder_preset": cylinder_preset,
        "cylinder_name": cap["cylinder_name"],
        "fill_pressure_psi": fill_pressure_psi,
        "gas_name": format_gas_name(f_o2, f_he),
        "f_o2": f_o2,
        "f_he": f_he,
        "depth_units": depth_units,
        "volume_units": volume_units,
        "total_volume": round(total_vol, 1),
        "usable_volume": round(usable_vol, 1),
        "reserve_rule": reserve_rule,
        "ceilings": {
            "mod_po2_limit": round(mod_limit, 1),
            "mnd_narcosis_limit": round(mnd_limit, 1),
            "mdd_density_5_2_limit": round(mdd_5_2, 1),
            "mdd_density_6_2_limit": round(mdd_6_2, 1),
            "tank_volume_limit_for_min_time": round(gas_volume_max_depth, 1),
        },
        "max_safe_operating_depth": round(max_safe_depth, 1),
        "limiting_factor": limiting_factor,
        "depth_time_envelope": envelope_table,
    }


def solve_rock_bottom(
    depth: float,
    bottom_time_min: float,
    f_o2: float = 0.21,
    f_he: float = 0.0,
    cylinder_preset: str = "2xLP85",
    fill_pressure_psi: float = 2640.0,
    first_switch_depth: float = 70.0,
    stressed_rmv_per_diver: float = 1.00,
    num_divers_sharing: int = 2,
    problem_solving_time_min: float = 1.0,
    ascent_rate: float = 30.0,
    elevation_ft: float = 0.0,
    depth_units: str = "feet",
    volume_units: str = "cuft",
) -> Dict[str, Any]:
    """Variant 3B: Computes Minimum Gas ('Rock Bottom') and Turn Pressure for team gas sharing."""
    p_surf = surface_pressure_bar(elevation_ft)
    k = get_hydrostatic_gradient_bar(depth_units, water_type="salt")
    p_bottom = p_surf + depth * k
    target_switch = min(depth, max(0.0, first_switch_depth))
    p_switch = p_surf + target_switch * k

    team_rmv = stressed_rmv_per_diver * num_divers_sharing
    vol_problem = team_rmv * (p_bottom / P0_BAR) * problem_solving_time_min
    asc_time = abs(depth - target_switch) / ascent_rate
    p_avg_asc = 0.5 * (p_bottom + p_switch)
    vol_ascent = team_rmv * (p_avg_asc / P0_BAR) * asc_time
    rock_bottom_vol = vol_problem + vol_ascent

    cap = calculate_cylinder_fill_capacity(
        cylinder_preset=cylinder_preset,
        fill_pressure=fill_pressure_psi,
        pressure_units="psi",
        f_o2=f_o2,
        f_he=f_he,
    )
    total_vol = cap["ideal_volume_cuft"] if volume_units == "cuft" else cap["ideal_volume_liters"]
    psi_per_unit = fill_pressure_psi / max(1e-6, total_vol)
    rock_bottom_psi = math.ceil((rock_bottom_vol * psi_per_unit) / 50.0) * 50.0
    thirds_turn_psi = math.ceil((fill_pressure_psi * (2.0 / 3.0)) / 50.0) * 50.0

    return {
        "depth": depth,
        "bottom_time_min": bottom_time_min,
        "depth_units": depth_units,
        "cylinder_preset": cylinder_preset,
        "fill_pressure_psi": fill_pressure_psi,
        "first_gas_switch_depth": target_switch,
        "team_stressed_rmv": round(team_rmv, 2),
        "problem_resolution_volume": round(vol_problem, 1),
        "emergency_ascent_volume": round(vol_ascent, 1),
        "rock_bottom_volume": round(rock_bottom_vol, 1),
        "volume_units": volume_units,
        "rock_bottom_pressure_psi": round(rock_bottom_psi, 0),
        "rock_bottom_pressure_bar": round(rock_bottom_psi / P0_PSI * P0_BAR, 0),
        "rule_of_thirds_turn_pressure_psi": round(thirds_turn_psi, 0),
    }


def solve_what_if_comparison(
    cfg: DiveConfig,
    gf_pairs: Optional[List[Tuple[float, float]]] = None,
    include_lost_gas: bool = True,
) -> Dict[str, Any]:
    """Variant 3C: Runs sensitivity analysis across GF pairs and lost-deco-gas failure modes."""
    if gf_pairs is None:
        gf_pairs = [(20.0, 80.0), (30.0, 70.0), (30.0, 85.0), (40.0, 85.0)]
    scenarios: List[Dict[str, Any]] = []

    for gfl, gfh in gf_pairs:
        c_copy = DiveConfig(**{**asdict(cfg), "gf_low": gfl, "gf_high": gfh})
        c_copy.oc_gases = [GasMix(**asdict(g)) for g in cfg.oc_gases]
        c_copy.bailout_gases = [GasMix(**asdict(g)) for g in cfg.bailout_gases]
        c_copy.ccr_diluent = GasMix(**asdict(cfg.ccr_diluent)) if cfg.ccr_diluent else None
        res = _execute_single_schedule(c_copy, schedule_mode=c_copy.dive_mode)
        s = res["summary"]
        scenarios.append({
            "scenario": f"GF {int(gfl)}/{int(gfh)} (All Gases)",
            "gf_low": gfl,
            "gf_high": gfh,
            "first_stop_depth": s["first_stop_depth"],
            "total_deco_min": s["total_deco_min"],
            "total_runtime_min": s["total_runtime_min"],
            "final_cns_pct": s["final_cns_pct"],
            "final_otu": s["final_otu"],
        })

    if include_lost_gas and cfg.dive_mode == "OC" and len(cfg.oc_gases) > 1:
        deco_only = [g for g in cfg.oc_gases if g.role == "deco"]
        for lost_g in deco_only:
            c_copy = DiveConfig(**asdict(cfg))
            c_copy.oc_gases = [
                GasMix(**{**asdict(g), "enabled": (g.name != lost_g.name)})
                for g in cfg.oc_gases
            ]
            res = _execute_single_schedule(c_copy, schedule_mode="OC")
            s = res["summary"]
            scenarios.append({
                "scenario": f"Lost Deco Gas: {lost_g.name}",
                "gf_low": cfg.gf_low,
                "gf_high": cfg.gf_high,
                "first_stop_depth": s["first_stop_depth"],
                "total_deco_min": s["total_deco_min"],
                "total_runtime_min": s["total_runtime_min"],
                "final_cns_pct": s["final_cns_pct"],
                "final_otu": s["final_otu"],
            })

    return {"scenarios": scenarios}


def solve_repetitive_dive(
    dive1_cfg: DiveConfig,
    surface_interval_min: float,
    dive2_cfg: DiveConfig,
) -> Dict[str, Any]:
    """Variant 3D: Evolves Dive 1 -> Surface Interval (Haldane + 90m CNS decay) -> Dive 2."""
    if surface_interval_min < 0.0:
        raise DivePlannerValidationError("ERR_SI", f"Surface interval must be >= 0, got {surface_interval_min}.")

    res1 = plan_dive(dive1_cfg)
    n2_after_d1 = res1["_final_n2_raw"]
    he_after_d1 = res1["_final_he_raw"]
    cns_after_d1 = res1["primary_plan"]["summary"]["final_cns_pct"]
    otu_after_d1 = res1["primary_plan"]["summary"]["final_otu"]

    p_surf = surface_pressure_bar(dive1_cfg.elevation_ft)
    table = get_zhl16c_table(dive2_cfg.zhl16c_comp1_variant)
    air_surface = GasMix(name="Surface Air", f_o2=AIR_F_O2, f_he=0.0)
    n2_after_si, he_after_si = _evolve_tissues(
        n2_after_d1,
        he_after_d1,
        table,
        p_surf,
        p_surf,
        surface_interval_min,
        air_surface,
        "OC",
        P0_BAR,
    )
    cns_after_si = decay_cns_surface_interval(cns_after_d1, surface_interval_min)

    res2 = plan_dive(
        dive2_cfg,
        initial_n2=n2_after_si,
        initial_he=he_after_si,
        initial_cns=cns_after_si,
        initial_otu=otu_after_d1,
    )
    res1.pop("_final_n2_raw", None)
    res1.pop("_final_he_raw", None)
    res2.pop("_final_n2_raw", None)
    res2.pop("_final_he_raw", None)

    return {
        "surface_interval_min": surface_interval_min,
        "cns_before_si_pct": cns_after_d1,
        "cns_after_si_pct": round(cns_after_si, 1),
        "dive_1": res1["primary_plan"]["summary"],
        "dive_2": res2["primary_plan"]["summary"],
        "dive_2_full_plan": res2["primary_plan"],
    }


def solve_ccr_bailout_sizing(
    depth: float,
    bottom_time_min: float,
    diluent_f_o2: float = 0.13,
    diluent_f_he: float = 0.54,
    setpoint_bottom_ata: float = 1.20,
    setpoint_deco_ata: float = 1.30,
    bailout_bottom_rmv: float = 0.90,
    bailout_deco_rmv: float = 0.70,
    gf_low: float = 30.0,
    gf_high: float = 85.0,
    elevation_ft: float = 0.0,
    depth_units: str = "feet",
    volume_units: str = "cuft",
) -> Dict[str, Any]:
    """Variant 3E: Computes CCR loop failure bailout schedule and recommends stage cylinders."""
    best = calculate_best_mix_for_depth(
        depth=depth,
        max_po2_ata=1.40,
        max_end=100.0 if depth_units == "feet" else 30.0,
        elevation_ft=elevation_ft,
        depth_units=depth_units,
    )
    bailout_gases = [
        GasMix(
            name=f"Bailout {format_gas_name(diluent_f_o2, diluent_f_he)}",
            f_o2=diluent_f_o2,
            f_he=diluent_f_he,
            role="bailout",
            max_po2=1.40,
            switch_depth=depth,
            cylinder_preset="AL80",
            start_pressure_psi=3000.0,
        ),
        GasMix(
            name="Bailout EAN50",
            f_o2=0.50,
            f_he=0.0,
            role="bailout",
            max_po2=1.60,
            switch_depth=70.0 if depth_units == "feet" else 21.0,
            cylinder_preset="AL80",
            start_pressure_psi=3000.0,
        ),
        GasMix(
            name="Bailout O2 100%",
            f_o2=1.00,
            f_he=0.0,
            role="bailout",
            max_po2=1.60,
            switch_depth=20.0 if depth_units == "feet" else 6.0,
            cylinder_preset="AL40",
            start_pressure_psi=3000.0,
        ),
    ]
    cfg = DiveConfig(
        dive_mode="CCR",
        include_bailout=True,
        gf_low=gf_low,
        gf_high=gf_high,
        depth_units=depth_units,
        volume_units=volume_units,
        elevation_ft=elevation_ft,
        bottom_rmv=bailout_bottom_rmv,
        deco_rmv=bailout_deco_rmv,
        ccr_setpoint_bottom=setpoint_bottom_ata,
        ccr_setpoint_deco=setpoint_deco_ata,
        segments=[{"depth": depth, "time_min": bottom_time_min}],
        ccr_diluent=GasMix(
            name=f"Diluent {format_gas_name(diluent_f_o2, diluent_f_he)}",
            f_o2=diluent_f_o2,
            f_he=diluent_f_he,
            role="diluent",
        ),
        bailout_gases=bailout_gases,
    )
    res = plan_dive(cfg)
    bo = res["bailout_plan"]
    stage_recommendations: List[Dict[str, Any]] = []
    for cyl in bo["cylinder_logistics"]:
        vol_req = cyl["volume_consumed"] * 1.25  # 25% safety margin for bailout stage sizing
        rec_cyl = "AL40" if vol_req <= (38.0 if volume_units == "cuft" else 1050.0) else (
            "AL80" if vol_req <= (77.0 if volume_units == "cuft" else 2150.0) else "2xAL80 (Two Stages)"
        )
        stage_recommendations.append({
            "gas_name": cyl["gas_name"],
            "volume_consumed": cyl["volume_consumed"],
            "volume_with_25pct_margin": round(vol_req, 1),
            "volume_units": volume_units,
            "recommended_stage_cylinder": rec_cyl,
            "single_cylinder_status": cyl["status"],
        })
    return {
        "depth": depth,
        "bottom_time_min": bottom_time_min,
        "depth_units": depth_units,
        "ccr_primary_summary": res["primary_plan"]["summary"],
        "bailout_summary": bo["summary"],
        "stage_cylinder_recommendations": stage_recommendations,
        "recommended_diluent_for_depth": best["best_mix_name"],
    }


def config_from_dict(data: Dict[str, Any]) -> DiveConfig:
    """Constructs a validated DiveConfig instance from a raw dictionary."""
    oc_gases = [GasMix(**g) for g in data.get("oc_gases", [])]
    bailout_gases = [GasMix(**g) for g in data.get("bailout_gases", [])]
    dil_raw = data.get("ccr_diluent")
    ccr_dil = GasMix(**dil_raw) if isinstance(dil_raw, dict) else None
    allowed_keys = {
        "dive_mode", "include_bailout", "zhl16c_comp1_variant", "gf_low", "gf_high",
        "o2_narcotic", "depth_units", "volume_units", "pressure_units", "setpoint_units",
        "elevation_ft", "water_type", "stop_size", "last_oc_stop", "last_ccr_stop",
        "min_stop_time_sec", "descent_rate", "ascent_rate", "deco_ascent_rate",
        "surface_ascent_rate", "bottom_rmv", "deco_rmv", "ccr_setpoint_bottom",
        "ccr_setpoint_deco", "segments",
    }
    kwargs = {k: v for k, v in data.items() if k in allowed_keys}
    kwargs["oc_gases"] = oc_gases
    kwargs["bailout_gases"] = bailout_gases
    kwargs["ccr_diluent"] = ccr_dil
    return DiveConfig(**kwargs)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILES_PATH = PROJECT_ROOT / "assets" / "synthetic_dive_profiles.json"


def _to_relative_path_str(p: Path) -> str:
    """Formats a path relative to PROJECT_ROOT when inside the repository."""
    try:
        return p.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return p.name


def _rebuild_dashboard_if_present() -> bool:
    """Regenerates dashboard.html when the default profile store is updated."""
    try:
        from scripts import build_dashboard
        build_dashboard.main()
        return True
    except Exception:
        return False


def list_saved_profiles(profiles_file: Optional[Path] = None) -> Dict[str, Any]:
    """Lists all saved dive profiles in the JSON profile store."""
    target_path = profiles_file or DEFAULT_PROFILES_PATH
    rel_str = _to_relative_path_str(target_path)
    if not target_path.exists():
        return {"profiles_file": rel_str, "count": 0, "profiles": []}
    raw = json.loads(target_path.read_text(encoding="utf-8"))
    summary_list: List[Dict[str, Any]] = []
    for item in raw.get("profiles", []):
        cfg = item.get("config", {})
        segs = cfg.get("segments", [{"depth": 0, "time_min": 0}])
        summary_list.append({
            "profile_id": item.get("profile_id", ""),
            "title": item.get("title", ""),
            "scenario_type": item.get("scenario_type", item.get("description", "Custom Dive Profile")),
            "dive_mode": cfg.get("dive_mode", "OC"),
            "depth": segs[0].get("depth", 0),
            "time_min": segs[0].get("time_min", 0),
            "depth_units": cfg.get("depth_units", "feet"),
            "gf_low": cfg.get("gf_low", 30),
            "gf_high": cfg.get("gf_high", 85),
        })
    return {
        "profiles_file": rel_str,
        "count": len(summary_list),
        "profiles": summary_list,
    }


def save_profile_to_store(
    profile_id: str,
    cfg_dict: Dict[str, Any],
    title: Optional[str] = None,
    scenario_type: str = "User Saved Dive Profile",
    profiles_file: Optional[Path] = None,
    rebuild_dashboard: bool = True,
) -> Dict[str, Any]:
    """Creates or updates a dive profile in the JSON profile store and refreshes dashboard.html."""
    clean_id = profile_id.strip()
    if not clean_id:
        raise DivePlannerValidationError("ERR_PROFILE_ID", "profile_id cannot be empty.")

    target_path = profiles_file or DEFAULT_PROFILES_PATH
    if target_path.exists():
        raw = json.loads(target_path.read_text(encoding="utf-8"))
    else:
        raw = {
            "dataset_name": "technical_dive_profiles_v2",
            "description": "Technical scuba diving profile library.",
            "profiles": [],
        }

    segs = cfg_dict.get("segments", [{"depth": 150.0, "time_min": 25.0}])
    d_val = segs[0].get("depth", 150.0)
    t_val = segs[0].get("time_min", 25.0)
    d_unit = "ft" if cfg_dict.get("depth_units", "feet") == "feet" else "m"
    mode_str = cfg_dict.get("dive_mode", "OC")
    gfl = int(cfg_dict.get("gf_low", 30))
    gfh = int(cfg_dict.get("gf_high", 85))
    oc_g = cfg_dict.get("oc_gases", [])
    primary_gas_name = (
        cfg_dict.get("ccr_diluent", {}).get("name", "CCR")
        if mode_str == "CCR" and cfg_dict.get("ccr_diluent")
        else (oc_g[0].get("name", "Mix") if oc_g else "Mix")
    )
    resolved_title = (
        title.strip()
        if title and title.strip()
        else f"{mode_str} {primary_gas_name} - {d_val:.0f} {d_unit} for {t_val:.0f} min (GF {gfl}/{gfh})"
    )

    new_entry = {
        "profile_id": clean_id,
        "title": resolved_title,
        "scenario_type": scenario_type,
        "config": cfg_dict,
    }

    profiles_list = raw.get("profiles", [])
    updated = False
    for idx, existing in enumerate(profiles_list):
        if existing.get("profile_id") == clean_id:
            profiles_list[idx] = new_entry
            updated = True
            break
    if not updated:
        profiles_list.append(new_entry)
    raw["profiles"] = profiles_list

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

    dash_rebuilt = False
    if rebuild_dashboard and target_path.resolve() == DEFAULT_PROFILES_PATH.resolve():
        dash_rebuilt = _rebuild_dashboard_if_present()

    return {
        "action": "updated" if updated else "created",
        "profile_id": clean_id,
        "title": resolved_title,
        "profiles_file": _to_relative_path_str(target_path),
        "total_profiles": len(profiles_list),
        "dashboard_updated": dash_rebuilt,
    }


def delete_profile_from_store(
    profile_id: str,
    profiles_file: Optional[Path] = None,
    rebuild_dashboard: bool = True,
) -> Dict[str, Any]:
    """Deletes a profile by profile_id from the JSON profile store and refreshes dashboard.html."""
    target_path = profiles_file or DEFAULT_PROFILES_PATH
    rel_str = _to_relative_path_str(target_path)
    if not target_path.exists():
        raise DivePlannerValidationError("ERR_FILE_NOT_FOUND", f"Profiles file not found: {rel_str}")
    raw = json.loads(target_path.read_text(encoding="utf-8"))
    before = len(raw.get("profiles", []))
    remaining = [p for p in raw.get("profiles", []) if p.get("profile_id") != profile_id]
    if len(remaining) == before:
        raise DivePlannerValidationError("ERR_PROFILE_ID", f"Profile ID '{profile_id}' not found in {rel_str}.")
    raw["profiles"] = remaining
    target_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

    dash_rebuilt = False
    if rebuild_dashboard and target_path.resolve() == DEFAULT_PROFILES_PATH.resolve():
        dash_rebuilt = _rebuild_dashboard_if_present()

    return {
        "action": "deleted",
        "profile_id": profile_id,
        "profiles_file": rel_str,
        "total_profiles": len(remaining),
        "dashboard_updated": dash_rebuilt,
    }


# ---------------------------------------------------------------------------
# CLI Formatting and Entry Point
# ---------------------------------------------------------------------------
def _print_plan_table(result: Dict[str, Any]) -> None:
    plan = result["primary_plan"]
    s = plan["summary"]
    d_u = plan["depth_units"]
    v_u = plan["volume_units"]
    print("=" * 96)
    print(
        f"ZHL-16C ({plan['zhl16c_comp1_variant']}) + GF {int(plan['gf_low'])}/{int(plan['gf_high'])} "
        f"DIVE PLAN | MODE: {plan['schedule_mode']} | ELEVATION: {plan['elevation_ft']:.0f} ft "
        f"({plan['surface_pressure_bar']:.3f} bar)"
    )
    print("=" * 96)
    if result.get("auto_selected_best_gas"):
        bg = result["auto_selected_best_gas"]
        print(
            f"AUTO-SELECTED BEST BOTTOM MIX: {bg['best_mix_name']} "
            f"(O2={bg['f_o2']*100:.0f}%, He={bg['f_he']*100:.0f}%, N2={bg['f_n2']*100:.0f}%)"
        )
    print(
        f"Max Depth: {s['max_depth']} {d_u} | Runtime (TTS): {s['total_runtime_mmss']} | "
        f"Total Deco: {s['total_deco_mmss']} | First Stop: {s['first_stop_depth']} {d_u}"
    )
    print(
        f"Max PO2: {s['max_po2_ata']:.2f} ATA | Max END: {s['max_end']} {d_u} | "
        f"Max Density: {s['max_density_g_l']:.2f} g/L | CNS: {s['final_cns_pct']:.1f}% | OTU: {s['final_otu']:.1f}"
    )
    print("-" * 96)
    print(
        f"{'PHASE':<16} {'DEPTH':>8} {'TIME':>7} {'RUNTIME':>8} {'GAS MIX':<20} "
        f"{'PO2':>5} {'END':>6} {'DENS':>6} {'CNS%':>6} {'VOL':>7}"
    )
    print("-" * 96)
    for st in plan["steps"]:
        print(
            f"{st['phase']:<16} {st['depth']:>6.0f}{d_u[0]} {st['duration_mmss']:>7} "
            f"{st['runtime_mmss']:>8} {st['gas_name']:<20} {st['po2_ata']:>5.2f} "
            f"{st['end']:>6.0f} {st['density_g_l']:>6.2f} {st['cns_pct']:>5.1f}% "
            f"{st['gas_volume_used']:>6.1f}{v_u[0]}"
        )
    print("-" * 96)
    if plan["warnings"]:
        print("ALERTS / WARNINGS:")
        for w in plan["warnings"]:
            print(f"  * {w}")
        print("-" * 96)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zhl16c_planner",
        description="Deterministic Bühlmann ZH-L16C + Gradient Factors Dive Planner and Diver Utility CLI.",
    )
    parser.add_argument("--json", action="store_true", help="Emit structured JSON output.")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # 1. plan
    p_plan = sub.add_parser("plan", help="Calculate OC, CCR, or CCR+Bailout decompression dive plan.")
    p_plan.add_argument("--input-file", type=str, help="Path to JSON dive configuration file.")
    p_plan.add_argument("--profile-id", type=str, help="Profile ID if loading from synthetic_dive_profiles.json.")
    p_plan.add_argument("--mode", choices=["OC", "CCR"], default="OC")
    p_plan.add_argument("--depth", type=float, default=150.0)
    p_plan.add_argument("--time", type=float, default=25.0)
    p_plan.add_argument("--f-o2", type=float, default=0.21)
    p_plan.add_argument("--f-he", type=float, default=0.0)
    p_plan.add_argument("--deco-gases", type=str, default="EAN50:0.50:0.0:70,O2 100%:1.00:0.0:20", help="Comma-separated name:f_o2:f_he:switch_depth")
    p_plan.add_argument("--gf-low", type=float, default=30.0)
    p_plan.add_argument("--gf-high", type=float, default=85.0)
    p_plan.add_argument("--comp1", choices=["1b", "1"], default="1b")
    p_plan.add_argument("--o2-narcotic", type=str, choices=["true", "false"], default="true")
    p_plan.add_argument("--depth-units", choices=["feet", "meters"], default="feet")
    p_plan.add_argument("--volume-units", choices=["cuft", "liters"], default="cuft")
    p_plan.add_argument("--setpoint-units", choices=["ATA", "BAR"], default="ATA")
    p_plan.add_argument("--setpoint-bottom", type=float, default=1.20)
    p_plan.add_argument("--setpoint-deco", type=float, default=1.30)
    p_plan.add_argument("--stop-size", type=float, default=10.0)
    p_plan.add_argument("--last-oc-stop", type=float, default=10.0)
    p_plan.add_argument("--last-ccr-stop", type=float, default=10.0)
    p_plan.add_argument("--min-stop-sec", type=int, default=60)
    p_plan.add_argument("--descent-rate", type=float, default=60.0)
    p_plan.add_argument("--ascent-rate", type=float, default=30.0)
    p_plan.add_argument("--deco-ascent-rate", type=float, default=30.0)
    p_plan.add_argument("--surface-ascent-rate", type=float, default=10.0)
    p_plan.add_argument("--bottom-rmv", type=float, default=0.75)
    p_plan.add_argument("--deco-rmv", type=float, default=0.60)
    p_plan.add_argument("--elevation-ft", type=float, default=0.0)
    p_plan.add_argument("--auto-best-gas", action="store_true", help="Variant 1: Automatically compute best bottom and deco gases.")
    p_plan.add_argument("--save-profile-id", type=str, help="Save or update this planned dive configuration under the given profile ID.")
    p_plan.add_argument("--save-profile-title", type=str, help="Optional display title when saving the profile for the UI dropdown selector.")
    p_plan.add_argument("--profiles-file", type=str, help="Optional custom JSON file path for reading/saving profiles (default: assets/synthetic_dive_profiles.json).")

    # 2. max-depth
    p_md = sub.add_parser("max-depth", help="Variant 2: Given tank size and gas mix, calculate maximum safe depth and time envelope.")
    p_md.add_argument("--cylinder", type=str, default="AL80")
    p_md.add_argument("--fill-psi", type=float, default=3000.0)
    p_md.add_argument("--f-o2", type=float, default=0.32)
    p_md.add_argument("--f-he", type=float, default=0.0)
    p_md.add_argument("--max-po2", type=float, default=1.40)
    p_md.add_argument("--max-end", type=float, default=100.0)
    p_md.add_argument("--reserve-rule", choices=["thirds", "half", "all"], default="thirds")
    p_md.add_argument("--depth-units", choices=["feet", "meters"], default="feet")
    p_md.add_argument("--volume-units", choices=["cuft", "liters"], default="cuft")

    # 3. max-time
    p_mt = sub.add_parser("max-time", help="Variant 3A: Solve for NDL, tank-limited bottom time, and CNS limit at depth.")
    p_mt.add_argument("--depth", type=float, required=True)
    p_mt.add_argument("--f-o2", type=float, default=0.32)
    p_mt.add_argument("--f-he", type=float, default=0.0)
    p_mt.add_argument("--cylinder", type=str, default="AL80")
    p_mt.add_argument("--fill-psi", type=float, default=3000.0)
    p_mt.add_argument("--depth-units", choices=["feet", "meters"], default="feet")

    # 4. rock-bottom
    p_rb = sub.add_parser("rock-bottom", help="Variant 3B: Calculate minimum reserve gas ('rock bottom') and turn pressure.")
    p_rb.add_argument("--depth", type=float, required=True)
    p_rb.add_argument("--time", type=float, default=25.0)
    p_rb.add_argument("--cylinder", type=str, default="2xLP85")
    p_rb.add_argument("--fill-psi", type=float, default=2640.0)
    p_rb.add_argument("--switch-depth", type=float, default=70.0)
    p_rb.add_argument("--stressed-rmv", type=float, default=1.00)

    # 5. what-if
    p_wi = sub.add_parser("what-if", help="Variant 3C: Compare GF pairs and lost-deco-gas scenarios.")
    p_wi.add_argument("--depth", type=float, default=180.0)
    p_wi.add_argument("--time", type=float, default=25.0)
    p_wi.add_argument("--f-o2", type=float, default=0.18)
    p_wi.add_argument("--f-he", type=float, default=0.45)

    # 6. repetitive
    p_rep = sub.add_parser("repetitive", help="Variant 3D: Chain Dive 1 -> Surface Interval -> Dive 2.")
    p_rep.add_argument("--d1-depth", type=float, default=130.0)
    p_rep.add_argument("--d1-time", type=float, default=25.0)
    p_rep.add_argument("--surface-interval", type=float, default=90.0)
    p_rep.add_argument("--d2-depth", type=float, default=100.0)
    p_rep.add_argument("--d2-time", type=float, default=25.0)
    p_rep.add_argument("--f-o2", type=float, default=0.32)

    # 6b. bailout-sizing
    p_bs = sub.add_parser("bailout-sizing", help="Variant 3E: Calculate CCR loop failure bailout schedule and stage cylinder sizing.")
    p_bs.add_argument("--depth", type=float, required=True)
    p_bs.add_argument("--time", type=float, required=True)
    p_bs.add_argument("--f-o2", type=float, default=0.13)
    p_bs.add_argument("--f-he", type=float, default=0.54)
    p_bs.add_argument("--setpoint-bottom", type=float, default=1.20)
    p_bs.add_argument("--setpoint-deco", type=float, default=1.30)
    p_bs.add_argument("--bailout-rmv", type=float, default=0.90)
    p_bs.add_argument("--depth-units", choices=["feet", "meters"], default="feet")
    p_bs.add_argument("--volume-units", choices=["cuft", "liters"], default="cuft")

    # 7. best-mix
    p_bm = sub.add_parser("best-mix", help="Tool 2: Calculate Best Nitrox, Best Trimix, and Agency Match for depth.")
    p_bm.add_argument("--depth", type=float, required=True)
    p_bm.add_argument("--max-po2", type=float, default=1.40)
    p_bm.add_argument("--max-end", type=float, default=100.0)
    p_bm.add_argument("--max-density", type=float, default=5.20)
    p_bm.add_argument("--o2-narcotic", choices=["true", "false"], default="true")
    p_bm.add_argument("--elevation-ft", type=float, default=0.0)
    p_bm.add_argument("--depth-units", choices=["feet", "meters"], default="feet")

    # 8. gas-tools
    p_gt = sub.add_parser("gas-tools", help="Tool 1 & Tool 4: Calculate EAD, END, MOD, MinOD, MND, Gas Density, and MDD.")
    p_gt.add_argument("--depth", type=float, required=True)
    p_gt.add_argument("--f-o2", type=float, required=True)
    p_gt.add_argument("--f-he", type=float, default=0.0)
    p_gt.add_argument("--o2-narcotic", choices=["true", "false"], default="true")
    p_gt.add_argument("--max-po2", type=float, default=1.40)
    p_gt.add_argument("--max-end", type=float, default=100.0)
    p_gt.add_argument("--elevation-ft", type=float, default=0.0)
    p_gt.add_argument("--depth-units", choices=["feet", "meters"], default="feet")

    # 9. blend
    p_bl = sub.add_parser("blend", help="Tool 3: Calculate Nitrox/Trimix partial-pressure blending, top-up, and fill capacity.")
    p_bl.add_argument("--mode", choices=["partial_pressure", "topup_result"], default="partial_pressure")
    p_bl.add_argument("--start-pressure", type=float, default=0.0)
    p_bl.add_argument("--start-f-o2", type=float, default=0.21)
    p_bl.add_argument("--start-f-he", type=float, default=0.0)
    p_bl.add_argument("--target-pressure", type=float, default=3000.0)
    p_bl.add_argument("--target-f-o2", type=float, default=0.18)
    p_bl.add_argument("--target-f-he", type=float, default=0.45)
    p_bl.add_argument("--topup-f-o2", type=float, default=0.21)
    p_bl.add_argument("--topup-f-he", type=float, default=0.0)
    p_bl.add_argument("--pressure-units", choices=["psi", "bar"], default="psi")
    p_bl.add_argument("--cylinder", type=str, default="2xLP85")

    # 10. profiles (Manage UI Dropdown Profiles via CLI)
    p_prof = sub.add_parser("profiles", help="List, save, or delete saved dive profiles for the UI dropdown selector.")
    p_prof.add_argument("--action", choices=["list", "save", "delete"], default="list")
    p_prof.add_argument("--profile-id", type=str, help="Unique profile identifier (required for save and delete).")
    p_prof.add_argument("--title", type=str, help="Display title in the UI dropdown selector.")
    p_prof.add_argument("--profiles-file", type=str, help="Optional custom JSON file path (default: assets/synthetic_dive_profiles.json).")
    p_prof.add_argument("--mode", choices=["OC", "CCR"], default="OC")
    p_prof.add_argument("--depth", type=float, default=150.0)
    p_prof.add_argument("--time", type=float, default=25.0)
    p_prof.add_argument("--f-o2", type=float, default=0.21)
    p_prof.add_argument("--f-he", type=float, default=0.0)
    p_prof.add_argument("--deco-gases", type=str, default="EAN50:0.50:0.0:70,O2 100%:1.00:0.0:20")
    p_prof.add_argument("--gf-low", type=float, default=30.0)
    p_prof.add_argument("--gf-high", type=float, default=85.0)
    p_prof.add_argument("--comp1", choices=["1b", "1"], default="1b")
    p_prof.add_argument("--o2-narcotic", type=str, choices=["true", "false"], default="true")
    p_prof.add_argument("--depth-units", choices=["feet", "meters"], default="feet")
    p_prof.add_argument("--volume-units", choices=["cuft", "liters"], default="cuft")
    p_prof.add_argument("--setpoint-units", choices=["ATA", "BAR"], default="ATA")
    p_prof.add_argument("--setpoint-bottom", type=float, default=1.20)
    p_prof.add_argument("--setpoint-deco", type=float, default=1.30)
    p_prof.add_argument("--stop-size", type=float, default=10.0)
    p_prof.add_argument("--last-oc-stop", type=float, default=10.0)
    p_prof.add_argument("--last-ccr-stop", type=float, default=10.0)
    p_prof.add_argument("--min-stop-sec", type=int, default=60)
    p_prof.add_argument("--descent-rate", type=float, default=60.0)
    p_prof.add_argument("--ascent-rate", type=float, default=30.0)
    p_prof.add_argument("--deco-ascent-rate", type=float, default=30.0)
    p_prof.add_argument("--surface-ascent-rate", type=float, default=10.0)
    p_prof.add_argument("--bottom-rmv", type=float, default=0.75)
    p_prof.add_argument("--deco-rmv", type=float, default=0.60)
    p_prof.add_argument("--elevation-ft", type=float, default=0.0)
    p_prof.add_argument("--auto-best-gas", action="store_true", help="Automatically select optimal bottom and deco gases before saving.")

    return parser


def _build_dive_config_from_cli_args(args: argparse.Namespace) -> DiveConfig:
    """Constructs a DiveConfig from CLI flags shared by 'plan' and 'profiles --action save'."""
    deco_list: List[GasMix] = [
        GasMix(
            name=format_gas_name(args.f_o2, args.f_he),
            f_o2=args.f_o2,
            f_he=args.f_he,
            role="bottom",
            max_po2=1.40,
            cylinder_preset="2xLP85",
            start_pressure_psi=2640.0,
        )
    ]
    if args.deco_gases:
        for item in args.deco_gases.split(","):
            parts = item.strip().split(":")
            if len(parts) >= 4:
                deco_list.append(
                    GasMix(
                        name=parts[0],
                        f_o2=float(parts[1]),
                        f_he=float(parts[2]),
                        role="deco",
                        max_po2=1.60,
                        switch_depth=float(parts[3]),
                        cylinder_preset="AL80" if float(parts[1]) < 0.99 else "AL40",
                    )
                )
    return DiveConfig(
        dive_mode=args.mode,
        zhl16c_comp1_variant=args.comp1,
        gf_low=args.gf_low,
        gf_high=args.gf_high,
        o2_narcotic=(args.o2_narcotic == "true"),
        depth_units=args.depth_units,
        volume_units=args.volume_units,
        setpoint_units=args.setpoint_units,
        ccr_setpoint_bottom=args.setpoint_bottom,
        ccr_setpoint_deco=args.setpoint_deco,
        stop_size=args.stop_size,
        last_oc_stop=args.last_oc_stop,
        last_ccr_stop=args.last_ccr_stop,
        min_stop_time_sec=args.min_stop_sec,
        descent_rate=args.descent_rate,
        ascent_rate=args.ascent_rate,
        deco_ascent_rate=args.deco_ascent_rate,
        surface_ascent_rate=args.surface_ascent_rate,
        bottom_rmv=args.bottom_rmv,
        deco_rmv=args.deco_rmv,
        elevation_ft=args.elevation_ft,
        segments=[{"depth": args.depth, "time_min": args.time}],
        oc_gases=deco_list,
        ccr_diluent=GasMix(name=format_gas_name(args.f_o2, args.f_he), f_o2=args.f_o2, f_he=args.f_he, role="diluent"),
        bailout_gases=deco_list,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        if args.subcommand == "plan":
            prof_store_path = Path(args.profiles_file) if args.profiles_file else DEFAULT_PROFILES_PATH
            if args.input_file or args.profile_id:
                in_path = Path(args.input_file) if args.input_file else prof_store_path
                if not in_path.exists():
                    raise DivePlannerValidationError("ERR_FILE_NOT_FOUND", f"Input file not found: {in_path}")
                try:
                    raw = json.loads(in_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    print(f"[ERR_MALFORMED_JSON] Failed to parse JSON from {in_path}: {exc}", file=sys.stderr)
                    return 3
                if "profiles" in raw and args.profile_id:
                    matched = [p["config"] for p in raw["profiles"] if p["profile_id"] == args.profile_id]
                    if not matched:
                        raise DivePlannerValidationError("ERR_PROFILE_ID", f"Profile ID '{args.profile_id}' not found.")
                    cfg = config_from_dict(matched[0])
                elif "config" in raw:
                    cfg = config_from_dict(raw["config"])
                else:
                    cfg = config_from_dict(raw)
                res = plan_dive(cfg, auto_best_gas=args.auto_best_gas)
            else:
                cfg = _build_dive_config_from_cli_args(args)
                res = plan_dive(cfg, auto_best_gas=args.auto_best_gas)

            if args.save_profile_id:
                saved_meta = save_profile_to_store(
                    profile_id=args.save_profile_id,
                    cfg_dict=res["config"],
                    title=args.save_profile_title,
                    profiles_file=prof_store_path,
                )
                res["saved_profile"] = saved_meta

            res.pop("_final_n2_raw", None)
            res.pop("_final_he_raw", None)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                _print_plan_table(res)
                if args.save_profile_id and "saved_profile" in res:
                    sp = res["saved_profile"]
                    print(f"SAVED PROFILE [{sp['profile_id']}]: '{sp['title']}' -> {sp['profiles_file']}")
            return 0

        if args.subcommand == "profiles":
            prof_store_path = Path(args.profiles_file) if args.profiles_file else DEFAULT_PROFILES_PATH
            if args.action == "list":
                out = list_saved_profiles(prof_store_path)
                print(json.dumps(out, indent=2))
                return 0
            if args.action == "save":
                if not args.profile_id:
                    raise DivePlannerValidationError("ERR_PROFILE_ID", "--profile-id is required for 'profiles --action save'.")
                cfg = _build_dive_config_from_cli_args(args)
                res = plan_dive(cfg, auto_best_gas=args.auto_best_gas)
                out = save_profile_to_store(
                    profile_id=args.profile_id,
                    cfg_dict=res["config"],
                    title=args.title,
                    profiles_file=prof_store_path,
                )
                print(json.dumps(out, indent=2))
                return 0
            if args.action == "delete":
                if not args.profile_id:
                    raise DivePlannerValidationError("ERR_PROFILE_ID", "--profile-id is required for 'profiles --action delete'.")
                out = delete_profile_from_store(
                    profile_id=args.profile_id,
                    profiles_file=prof_store_path,
                )
                print(json.dumps(out, indent=2))
                return 0

        if args.subcommand == "max-depth":
            out = solve_max_depth_envelope(
                cylinder_preset=args.cylinder,
                fill_pressure_psi=args.fill_psi,
                f_o2=args.f_o2,
                f_he=args.f_he,
                max_po2_ata=args.max_po2,
                max_end=args.max_end,
                reserve_rule=args.reserve_rule,
                depth_units=args.depth_units,
                volume_units=args.volume_units,
            )
            print(json.dumps(out, indent=2))
            return 0

        if args.subcommand == "max-time":
            out = solve_max_time_at_depth(
                depth=args.depth,
                f_o2=args.f_o2,
                f_he=args.f_he,
                cylinder_preset=args.cylinder,
                fill_pressure_psi=args.fill_psi,
                depth_units=args.depth_units,
            )
            print(json.dumps(out, indent=2))
            return 0

        if args.subcommand == "rock-bottom":
            out = solve_rock_bottom(
                depth=args.depth,
                bottom_time_min=args.time,
                cylinder_preset=args.cylinder,
                fill_pressure_psi=args.fill_psi,
                first_switch_depth=args.switch_depth,
                stressed_rmv_per_diver=args.stressed_rmv,
            )
            print(json.dumps(out, indent=2))
            return 0

        if args.subcommand == "what-if":
            cfg = DiveConfig(
                segments=[{"depth": args.depth, "time_min": args.time}],
                oc_gases=[
                    GasMix(name=format_gas_name(args.f_o2, args.f_he), f_o2=args.f_o2, f_he=args.f_he, role="bottom"),
                    GasMix(name="EAN50", f_o2=0.50, f_he=0.0, role="deco", max_po2=1.6, switch_depth=70.0),
                    GasMix(name="O2 100%", f_o2=1.00, f_he=0.0, role="deco", max_po2=1.6, switch_depth=20.0),
                ],
            )
            out = solve_what_if_comparison(cfg)
            print(json.dumps(out, indent=2))
            return 0

        if args.subcommand == "repetitive":
            d1 = DiveConfig(
                segments=[{"depth": args.d1_depth, "time_min": args.d1_time}],
                oc_gases=[GasMix(name=format_gas_name(args.f_o2, 0.0), f_o2=args.f_o2, f_he=0.0, role="bottom")],
            )
            d2 = DiveConfig(
                segments=[{"depth": args.d2_depth, "time_min": args.d2_time}],
                oc_gases=[GasMix(name=format_gas_name(args.f_o2, 0.0), f_o2=args.f_o2, f_he=0.0, role="bottom")],
            )
            out = solve_repetitive_dive(d1, args.surface_interval, d2)
            print(json.dumps(out, indent=2))
            return 0

        if args.subcommand == "bailout-sizing":
            out = solve_ccr_bailout_sizing(
                depth=args.depth,
                bottom_time_min=args.time,
                diluent_f_o2=args.f_o2,
                diluent_f_he=args.f_he,
                setpoint_bottom_ata=args.setpoint_bottom,
                setpoint_deco_ata=args.setpoint_deco,
                bailout_bottom_rmv=args.bailout_rmv,
                depth_units=args.depth_units,
                volume_units=args.volume_units,
            )
            print(json.dumps(out, indent=2))
            return 0

        if args.subcommand == "best-mix":
            out = calculate_best_mix_for_depth(
                depth=args.depth,
                max_po2_ata=args.max_po2,
                max_end=args.max_end,
                max_density_g_l=args.max_density,
                o2_narcotic=(args.o2_narcotic == "true"),
                elevation_ft=args.elevation_ft,
                depth_units=args.depth_units,
            )
            print(json.dumps(out, indent=2))
            return 0

        if args.subcommand == "gas-tools":
            out = calculate_ead_end_mod_density(
                depth=args.depth,
                f_o2=args.f_o2,
                f_he=args.f_he,
                o2_narcotic=(args.o2_narcotic == "true"),
                max_po2_ata=args.max_po2,
                max_end=args.max_end,
                elevation_ft=args.elevation_ft,
                depth_units=args.depth_units,
            )
            print(json.dumps(out, indent=2))
            return 0

        if args.subcommand == "blend":
            out = calculate_gas_blender(
                mode=args.mode,
                start_pressure=args.start_pressure,
                start_f_o2=args.start_f_o2,
                start_f_he=args.start_f_he,
                target_pressure=args.target_pressure,
                target_f_o2=args.target_f_o2,
                target_f_he=args.target_f_he,
                topup_f_o2=args.topup_f_o2,
                topup_f_he=args.topup_f_he,
                pressure_units=args.pressure_units,
                cylinder_preset=args.cylinder,
            )
            print(json.dumps(out, indent=2))
            return 0

    except DivePlannerValidationError as exc:
        print(f"VALIDATION ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"UNEXPECTED ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

