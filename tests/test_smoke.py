#!/usr/bin/env python3
"""Smoke tests verifying CLI execution of all 10 subcommands and exit code conventions."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLI_SCRIPT = PROJECT_ROOT / "scripts" / "zhl16c_planner.py"


class TestCliSmoke(unittest.TestCase):
    """Executes scripts/zhl16c_planner.py subcommands from the command line."""

    def _run_cli(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI_SCRIPT)] + args,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_plan_subcommand_json_and_table(self) -> None:
        res_table = self._run_cli(["plan", "--depth", "150", "--time", "25", "--auto-best-gas"])
        self.assertEqual(res_table.returncode, 0, msg=res_table.stderr)
        self.assertIn("ZHL-16C (1b)", res_table.stdout)
        self.assertIn("SAFETY & VERIFICATION NOTICE", res_table.stdout)
        self.assertIn("certified dive professional", res_table.stdout)

        res_json = self._run_cli(["--json", "plan", "--depth", "180", "--time", "25", "--auto-best-gas"])
        self.assertEqual(res_json.returncode, 0, msg=res_json.stderr)
        data = json.loads(res_json.stdout)
        self.assertIn("primary_plan", data)
        self.assertTrue(data["primary_plan"]["summary"]["is_deco_dive"])
        self.assertIn("safety_notice", data)
        self.assertIn("certified dive professional", data["safety_notice"])

    def test_all_variant_and_utility_subcommands(self) -> None:
        commands = [
            ["max-depth", "--cylinder", "AL80", "--fill-psi", "3000", "--f-o2", "0.32"],
            ["max-time", "--depth", "100", "--f-o2", "0.32", "--cylinder", "AL80"],
            ["rock-bottom", "--depth", "180", "--time", "25", "--cylinder", "2xLP85"],
            ["what-if", "--depth", "180", "--time", "25", "--f-o2", "0.18", "--f-he", "0.45"],
            ["repetitive", "--d1-depth", "130", "--d1-time", "25", "--surface-interval", "90", "--d2-depth", "100", "--d2-time", "20"],
            ["bailout-sizing", "--depth", "220", "--time", "25", "--f-o2", "0.13", "--f-he", "0.54"],
            ["best-mix", "--depth", "200", "--max-po2", "1.40", "--max-end", "100"],
            ["best-mix", "--depth", "100", "--max-po2", "1.40", "--no-helium"],
            ["gas-tools", "--depth", "160", "--f-o2", "0.21", "--f-he", "0.35"],
            ["blend", "--mode", "partial_pressure", "--start-pressure", "500", "--start-f-o2", "0.18", "--start-f-he", "0.45", "--target-pressure", "2640", "--target-f-o2", "0.21", "--target-f-he", "0.35"],
            ["blend", "--mode", "topup_result", "--start-pressure", "1000", "--start-f-o2", "0.32", "--target-pressure", "3000", "--topup-f-o2", "0.21"],
            ["profiles", "--action", "list"],
        ]
        for cmd in commands:
            with self.subTest(subcommand=cmd[0]):
                proc = self._run_cli(cmd)
                self.assertEqual(proc.returncode, 0, msg=f"{cmd} failed: {proc.stderr}")
                parsed = json.loads(proc.stdout)
                self.assertIsInstance(parsed, dict)
                if cmd[0] != "profiles":
                    self.assertIn("safety_notice", parsed, msg=f"Missing safety_notice in {cmd[0]} output")
                    self.assertIn("SAFETY & VERIFICATION NOTICE", parsed["safety_notice"])

        # Verify --no-helium restricts both best-mix and plan --auto-best-gas to 0% He
        bm_no_he = self._run_cli(["best-mix", "--depth", "100", "--max-po2", "1.40", "--no-helium"])
        self.assertEqual(bm_no_he.returncode, 0, msg=bm_no_he.stderr)
        bm_data = json.loads(bm_no_he.stdout)
        self.assertFalse(bm_data["allow_helium"])
        self.assertEqual(bm_data["best_mix_name"], "EAN34")
        self.assertEqual(bm_data["f_he"], 0.0)

        plan_no_he = self._run_cli(["--json", "plan", "--depth", "100", "--time", "25", "--auto-best-gas", "--no-helium"])
        self.assertEqual(plan_no_he.returncode, 0, msg=plan_no_he.stderr)
        plan_data = json.loads(plan_no_he.stdout)
        self.assertEqual(plan_data["auto_selected_best_gas"]["best_mix_name"], "EAN34")
        self.assertEqual(plan_data["auto_selected_best_gas"]["f_he"], 0.0)

        # Verify rock-bottom CLI parity flags and effective turn pressure governance
        rb_cli = self._run_cli([
            "rock-bottom", "--depth", "130", "--cylinder", "AL80", "--fill-psi", "3000",
            "--switch-depth", "0", "--stressed-rmv", "1.00", "--divers", "2",
            "--problem-time", "1.0", "--ascent-rate", "30",
        ])
        self.assertEqual(rb_cli.returncode, 0, msg=rb_cli.stderr)
        rb_data = json.loads(rb_cli.stdout)
        self.assertEqual(rb_data["turn_governing_rule"], "ROCK_BOTTOM")
        self.assertGreater(rb_data["effective_turn_pressure_psi"], rb_data["rule_of_thirds_turn_pressure_psi"])

        # Verify repetitive --start-cns standalone NOAA 90-minute half-time CNS decay
        si_cli = self._run_cli(["repetitive", "--start-cns", "60", "--surface-interval", "90"])
        self.assertEqual(si_cli.returncode, 0, msg=si_cli.stderr)
        si_data = json.loads(si_cli.stdout)
        self.assertEqual(si_data["mode"], "cns_surface_interval_decay")
        self.assertEqual(si_data["cns_after_si_pct"], 30.0)
        self.assertIn("safety_notice", si_data)

    def test_profile_save_recall_and_delete_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_store = str(Path(tmpdir) / "custom_profiles.json")
            # 1. Save a profile via 'plan --save-profile-id'
            proc_save = self._run_cli([
                "--json", "plan",
                "--depth", "165", "--time", "30",
                "--f-o2", "0.21", "--f-he", "0.35",
                "--save-profile-id", "test-wreck-165",
                "--save-profile-title", "Test Wreck 165ft",
                "--profiles-file", temp_store,
            ])
            self.assertEqual(proc_save.returncode, 0, msg=proc_save.stderr)
            saved_out = json.loads(proc_save.stdout)
            self.assertEqual(saved_out["saved_profile"]["profile_id"], "test-wreck-165")

            # 2. List profiles from the store
            proc_list = self._run_cli(["profiles", "--action", "list", "--profiles-file", temp_store])
            self.assertEqual(proc_list.returncode, 0, msg=proc_list.stderr)
            list_out = json.loads(proc_list.stdout)
            self.assertEqual(list_out["count"], 1)
            self.assertEqual(list_out["profiles"][0]["title"], "Test Wreck 165ft")

            # 3. Recall and execute the saved profile by ID
            proc_recall = self._run_cli([
                "--json", "plan",
                "--profile-id", "test-wreck-165",
                "--profiles-file", temp_store,
            ])
            self.assertEqual(proc_recall.returncode, 0, msg=proc_recall.stderr)
            recall_out = json.loads(proc_recall.stdout)
            self.assertEqual(recall_out["primary_plan"]["summary"]["max_depth"], 165.0)

            # 4. Delete the profile via 'profiles --action delete'
            proc_del = self._run_cli([
                "profiles", "--action", "delete",
                "--profile-id", "test-wreck-165",
                "--profiles-file", temp_store,
            ])
            self.assertEqual(proc_del.returncode, 0, msg=proc_del.stderr)
            del_out = json.loads(proc_del.stdout)
            self.assertEqual(del_out["total_profiles"], 0)

    def test_cylinders_save_list_delete_lifecycle(self) -> None:
        # 1. Verify top-level --help lists cylinders cleanly and has no raw argparse dict bug
        proc_help = self._run_cli(["--help"])
        self.assertEqual(proc_help.returncode, 0, msg=proc_help.stderr)
        self.assertIn("cylinders", proc_help.stdout)
        self.assertNotIn("option_strings", proc_help.stdout)

        proc_cyl_help = self._run_cli(["cylinders", "--help"])
        self.assertEqual(proc_cyl_help.returncode, 0, msg=proc_cyl_help.stderr)
        self.assertIn("--cylinder-id", proc_cyl_help.stdout)
        self.assertIn("--rated-cuft", proc_cyl_help.stdout)
        self.assertIn("--water-liters", proc_cyl_help.stdout)

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_store = str(Path(tmpdir) / "custom_cyl_store.json")

            # 2. Save custom Imperial cylinder (HP130)
            proc_imp = self._run_cli([
                "cylinders", "--action", "save",
                "--cylinder-id", "HP130",
                "--name", "High Pressure Steel 130",
                "--rated-cuft", "130",
                "--rated-psi", "3442",
                "--profiles-file", temp_store,
            ])
            self.assertEqual(proc_imp.returncode, 0, msg=proc_imp.stderr)
            imp_out = json.loads(proc_imp.stdout)
            self.assertEqual(imp_out["action"], "created")
            self.assertEqual(imp_out["cylinder_id"], "HP130")
            self.assertAlmostEqual(imp_out["spec"]["rated_bar"], 237.3, delta=0.2)
            self.assertGreater(imp_out["spec"]["water_liters"], 15.0)

            # 3. Save custom Metric cylinder (D15_232)
            proc_met = self._run_cli([
                "cylinders", "--action", "save",
                "--cylinder-id", "D15_232",
                "--name", "Twin 2x15L Euro Doubles",
                "--water-liters", "30.0",
                "--rated-bar", "232",
                "--profiles-file", temp_store,
            ])
            self.assertEqual(proc_met.returncode, 0, msg=proc_met.stderr)
            met_out = json.loads(proc_met.stdout)
            self.assertEqual(met_out["custom_count"], 2)
            self.assertAlmostEqual(met_out["spec"]["rated_psi"], 3364.9, delta=0.5)

            # 4. List cylinders includes 14 built-ins + 2 custom
            proc_list = self._run_cli(["cylinders", "--action", "list", "--profiles-file", temp_store])
            self.assertEqual(proc_list.returncode, 0, msg=proc_list.stderr)
            list_out = json.loads(proc_list.stdout)
            self.assertEqual(list_out["builtin_count"], 14)
            self.assertEqual(list_out["custom_count"], 2)
            ids = {c["cylinder_id"] for c in list_out["cylinders"]}
            self.assertIn("HP130", ids)
            self.assertIn("D15_232", ids)

            # 5. Use custom cylinders across plan, rock-bottom, and blend CLI subcommands
            proc_plan = self._run_cli([
                "--json", "plan", "--depth", "150", "--time", "20", "--f-o2", "0.21", "--f-he", "0.35",
                "--cylinder", "HP130", "--profiles-file", temp_store,
            ])
            self.assertEqual(proc_plan.returncode, 0, msg=proc_plan.stderr)
            plan_out = json.loads(proc_plan.stdout)
            self.assertEqual(plan_out["primary_plan"]["cylinder_logistics"][0]["cylinder_preset"], "HP130")
            self.assertEqual(plan_out["primary_plan"]["cylinder_logistics"][0]["start_pressure_psi"], 3442.0)

            proc_rb = self._run_cli([
                "rock-bottom", "--depth", "150", "--time", "20",
                "--cylinder", "HP130", "--fill-psi", "3442",
                "--profiles-file", temp_store,
            ])
            self.assertEqual(proc_rb.returncode, 0, msg=proc_rb.stderr)
            rb_out = json.loads(proc_rb.stdout)
            self.assertEqual(rb_out["cylinder_preset"], "HP130")

            proc_bl = self._run_cli([
                "blend", "--cylinder", "D15_232", "--pressure-units", "bar",
                "--target-pressure", "232", "--target-f-o2", "0.18", "--target-f-he", "0.45",
                "--profiles-file", temp_store,
            ])
            self.assertEqual(proc_bl.returncode, 0, msg=proc_bl.stderr)
            bl_out = json.loads(proc_bl.stdout)
            self.assertEqual(bl_out["cylinder_capacity"]["cylinder_preset"], "D15_232")
            self.assertEqual(bl_out["cylinder_capacity"]["water_volume_liters"], 30.0)

            # 6. Built-in protection & unknown cylinder rejection -> exit code 2
            proc_builtin = self._run_cli([
                "cylinders", "--action", "delete", "--cylinder-id", "AL80", "--profiles-file", temp_store,
            ])
            self.assertEqual(proc_builtin.returncode, 2)
            self.assertIn("ERR_CYLINDER_BUILTIN", proc_builtin.stderr)

            proc_unknown = self._run_cli([
                "rock-bottom", "--depth", "130", "--cylinder", "NON_EXISTENT_999", "--profiles-file", temp_store,
            ])
            self.assertEqual(proc_unknown.returncode, 2)
            self.assertIn("ERR_CYLINDER_ID", proc_unknown.stderr)

            # 7. Delete custom cylinder cleanly
            proc_del = self._run_cli([
                "cylinders", "--action", "delete", "--cylinder-id", "HP130", "--profiles-file", temp_store,
            ])
            self.assertEqual(proc_del.returncode, 0, msg=proc_del.stderr)
            del_out = json.loads(proc_del.stdout)
            self.assertEqual(del_out["custom_count"], 1)

    def test_error_exit_codes(self) -> None:
        # Invalid GF Low > GF High -> exit code 2
        proc_val = self._run_cli(["plan", "--depth", "150", "--time", "20", "--gf-low", "90", "--gf-high", "50"])
        self.assertEqual(proc_val.returncode, 2)
        self.assertIn("ERR_GF_RANGE", proc_val.stderr)

        # Malformed JSON file -> exit code 3
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            tmp.write("{invalid_json: true")
            tmp_path = tmp.name
        try:
            proc_json = self._run_cli(["plan", "--input-file", tmp_path])
            self.assertEqual(proc_json.returncode, 3)
            self.assertIn("ERR_MALFORMED_JSON", proc_json.stderr)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
