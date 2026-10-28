#!/usr/bin/env python3
"""Unit tests for the Bühlmann ZH-L16C + Gradient Factors mathematical engine and diver utilities."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import zhl16c_planner as p


class TestZhl16cMathematics(unittest.TestCase):
    """Verifies exact Bühlmann ZH-L16C, Haldane, Schreiner, Baker GF, CNS, and OTU equations."""

    def test_compartment_1b_vs_1_toggle(self) -> None:
        table_1b = p.get_zhl16c_table("1b")
        table_1a = p.get_zhl16c_table("1")
        self.assertEqual(len(table_1b), 16)
        self.assertEqual(len(table_1a), 16)
        self.assertEqual(table_1b[0][:4], ("1b", 5.0, 1.1696, 0.5578))
        self.assertEqual(table_1a[0][:4], ("1", 4.0, 1.2599, 0.5050))
        self.assertEqual(table_1b[1:], table_1a[1:])

    def test_surface_pressure_altitude(self) -> None:
        p0 = p.surface_pressure_bar(0.0)
        self.assertAlmostEqual(p0, 1.01325, places=5)
        p_5000 = p.surface_pressure_bar(5000.0)
        # At 5000 ft (~1524 m), barometric pressure is ~0.843 bar
        self.assertAlmostEqual(p_5000, 0.84307, places=4)

    def test_haldane_and_schreiner_steps(self) -> None:
        # After 1 half-time at constant Pi0 = 3.0 bar starting from P0 = 1.0 bar, P = 2.0 bar
        p_after = p.haldane_step(1.0, 3.0, 5.0, 5.0)
        self.assertAlmostEqual(p_after, 2.0, places=7)

        # Schreiner with zero rate must equal Haldane
        p_sch_flat = p.schreiner_step(1.0, 3.0, 3.0, 5.0, 5.0)
        self.assertAlmostEqual(p_sch_flat, p_after, places=7)

        # Schreiner during linear descent (Pi increases from 0.75 to 3.75 over 3 minutes)
        p_sch_desc = p.schreiner_step(0.75, 0.75, 3.75, 5.0, 3.0)
        self.assertGreater(p_sch_desc, 0.75)
        self.assertLess(p_sch_desc, 3.75)

    def test_alveolar_inert_pressures_oc_and_ccr(self) -> None:
        # OC Air at 4.0 bar ambient
        pi_n2, pi_he, fo2, fn2, fhe = p.alveolar_inert_pressures(4.0, 0.21, 0.0, "OC")
        self.assertAlmostEqual(pi_n2, (4.0 - p.P_H2O_BAR) * 0.79, places=6)
        self.assertAlmostEqual(pi_he, 0.0, places=6)
        self.assertAlmostEqual(fo2, 0.21, places=6)

        # CCR at 4.0 bar with 1.3 bar setpoint and Tx 10/50 diluent (40% N2, 50% He -> 4:5 ratio)
        pi_n2_c, pi_he_c, fo2_c, fn2_c, fhe_c = p.alveolar_inert_pressures(
            4.0, 0.10, 0.50, "CCR", setpoint_bar=1.3
        )
        self.assertAlmostEqual(fo2_c, 1.3 / 4.0, places=6)
        self.assertAlmostEqual(pi_n2_c / pi_he_c, 0.40 / 0.50, places=6)
        self.assertAlmostEqual(fo2_c + fn2_c + fhe_c, 1.0, places=6)

    def test_baker_gradient_factor_ceiling(self) -> None:
        # Pure N2 in Comp 1b (a=1.1696, b=0.5578) with P_N2 = 3.0 bar at GF=0.30
        p_tol_30, a_w, b_w = p.compartment_ceiling_bar(
            3.0, 0.0, 1.1696, 0.5578, 1.6189, 0.4770, 0.30
        )
        self.assertAlmostEqual(a_w, 1.1696, places=6)
        self.assertAlmostEqual(b_w, 0.5578, places=6)
        expected = (3.0 - 1.1696 * 0.30) / (0.30 / 0.5578 - 0.30 + 1.0)
        self.assertAlmostEqual(p_tol_30, expected, places=6)

    def test_noaa_cns_and_otu_calculations(self) -> None:
        # At 1.40 ATA, NOAA T_lim = -300*(1.4) + 570 = 150 min. 30 min -> 20.0% CNS
        self.assertAlmostEqual(p.noaa_t_lim_min(1.40), 150.0, places=5)
        self.assertAlmostEqual(p.calculate_cns_segment(1.40, 1.40, 30.0), 20.0, places=5)
        # At 1.60 ATA, NOAA T_lim = -750*(1.6) + 1245 = 45 min. 45 min -> 100.0% CNS
        self.assertAlmostEqual(p.noaa_t_lim_min(1.60), 45.0, places=5)
        self.assertAlmostEqual(p.calculate_cns_segment(1.60, 1.60, 45.0), 100.0, places=5)
        # Surface interval decay: 90 min halves CNS %
        self.assertAlmostEqual(p.decay_cns_surface_interval(80.0, 90.0), 40.0, places=5)
        # OTU at 1.00 ATA: ((1.0 - 0.5)/0.5)^(5/6) = 1.0 OTU/min
        self.assertAlmostEqual(p.calculate_otu_segment(1.00, 1.00, 25.0), 25.0, places=5)

    def test_diver_utility_tools_1_to_4(self) -> None:
        # Tool 1 & 4: EAD, END, MOD, Gas Density for EAN32 at 100 fsw
        props = p.calculate_ead_end_mod_density(100.0, 0.32, 0.0, o2_narcotic=True)
        self.assertAlmostEqual(props["mod_working"], 111.4, places=1)
        self.assertAlmostEqual(props["ead"], 81.5, places=1)
        self.assertAlmostEqual(props["end"], 100.0, places=1)
        self.assertEqual(props["density_status"], "WARNING_HIGH_DENSITY")

        # Compare END with O2 non-narcotic on Tx 18/45 at 200 fsw
        p_narc = p.calculate_ead_end_mod_density(200.0, 0.18, 0.45, o2_narcotic=True)
        p_non = p.calculate_ead_end_mod_density(200.0, 0.18, 0.45, o2_narcotic=False)
        self.assertGreater(p_narc["end"], p_non["end"])

        # Tool 2: Best Mix for 200 fsw
        best = p.calculate_best_mix_for_depth(200.0, max_po2_ata=1.40, max_end=100.0)
        self.assertEqual(best["f_o2"], 0.19)
        self.assertGreaterEqual(best["f_he"], 0.45)
        self.assertLessEqual(best["properties_at_depth"]["po2_at_depth_ata"], 1.40)
        self.assertLessEqual(best["properties_at_depth"]["end"], 100.0)

        # Tool 3: Partial-pressure Trimix blending and Top-Up
        blend = p.calculate_gas_blender(
            mode="partial_pressure",
            start_pressure=500.0,
            start_f_o2=0.18,
            start_f_he=0.45,
            target_pressure=2640.0,
            target_f_o2=0.21,
            target_f_he=0.35,
            cylinder_preset="2xLP85",
        )
        self.assertEqual(blend["bleed_down_amount"], 0.0)
        self.assertAlmostEqual(
            blend["usable_initial_pressure"]
            + blend["add_helium"]
            + blend["add_oxygen"]
            + blend["add_topup_air"],
            2640.0,
            places=1,
        )

    def test_validation_error_codes(self) -> None:
        with self.assertRaises(p.DivePlannerValidationError) as ctx:
            p.validate_gas_fractions(0.60, 0.50)
        self.assertEqual(ctx.exception.code, "ERR_GAS_FRACTIONS")

        with self.assertRaises(p.DivePlannerValidationError) as ctx2:
            cfg = p.DiveConfig(gf_low=90.0, gf_high=70.0)
            cfg.validate()
        self.assertEqual(ctx2.exception.code, "ERR_GF_RANGE")

        with self.assertRaises(p.DivePlannerValidationError) as ctx3:
            cfg = p.DiveConfig(min_stop_time_sec=120)
            cfg.validate()
        self.assertEqual(ctx3.exception.code, "ERR_STOP_INTERVAL")

        with self.assertRaises(p.DivePlannerValidationError) as ctx4:
            cfg = p.DiveConfig(descent_rate=0.0)
            cfg.validate()
        self.assertEqual(ctx4.exception.code, "ERR_KINEMATIC_RATE")

        with self.assertRaises(p.DivePlannerValidationError) as ctx5:
            p.calculate_gas_blender(
                mode="partial_pressure",
                start_pressure=0.0,
                target_pressure=3000.0,
                target_f_o2=0.10,
                target_f_he=0.0,
                topup_f_o2=0.21,
                topup_f_he=0.0,
            )
        self.assertEqual(ctx5.exception.code, "ERR_BLEND_IMPOSSIBLE")


if __name__ == "__main__":
    unittest.main()
