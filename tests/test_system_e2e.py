#!/usr/bin/env python3
"""End-to-end system tests for benchmark profiles, dashboard generation, and repository structure."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import build_dashboard
from scripts import zhl16c_planner as p


class TestSystemEndToEnd(unittest.TestCase):
    """End-to-end verification of benchmark profiles, dashboard generation, and repository files."""

    def test_synthetic_profiles_end_to_end(self) -> None:
        profiles_path = PROJECT_ROOT / "assets" / "synthetic_dive_profiles.json"
        self.assertTrue(profiles_path.exists())
        payload = json.loads(profiles_path.read_text(encoding="utf-8"))
        profiles = payload.get("profiles", [])
        self.assertGreaterEqual(len(profiles), 3)

        for item in profiles:
            with self.subTest(profile_id=item["profile_id"]):
                cfg = p.config_from_dict(item["config"])
                res = p.plan_dive(cfg)
                summary = res["primary_plan"]["summary"]
                self.assertTrue(summary["is_deco_dive"])
                self.assertGreater(summary["total_deco_min"], 0.0)
                self.assertGreater(summary["total_runtime_min"], summary["total_deco_min"])
                self.assertEqual(len(res["primary_plan"]["final_compartments"]), 16)
                if cfg.dive_mode == "CCR" and cfg.include_bailout:
                    self.assertIsNotNone(res["bailout_plan"])
                    self.assertGreater(
                        len(res["bailout_plan"]["cylinder_logistics"]),
                        0,
                    )

    def test_all_eight_query_variants_programmatic(self) -> None:
        # Variant 1: Auto-best-gas dive plan
        cfg_v1 = p.DiveConfig(segments=[{"depth": 200.0, "time_min": 25.0}])
        res_v1 = p.plan_dive(cfg_v1, auto_best_gas=True)
        self.assertIsNotNone(res_v1["auto_selected_best_gas"])
        self.assertGreater(res_v1["primary_plan"]["summary"]["total_deco_min"], 20.0)

        # Variant 2: Tank & Gas Mix -> Max Depth Envelope
        res_v2 = p.solve_max_depth_envelope(cylinder_preset="AL80", fill_pressure_psi=3000.0, f_o2=0.32, f_he=0.0)
        self.assertGreater(res_v2["max_safe_operating_depth"], 80.0)
        self.assertLessEqual(res_v2["max_safe_operating_depth"], 112.0)

        # Variant 3A: NDL & Max Bottom Time at Depth
        res_v3a = p.solve_max_time_at_depth(depth=100.0, f_o2=0.32, f_he=0.0)
        self.assertGreater(res_v3a["no_decompression_limit_min"], 15.0)
        self.assertGreater(res_v3a["tank_limited_max_bottom_time_min"], 15.0)

        # Variant 3B: Rock Bottom
        res_v3b = p.solve_rock_bottom(depth=180.0, bottom_time_min=25.0, cylinder_preset="2xLP85", fill_pressure_psi=2640.0)
        self.assertGreater(res_v3b["rock_bottom_volume"], 20.0)
        self.assertGreater(res_v3b["rock_bottom_pressure_psi"], 300.0)

        # Variant 3C: What-If GF and Lost Gas
        cfg_v3c = p.DiveConfig(
            segments=[{"depth": 180.0, "time_min": 25.0}],
            oc_gases=[
                p.GasMix(name="Tx 18/45", f_o2=0.18, f_he=0.45, role="bottom"),
                p.GasMix(name="EAN50", f_o2=0.50, f_he=0.0, role="deco", max_po2=1.6, switch_depth=70.0),
                p.GasMix(name="O2 100%", f_o2=1.00, f_he=0.0, role="deco", max_po2=1.6, switch_depth=20.0),
            ],
        )
        res_v3c = p.solve_what_if_comparison(cfg_v3c)
        self.assertGreaterEqual(len(res_v3c["scenarios"]), 6)

        # Variant 3D: Repetitive Dive
        d1 = p.DiveConfig(
            segments=[{"depth": 120.0, "time_min": 20.0}],
            oc_gases=[p.GasMix(name="EAN32", f_o2=0.32, f_he=0.0, role="bottom")],
        )
        d2 = p.DiveConfig(
            segments=[{"depth": 100.0, "time_min": 20.0}],
            oc_gases=[p.GasMix(name="EAN32", f_o2=0.32, f_he=0.0, role="bottom")],
        )
        res_v3d = p.solve_repetitive_dive(d1, 60.0, d2)
        self.assertLess(res_v3d["cns_after_si_pct"], res_v3d["cns_before_si_pct"])

        # Variant 3E: CCR Bailout Sizing
        res_v3e = p.solve_ccr_bailout_sizing(depth=220.0, bottom_time_min=25.0)
        self.assertEqual(len(res_v3e["stage_cylinder_recommendations"]), 3)

    def test_dashboard_design_md_compliance(self) -> None:
        exit_code = build_dashboard.main()
        self.assertEqual(exit_code, 0)
        dash_path = PROJECT_ROOT / "dashboard.html"
        self.assertTrue(dash_path.exists())
        html = dash_path.read_text(encoding="utf-8")

        # Verify required DESIGN.md theme selector elements and tokens
        for required_token in [
            'id="theme-btn-light"',
            'id="theme-btn-dark"',
            'id="theme-btn-system"',
            'title="Light Theme"',
            'title="Dark Theme"',
            'title="System Theme"',
            'data-theme-mode="light"',
            'data-theme-mode="dark"',
            'data-theme-mode="system"',
            "prefers-color-scheme: dark",
            "localStorage",
            # Exact Light Mode tokens
            "#FAFAF9",
            "#FFFFFF",
            "#1C1917",
            "#787774",
            "#E7E5E4",
            # Exact Dark Mode tokens
            "#0D0E11",
            "#16171D",
            "#ECE8E2",
            "#9A9895",
            "#292A30",
            # Exact Semantic Palette tokens
            "#0D9488",
            "#D97706",
            "#4F46E5",
            "#059669",
            "#E11D48",
            # Required Typography
            "DM Sans",
            "Instrument Serif",
            "IBM Plex Mono",
            "tabular-nums",
            # In-Browser Profile Management Controls
            'id="btn-new-profile"',
            'id="btn-save-profile"',
            'id="btn-delete-profile"',
            'id="btn-export-profiles"',
            'id="btn-import-profiles"',
            'id="input-profile-name"',
            "zhl16c-custom-profiles",
            "createNewBlankProfile",
            "saveCurrentProfileToBrowser",
            "deleteSelectedProfileFromBrowser",
            # Primary Two-Tab Workspace Controls
            'id="main-tab-btn-planner"',
            'id="main-tab-btn-tools"',
            'id="main-view-planner"',
            'id="main-view-tools"',
            "switchMainWorkspaceTab",
            # Dual Y-Axis & Hover Tooltip Controls
            "PO2 (ATA)",
            "chart-hover-tooltip",
            "handleChartMouseMove",
            "handleChartMouseLeave",
        ]:
            self.assertIn(required_token, html, msg=f"Missing DESIGN.md token in dashboard.html: {required_token}")

    def test_project_structure_and_schema_integrity(self) -> None:
        required_files = [
            PROJECT_ROOT / "SKILL.md",
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "PRD.md",
            PROJECT_ROOT / "DESIGN.md",
            PROJECT_ROOT / "LICENSE",
            PROJECT_ROOT / "requirements.txt",
            PROJECT_ROOT / "documents" / "prd.md",
            PROJECT_ROOT / "references" / "zhl16c_math_reference.md",
            PROJECT_ROOT / "assets" / "dive_plan_schema.json",
            PROJECT_ROOT / "assets" / "synthetic_dive_profiles.json",
            PROJECT_ROOT / "scripts" / "zhl16c_planner.py",
            PROJECT_ROOT / "scripts" / "build_dashboard.py",
            PROJECT_ROOT / "dashboard.html",
        ]
        for fpath in required_files:
            self.assertTrue(fpath.exists(), msg=f"Required file missing: {fpath.name}")
            content = fpath.read_text(encoding="utf-8")
            self.assertGreater(len(content.strip()), 0)

        overview_img = PROJECT_ROOT / "assets" / "skill_overview.png"
        self.assertTrue(overview_img.exists(), msg="Required image missing: assets/skill_overview.png")
        self.assertGreater(overview_img.stat().st_size, 1024)

        schema_data = json.loads((PROJECT_ROOT / "assets" / "dive_plan_schema.json").read_text(encoding="utf-8"))
        self.assertIn("properties", schema_data)
        self.assertEqual(schema_data.get("title"), "TechnicalScubaDivePlanConfig")

        listed = p.list_saved_profiles()
        self.assertEqual(listed["profiles_file"], "assets/synthetic_dive_profiles.json")


if __name__ == "__main__":
    unittest.main()
