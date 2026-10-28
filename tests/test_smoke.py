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

        res_json = self._run_cli(["--json", "plan", "--depth", "180", "--time", "25", "--auto-best-gas"])
        self.assertEqual(res_json.returncode, 0, msg=res_json.stderr)
        data = json.loads(res_json.stdout)
        self.assertIn("primary_plan", data)
        self.assertTrue(data["primary_plan"]["summary"]["is_deco_dive"])

    def test_all_variant_and_utility_subcommands(self) -> None:
        commands = [
            ["max-depth", "--cylinder", "AL80", "--fill-psi", "3000", "--f-o2", "0.32"],
            ["max-time", "--depth", "100", "--f-o2", "0.32", "--cylinder", "AL80"],
            ["rock-bottom", "--depth", "180", "--time", "25", "--cylinder", "2xLP85"],
            ["what-if", "--depth", "180", "--time", "25", "--f-o2", "0.18", "--f-he", "0.45"],
            ["repetitive", "--d1-depth", "130", "--d1-time", "25", "--surface-interval", "90", "--d2-depth", "100", "--d2-time", "20"],
            ["bailout-sizing", "--depth", "220", "--time", "25", "--f-o2", "0.13", "--f-he", "0.54"],
            ["best-mix", "--depth", "200", "--max-po2", "1.40", "--max-end", "100"],
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
