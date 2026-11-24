#!/usr/bin/env python3
"""Unit tests for the Bühlmann ZH-L16C + Gradient Factors mathematical engine and diver utilities."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import tempfile
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

    def test_strict_schema_and_finite_validation(self) -> None:
        # Reject undefined top-level keys
        with self.assertRaises(p.DivePlannerValidationError) as ctx_top:
            p.config_from_dict({
                "dive_mode": "OC",
                "segments": [{"depth": 100, "time_min": 20}],
                "unexpected_key": 123,
            })
        self.assertEqual(ctx_top.exception.code, "ERR_UNKNOWN_KEY")

        # Reject undefined gas mix keys
        with self.assertRaises(p.DivePlannerValidationError) as ctx_gas:
            p.config_from_dict({
                "dive_mode": "OC",
                "segments": [{"depth": 100, "time_min": 20}],
                "oc_gases": [{"name": "EAN32", "f_o2": 0.32, "f_he": 0.0, "extra": True}],
            })
        self.assertEqual(ctx_gas.exception.code, "ERR_UNKNOWN_KEY")

        # Reject undefined segment keys
        with self.assertRaises(p.DivePlannerValidationError) as ctx_seg:
            p.config_from_dict({
                "dive_mode": "OC",
                "segments": [{"depth": 100, "time_min": 20, "bad_field": 1}],
            })
        self.assertEqual(ctx_seg.exception.code, "ERR_UNKNOWN_KEY")

        # Reject NaN / Inf numeric parameters
        with self.assertRaises(p.DivePlannerValidationError) as ctx_nan:
            cfg = p.DiveConfig(gf_low=float("nan"), gf_high=85.0)
            cfg.validate()
        self.assertEqual(ctx_nan.exception.code, "ERR_GF_RANGE")

        with self.assertRaises(p.DivePlannerValidationError) as ctx_inf:
            p.surface_pressure_bar(float("inf"))
        self.assertEqual(ctx_inf.exception.code, "ERR_ELEVATION")

        # Reject out-of-range CCR setpoints
        with self.assertRaises(p.DivePlannerValidationError) as ctx_sp:
            cfg = p.DiveConfig(ccr_setpoint_bottom=2.10)
            cfg.validate()
        self.assertEqual(ctx_sp.exception.code, "ERR_SETPOINT")

        # Reject invalid ascent_rate in solve_rock_bottom (prevents division by zero)
        with self.assertRaises(p.DivePlannerValidationError) as ctx_rb:
            p.solve_rock_bottom(depth=180.0, bottom_time_min=25.0, ascent_rate=0.0)
        self.assertEqual(ctx_rb.exception.code, "ERR_KINEMATIC_RATE")

    def test_best_mix_no_helium_mode(self) -> None:
        # 100 fsw at 1.40 ATA: with allow_helium=True density forces 2% He (Tx 34/2); allow_helium=False -> EAN34
        bm_trimix = p.calculate_best_mix_for_depth(100.0, max_po2_ata=1.40, max_end=100.0, allow_helium=True)
        self.assertGreater(bm_trimix["f_he"], 0.0)
        self.assertTrue(bm_trimix["allow_helium"])

        bm_nitrox_100 = p.calculate_best_mix_for_depth(100.0, max_po2_ata=1.40, max_end=100.0, allow_helium=False)
        self.assertFalse(bm_nitrox_100["allow_helium"])
        self.assertEqual(bm_nitrox_100["best_mix_name"], "EAN34")
        self.assertEqual(bm_nitrox_100["f_o2"], 0.34)
        self.assertEqual(bm_nitrox_100["f_he"], 0.0)
        self.assertEqual(bm_nitrox_100["closest_standard_agency_mix"]["f_he"], 0.0)
        self.assertTrue(any("GAS_DENSITY_CAUTION" in w for w in bm_nitrox_100["warnings"]))

        # 130 fsw without helium -> EAN28 with narcosis and critical density warnings
        bm_nitrox_130 = p.calculate_best_mix_for_depth(130.0, max_po2_ata=1.40, max_end=100.0, allow_helium=False)
        self.assertEqual(bm_nitrox_130["best_mix_name"], "EAN28")
        self.assertEqual(bm_nitrox_130["f_he"], 0.0)
        self.assertTrue(any("NARCOSIS_WARNING" in w for w in bm_nitrox_130["warnings"]))
        self.assertTrue(any("GAS_DENSITY_CRITICAL" in w for w in bm_nitrox_130["warnings"]))

        # 200 fsw without helium -> flags TRIMIX_REQUIRED_FOR_PO2 (< 21% O2)
        bm_nitrox_200 = p.calculate_best_mix_for_depth(200.0, max_po2_ata=1.40, max_end=100.0, allow_helium=False)
        self.assertEqual(bm_nitrox_200["f_he"], 0.0)
        self.assertTrue(any("TRIMIX_REQUIRED_FOR_PO2" in w for w in bm_nitrox_200["warnings"]))

        # plan_dive with auto_best_gas=True and allow_helium=False selects EAN34 (0% He)
        cfg = p.DiveConfig(segments=[{"depth": 100.0, "time_min": 25.0}])
        res = p.plan_dive(cfg, auto_best_gas=True, allow_helium=False)
        self.assertEqual(res["auto_selected_best_gas"]["best_mix_name"], "EAN34")
        self.assertEqual(res["auto_selected_best_gas"]["f_he"], 0.0)
        self.assertEqual(res["config"]["oc_gases"][0]["f_he"], 0.0)

    def test_rock_bottom_effective_turn_pressure_rules(self) -> None:
        # 1. Rule of Thirds governs when rock bottom < 1/3 of starting fill (2xLP85 @ 2640 psi, 180 ft -> 70 ft switch)
        rb_thirds = p.solve_rock_bottom(
            depth=180.0, bottom_time_min=25.0, cylinder_preset="2xLP85",
            fill_pressure_psi=2640.0, first_switch_depth=70.0, stressed_rmv_per_diver=1.00,
        )
        self.assertEqual(rb_thirds["turn_governing_rule"], "RULE_OF_THIRDS")
        self.assertEqual(rb_thirds["effective_turn_pressure_psi"], rb_thirds["rule_of_thirds_turn_pressure_psi"])
        self.assertEqual(rb_thirds["warnings"], [])

        # 2. Rock Bottom governs when reserve > 1/3 of starting fill (AL80 @ 3000 psi, 130 ft -> 0 ft surface)
        rb_gov = p.solve_rock_bottom(
            depth=130.0, bottom_time_min=20.0, cylinder_preset="AL80",
            fill_pressure_psi=3000.0, first_switch_depth=0.0, stressed_rmv_per_diver=1.00,
            num_divers_sharing=2, problem_solving_time_min=1.0, ascent_rate=30.0,
        )
        self.assertEqual(rb_gov["turn_governing_rule"], "ROCK_BOTTOM")
        self.assertGreater(rb_gov["effective_turn_pressure_psi"], rb_gov["rule_of_thirds_turn_pressure_psi"])
        self.assertTrue(any("ROCK_BOTTOM_EXCEEDS_THIRDS" in w for w in rb_gov["warnings"]))

        # 3. Insufficient cylinder capacity when rock bottom >= starting fill (AL80 @ 3000 psi, 220 ft -> 0 ft)
        rb_insuff = p.solve_rock_bottom(
            depth=220.0, bottom_time_min=20.0, cylinder_preset="AL80",
            fill_pressure_psi=3000.0, first_switch_depth=0.0, stressed_rmv_per_diver=1.00,
        )
        self.assertEqual(rb_insuff["turn_governing_rule"], "INSUFFICIENT_CYLINDER")
        self.assertEqual(rb_insuff["usable_before_turn_psi"], 0.0)
        self.assertTrue(any("INSUFFICIENT_CYLINDER_CAPACITY" in w for w in rb_insuff["warnings"]))

    def test_custom_cylinder_crud_and_physics_parity(self) -> None:
        # 1. Imperial auto-derivation (HP130: 130 cuft @ 3442 psi -> 15.72 L @ 237.3 bar, exact 1:1 volume)
        imp = p.build_cylinder_spec(name="High Pressure Steel 130", rated_cuft=130.0, rated_psi=3442.0)
        self.assertEqual(imp["rated_cuft"], 130.0)
        self.assertEqual(imp["rated_psi"], 3442.0)
        self.assertAlmostEqual(imp["rated_bar"], 237.3, delta=0.2)
        self.assertAlmostEqual(imp["water_liters"], 15.72, delta=0.05)

        # 2. Metric auto-derivation (D15_232: 30 L @ 232 bar -> 242.6 cuft @ 3364.9 psi, exact 1:1 volume)
        met = p.build_cylinder_spec(name="Twin 2x15L Euro Doubles", water_liters=30.0, rated_bar=232.0)
        self.assertEqual(met["water_liters"], 30.0)
        self.assertEqual(met["rated_bar"], 232.0)
        self.assertAlmostEqual(met["rated_psi"], 3364.9, delta=0.5)
        self.assertAlmostEqual(met["rated_cuft"], 242.6, delta=0.2)

        # 3. Validation errors for invalid ID, built-in collision, and out-of-range specs
        for bad_id in ("", "bad id", "../etc", "__proto__", "<script>"):
            with self.assertRaises(p.DivePlannerValidationError) as ctx:
                p.validate_cylinder_id(bad_id)
            self.assertEqual(ctx.exception.code, "ERR_CYLINDER_ID")

        with self.assertRaises(p.DivePlannerValidationError) as ctx:
            p.build_cylinder_spec(name="Bad", rated_cuft=100.0)  # missing working pressure
        self.assertEqual(ctx.exception.code, "ERR_CYLINDER_SPEC")

        with tempfile.TemporaryDirectory() as tmpdir:
            store = Path(tmpdir) / "cyl_store.json"
            with self.assertRaises(p.DivePlannerValidationError) as ctx:
                p.save_cylinder_to_store("AL80", name="Overwrite", rated_cuft=80.0, rated_psi=3000.0, profiles_file=store, rebuild_dashboard=False)
            self.assertEqual(ctx.exception.code, "ERR_CYLINDER_BUILTIN")

            # 4. Save, list, calculate capacity / blend / rock-bottom / plan, and delete
            saved = p.save_cylinder_to_store(
                "HP130", name="High Pressure Steel 130", rated_cuft=130.0, rated_psi=3442.0,
                profiles_file=store, rebuild_dashboard=False,
            )
            self.assertEqual(saved["action"], "created")
            self.assertEqual(saved["custom_count"], 1)

            listed = p.list_cylinders(profiles_file=store)
            self.assertEqual(listed["builtin_count"], 14)
            self.assertEqual(listed["custom_count"], 1)

            cap = p.calculate_cylinder_fill_capacity("HP130", 3442.0, "psi", 0.32, 0.0, profiles_file=store)
            self.assertEqual(cap["ideal_volume_cuft"], 130.0)
            self.assertEqual(cap["cylinder_name"], "High Pressure Steel 130")

            rb = p.solve_rock_bottom(
                depth=150.0, bottom_time_min=20.0, cylinder_preset="HP130",
                fill_pressure_psi=3442.0, profiles_file=store,
            )
            self.assertEqual(rb["cylinder_preset"], "HP130")

            cfg = p.DiveConfig(
                segments=[{"depth": 150.0, "time_min": 20.0}],
                oc_gases=[p.GasMix(name="Tx 21/35", f_o2=0.21, f_he=0.35, role="bottom", cylinder_preset="HP130", start_pressure_psi=3442.0)],
            )
            plan_res = p.plan_dive(cfg, profiles_file=store)
            self.assertEqual(plan_res["primary_plan"]["cylinder_logistics"][0]["cylinder_preset"], "HP130")
            self.assertEqual(plan_res["primary_plan"]["cylinder_logistics"][0]["volume_available"], 130.0)

            deleted = p.delete_cylinder_from_store("HP130", profiles_file=store, rebuild_dashboard=False)
            self.assertEqual(deleted["custom_count"], 0)

            with self.assertRaises(p.DivePlannerValidationError) as ctx:
                p.calculate_cylinder_fill_capacity("HP130", 3442.0, "psi", profiles_file=store)
            self.assertEqual(ctx.exception.code, "ERR_CYLINDER_ID")


if __name__ == "__main__":
    unittest.main()
