#!/usr/bin/env python3
"""End-to-end system tests for benchmark profiles, dashboard generation, and repository structure."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
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
            PROJECT_ROOT / "NOTICE",
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

        # Verify LICENSE stays verbatim Apache License, Version 2.0 and NOTICE carries safety notice
        license_head = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")[:200]
        self.assertIn("Apache License", license_head)
        self.assertIn("Version 2.0, January 2004", license_head)
        notice_text = (PROJECT_ROOT / "NOTICE").read_text(encoding="utf-8")
        self.assertIn("MANDATORY VERIFICATION, PROFESSIONAL CONFIRMATION, AND ASSUMPTION OF RISK NOTICE", notice_text)
        self.assertIn("DRAFT — REQUIRES LEGAL REVIEW", notice_text)

        overview_img = PROJECT_ROOT / "assets" / "skill_overview.png"
        self.assertTrue(overview_img.exists(), msg="Required image missing: assets/skill_overview.png")
        self.assertGreater(overview_img.stat().st_size, 1024)

        schema_data = json.loads((PROJECT_ROOT / "assets" / "dive_plan_schema.json").read_text(encoding="utf-8"))
        self.assertIn("properties", schema_data)
        self.assertEqual(schema_data.get("title"), "TechnicalScubaDivePlanConfig")

        listed = p.list_saved_profiles()
        self.assertEqual(listed["profiles_file"], "assets/synthetic_dive_profiles.json")

        # Verify legal draft templates exist and carry required legal-review banner
        for legal_name in ["privacy.md", "terms.md", "refunds.md", "cookies.md"]:
            legal_path = PROJECT_ROOT / "legal" / legal_name
            self.assertTrue(legal_path.exists(), msg=f"Missing legal draft: legal/{legal_name}")
            legal_text = legal_path.read_text(encoding="utf-8")
            self.assertIn("DRAFT — REQUIRES LEGAL REVIEW", legal_text)

    def test_dashboard_security_csp_xss_and_wcag_compliance(self) -> None:
        # 1. Verify script-tag breakout escaping in embedded JSON
        malicious = {
            "profiles": [
                {"profile_id": "xss-test", "title": "</script><script>alert(1)</script>"}
            ],
            "standard_cylinders": p.STANDARD_CYLINDERS,
            "standard_agency_mixes": p.STANDARD_AGENCY_MIXES,
        }
        rendered = build_dashboard.generate_dashboard_html(malicious)
        self.assertNotIn("</script><script>alert(1)</script>", rendered)
        self.assertIn("\\u003c/script\\u003e\\u003cscript\\u003ealert(1)\\u003c/script\\u003e", rendered)

        # 2. Verify CSP, offline isolation, XSS helpers, local erasure, print safety layout, and WCAG controls
        html = (PROJECT_ROOT / "dashboard.html").read_text(encoding="utf-8")
        for required_security_or_a11y in [
            'http-equiv="Content-Security-Policy"',
            "default-src 'none'",
            "connect-src 'none'",
            'name="referrer" content="no-referrer"',
            "function escapeHtml(",
            "function sanitizeImportedConfig(",
            "function clearAllLocalData(",
            "function handleTablistKeydown(",
            "function handleChartKeydown(",
            'class="skip-link"',
            ":focus-visible",
            "<footer ",
            'role="progressbar"',
            'id="btn-clear-local-data"',
            'id="btn-print-plan"',
            "@media print",
            'class="print-safety-block"',
            "Pre-Dive Verification Checklist",
            "safety_notice: SAFETY_VERIFICATION_NOTICE",
        ]:
            self.assertIn(required_security_or_a11y, html, msg=f"Missing hardened dashboard token: {required_security_or_a11y}")

        # Verify previously removed execution/Apache footer line remains omitted
        self.assertNotIn("Execution: Local offline browser only", html)

        # Verify zero external URLs, dedicated settings row under Profile, and icon-only SVG theme switcher
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        profile_row_start = html.index('class="navbar-profile-row"')
        settings_row_start = html.index('class="navbar-settings-row"')
        self.assertGreater(settings_row_start, profile_row_start)
        profile_row_block = html[profile_row_start:settings_row_start]
        settings_row_end = html.index("</header>", settings_row_start)
        settings_row_block = html[settings_row_start:settings_row_end]
        for action_id in ('id="preset-select"', 'id="btn-new-profile"', 'id="btn-save-profile"', 'id="btn-clear-local-data"'):
            self.assertIn(action_id, profile_row_block)
            self.assertNotIn(action_id, settings_row_block)
        for setting_id in ('id="mode-btn-oc"', 'id="unit-btn-feet"', 'class="theme-switcher"'):
            self.assertIn(setting_id, settings_row_block)
            self.assertNotIn(setting_id, profile_row_block)

        theme_start = html.index('class="theme-switcher"')
        theme_end = html.index("</div>", theme_start)
        theme_block = html[theme_start:theme_end]
        self.assertEqual(theme_block.count("<svg "), 3)
        self.assertEqual(theme_block.count('aria-hidden="true"'), 3)
        self.assertNotIn(">Light<", theme_block)
        self.assertNotIn(">Dark<", theme_block)
        self.assertNotIn(">System<", theme_block)

        # 3. Verify WCAG 2.2 AA contrast ratios (>= 4.5:1 text, >= 3.0:1 UI control borders)
        def _contrast(h1: str, h2: str) -> float:
            def _lum(hx: str) -> float:
                rgb = [int(hx.lstrip("#")[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
                lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
                return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
            l1, l2 = _lum(h1), _lum(h2)
            return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)

        text_pairs = [
            ("#1C1917", "#FFFFFF"),
            ("#57534E", "#FAFAF9"),
            ("#57534E", "#F5F5F4"),
            ("#0F766E", "#FFFFFF"),
            ("#B45309", "#FFFFFF"),
            ("#4338CA", "#FAFAF9"),
            ("#047857", "#FFFFFF"),
            ("#BE123C", "#FFFFFF"),
            ("#ECE8E2", "#16171D"),
            ("#9A9895", "#1E2028"),
            ("#2DD4BF", "#16171D"),
            ("#0D0E11", "#14B8A6"),
            ("#0D0E11", "#F59E0B"),
            ("#F59E0B", "#16171D"),
            ("#818CF8", "#16171D"),
            ("#34D399", "#16171D"),
            ("#FB7185", "#16171D"),
        ]
        for fg, bg in text_pairs:
            self.assertGreaterEqual(_contrast(fg, bg), 4.5, msg=f"WCAG AA text contrast failed for {fg} on {bg}")

        control_border_pairs = [
            ("#787774", "#FAFAF9"),
            ("#787774", "#FFFFFF"),
            ("#6E707A", "#16171D"),
            ("#6E707A", "#0D0E11"),
        ]
        for fg, bg in control_border_pairs:
            self.assertGreaterEqual(_contrast(fg, bg), 3.0, msg=f"WCAG AA UI border contrast failed for {fg} on {bg}")

    def test_repository_hygiene_and_algorithm_preservation(self) -> None:
        # Ensure zero local machine absolute paths and zero Unicode emojis across text files
        abs_prefixes = ["/Users" + "/", "/home" + "/", "/usr/" + "local/", "C:" + "\\"]
        skip_dirs = {".git", "__pycache__"}
        for path in sorted(PROJECT_ROOT.rglob("*")):
            if any(part in skip_dirs for part in path.parts) or not path.is_file():
                continue
            if path.suffix in {".png", ".pyc"}:
                continue
            content = path.read_text(encoding="utf-8")
            for prefix in abs_prefixes:
                self.assertNotIn(prefix, content, msg=f"Local absolute path found in {path.name}")
            for ch in content:
                codepoint = ord(ch)
                self.assertFalse(
                    0x1F300 <= codepoint <= 0x1FAFF or 0x2600 <= codepoint <= 0x27BF,
                    msg=f"Decorative emoji/symbol U+{codepoint:04X} found in {path.name}",
                )

        # Ensure algorithm names and Apache 2.0 license remain preserved
        readme_text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        for preserved in ["Bühlmann", "ZH-L16C", "Gradient Factors", "Haldane", "Schreiner", "NOAA", "Lambertsen", "Apache License"]:
            self.assertIn(preserved, readme_text, msg=f"Expected preserved term missing from README.md: {preserved}")

    def test_dashboard_gas_blender_zero_he_and_residual_updates(self) -> None:
        html = (PROJECT_ROOT / "dashboard.html").read_text(encoding="utf-8")

        # 1. Static checks: safe numeric parser, 5-tab Diver Tools layout, live oninput wiring, and removal of falsy-zero fallbacks
        self.assertIn("function readNumericInput(", html)
        self.assertIn("function setBestMixGasMode(", html)
        self.assertIn("function syncRockBottomFromPlan(", html)
        self.assertIn("function runUtilitySurfaceInterval(", html)
        self.assertIn('id="u2-mode-trimix"', html)
        self.assertIn('id="u2-mode-nitrox"', html)
        self.assertIn('id="util-tab-btn-si"', html)
        self.assertIn('id="util-tab-surface-interval"', html)
        self.assertIn('id="btn-u4-sync-plan"', html)
        self.assertIn('id="btn-u5-sync-plan"', html)
        self.assertIn('class="blender-mix-row"', html)
        self.assertIn('class="blender-mix-pair"', html)
        self.assertNotIn('Number(document.getElementById("u3-target-fhe").value) || 35', html)
        self.assertNotIn('Number(document.getElementById("u4-switch-depth").value) || 70', html)
        for input_id in [
            "u3-start-psi",
            "u3-target-psi",
            "u3-start-fo2",
            "u3-start-fhe",
            "u3-target-fo2",
            "u3-target-fhe",
        ]:
            self.assertRegex(
                html,
                rf'id="{input_id}"[^>]*oninput="runUtilityBlender\(\)"',
                msg=f"Missing live oninput handler on #{input_id}",
            )

        # 2. Execute the actual inline dashboard script under Node.js to verify runtime behavior & Python parity
        node_bin = shutil.which("node")
        if not node_bin:
            return
        script_match = re.search(r"<script>(.*)</script>", html, re.S)
        self.assertIsNotNone(script_match, "Inline <script> not found in dashboard.html")
        inline_js = script_match.group(1)

        harness = (
            """
            const vm = require('vm');
            function makeBtn() {
              return {
                attrs: {},
                classList: { toggle: () => {} },
                setAttribute(k, v) { this.attrs[k] = v; },
              };
            }
            const elements = {
              'u1-depth': { value: '130' },
              'u1-fo2': { value: '32' },
              'u1-fhe': { value: '0' },
              'u1-cylinder': { value: 'AL80' },
              'u1-max-po2': { value: '1.40' },
              'u1-max-end': { value: '100' },
              'u1-results-box': { innerHTML: '' },
              'u2-depth': { value: '100' },
              'u2-po2': { value: '1.40' },
              'u2-end': { value: '100' },
              'u2-mode-trimix': makeBtn(),
              'u2-mode-nitrox': makeBtn(),
              'u2-end-label-text': { textContent: 'Target Max END' },
              'u2-results-box': { innerHTML: '' },
              'u3-cylinder': { value: '2xLP85' },
              'u3-start-psi': { value: '500' },
              'u3-target-psi': { value: '2640' },
              'u3-start-fo2': { value: '18' },
              'u3-start-fhe': { value: '45' },
              'u3-target-fo2': { value: '21' },
              'u3-target-fhe': { value: '35' },
              'u3-results-box': { innerHTML: '' },
              'u4-depth': { value: '180' },
              'u4-cylinder': {
                value: '2xLP85',
                options: [{ value: '2xLP85' }, { value: 'AL80' }, { value: 'D12_232' }],
              },
              'u4-fill-pressure': { value: '2640' },
              'u4-switch-depth': { value: '70' },
              'u4-stressed-rmv': { value: '1.00' },
              'u4-divers': { value: '2' },
              'u4-problem-min': { value: '1.0' },
              'u4-ascent-rate': { value: '30' },
              'u4-results-box': { innerHTML: '' },
              'u5-start-cns': { value: '60.0' },
              'u4-si-min': { value: '90' },
              'u5-results-box': { innerHTML: '' },
              'input-depth': { value: '180' },
              'input-time': { value: '25' },
              'input-gf-low': { value: '30' },
              'input-gf-high': { value: '85' },
              'input-comp1': { value: '1b' },
              'input-o2-narc': { value: 'true' },
              'input-sp-bottom': { value: '1.20' },
              'input-sp-deco': { value: '1.30' },
              'input-sp-units': { value: 'ATA' },
              'input-stop-size': { value: '10' },
              'input-last-oc-stop': { value: '10' },
              'input-last-ccr-stop': { value: '10' },
              'input-min-stop-sec': { value: '60' },
              'input-rmv-bottom': { value: '0.75' },
              'input-rmv-deco': { value: '0.60' },
              'input-rate-desc': { value: '60' },
              'input-rate-asc': { value: '30' },
              'input-rate-deco': { value: '30' },
              'input-rate-surf': { value: '10' },
              'input-elevation': { value: '0' },
            };
            const ctx = {
              console,
              Math,
              Number,
              String,
              Boolean,
              Object,
              Array,
              JSON,
              Date,
              Infinity,
              NaN,
              isNaN,
              isFinite,
              document: {
                getElementById: (id) => elements[id] || null,
                querySelectorAll: () => [],
                documentElement: { setAttribute: () => {} },
                addEventListener: () => {},
              },
              window: {
                addEventListener: () => {},
                matchMedia: () => ({ matches: false, addEventListener: () => {} }),
              },
              localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
            };
            vm.createContext(ctx);
            vm.runInContext(SCRIPT_SRC, ctx);

            function runBlendCase(vals) {
              Object.keys(vals).forEach(k => { elements[k].value = String(vals[k]); });
              ctx.runUtilityBlender();
              return elements['u3-results-box'].innerHTML;
            }

            function runBestMixCase(depth, allowHe) {
              elements['u2-depth'].value = String(depth);
              elements['u2-po2'].value = '1.40';
              elements['u2-end'].value = '100';
              ctx.setBestMixGasMode(allowHe);
              return {
                html: elements['u2-results-box'].innerHTML,
                endLabel: elements['u2-end-label-text'].textContent,
                trimixPressed: elements['u2-mode-trimix'].attrs['aria-pressed'],
                nitroxPressed: elements['u2-mode-nitrox'].attrs['aria-pressed'],
              };
            }

            function runRockBottomCase(vals) {
              Object.keys(vals).forEach(k => { elements[k].value = String(vals[k]); });
              ctx.runUtilityDensityAndRockBottom();
              return elements['u4-results-box'].innerHTML;
            }

            ctx.runUtilityModAndMaxDepth();
            const u1DensityHtml = elements['u1-results-box'].innerHTML;

            const results = {
              u1_density: u1DensityHtml,
              zero_he_ean32: runBlendCase({
                'u3-cylinder': '2xLP85', 'u3-start-psi': '500', 'u3-target-psi': '2640',
                'u3-start-fo2': '18', 'u3-start-fhe': '45', 'u3-target-fo2': '32', 'u3-target-fhe': '0',
              }),
              zero_he_air: runBlendCase({
                'u3-cylinder': '2xLP85', 'u3-start-psi': '500', 'u3-target-psi': '2640',
                'u3-start-fo2': '21', 'u3-start-fhe': '0', 'u3-target-fo2': '21', 'u3-target-fhe': '0',
              }),
              partial_bleed_ean36_to_ean32: runBlendCase({
                'u3-cylinder': 'AL80', 'u3-start-psi': '2500', 'u3-target-psi': '3000',
                'u3-start-fo2': '36', 'u3-start-fhe': '0', 'u3-target-fo2': '32', 'u3-target-fhe': '0',
              }),
              empty_start_to_ean32: runBlendCase({
                'u3-cylinder': 'AL80', 'u3-start-psi': '0', 'u3-target-psi': '3000',
                'u3-start-fo2': '21', 'u3-start-fhe': '0', 'u3-target-fo2': '32', 'u3-target-fhe': '0',
              }),
              default_trimix_cascade: runBlendCase({
                'u3-cylinder': '2xLP85', 'u3-start-psi': '500', 'u3-target-psi': '2640',
                'u3-start-fo2': '18', 'u3-start-fhe': '45', 'u3-target-fo2': '21', 'u3-target-fhe': '35',
              }),
              impossible_air_topup: runBlendCase({
                'u3-cylinder': 'AL80', 'u3-start-psi': '0', 'u3-target-psi': '3000',
                'u3-start-fo2': '21', 'u3-start-fhe': '0', 'u3-target-fo2': '18', 'u3-target-fhe': '0',
              }),
              invalid_sum_over_100: runBlendCase({
                'u3-cylinder': 'AL80', 'u3-start-psi': '0', 'u3-target-psi': '3000',
                'u3-start-fo2': '21', 'u3-start-fhe': '0', 'u3-target-fo2': '70', 'u3-target-fhe': '40',
              }),
              bestmix_100_nitrox: runBestMixCase(100, false),
              bestmix_130_nitrox: runBestMixCase(130, false),
              bestmix_200_nitrox: runBestMixCase(200, false),
              bestmix_200_trimix: runBestMixCase(200, true),
              u4_thirds_governs: runRockBottomCase({
                'u4-depth': '180', 'u4-cylinder': '2xLP85', 'u4-fill-pressure': '2640',
                'u4-switch-depth': '70', 'u4-stressed-rmv': '1.00', 'u4-divers': '2',
                'u4-problem-min': '1.0', 'u4-ascent-rate': '30',
              }),
              u4_switch_depth_zero: runRockBottomCase({
                'u4-depth': '130', 'u4-cylinder': 'AL80', 'u4-fill-pressure': '3000',
                'u4-switch-depth': '0', 'u4-stressed-rmv': '1.00', 'u4-divers': '2',
                'u4-problem-min': '1.0', 'u4-ascent-rate': '30',
              }),
            };

            // Verify one-click Sync from Dive Plan restores active Dive Planner depth & deco switch
            elements['input-depth'].value = '200';
            ctx.syncRockBottomFromPlan();
            results.u4_synced_depth = elements['u4-depth'].value;
            results.u4_synced_switch = elements['u4-switch-depth'].value;

            // Verify Tab 5 Repetitive / Surface Interval CNS % decay
            elements['u5-start-cns'].value = '60.0';
            elements['u4-si-min'].value = '90';
            ctx.runUtilitySurfaceInterval();
            results.u5_si_decay = elements['u5-results-box'].innerHTML;

            process.stdout.write(JSON.stringify(results));
            """.replace("SCRIPT_SRC", json.dumps(inline_js))
        )
        proc = subprocess.run([node_bin], input=harness, capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, msg=f"Node execution failed: {proc.stderr}")
        out = json.loads(proc.stdout)

        # Tab 1: Verify Gas Density @ Depth and MDD (5.2 / 6.2 g/L)
        self.assertIn("Density @ 130ft", out["u1_density"])
        self.assertIn("MDD (5.2 / 6.2 g/L)", out["u1_density"])
        self.assertIn("g/L", out["u1_density"])

        # Case 1: Target He% = 0, O2% = 32 with residual Tx 18/45 @ 500 psi -> EAN32 (NOT Tx 32/35)
        py_ean32 = p.calculate_gas_blender(
            mode="partial_pressure", start_pressure=500, start_f_o2=0.18, start_f_he=0.45,
            target_pressure=2640, target_f_o2=0.32, target_f_he=0.0, cylinder_preset="2xLP85",
        )
        self.assertIn("<td><strong>EAN32</strong></td>", out["zero_he_ean32"])
        self.assertNotIn("Tx 32/35", out["zero_he_ean32"])
        self.assertIn("Tx 18/45 @ 500 psi", out["zero_he_ean32"])
        self.assertIn(f"{py_ean32['bleed_down_amount']:.0f} psi", out["zero_he_ean32"])
        self.assertIn(f"+{py_ean32['add_helium']:.0f} psi", out["zero_he_ean32"])
        self.assertIn(f"+{py_ean32['add_oxygen']:.0f} psi", out["zero_he_ean32"])
        self.assertIn(f"+{py_ean32['add_topup_air']:.0f} psi", out["zero_he_ean32"])

        # Case 2: Target He% = 0, O2% = 21 with residual Air @ 500 psi -> Air (21%), 0 psi bleed
        py_air = p.calculate_gas_blender(
            mode="partial_pressure", start_pressure=500, start_f_o2=0.21, start_f_he=0.0,
            target_pressure=2640, target_f_o2=0.21, target_f_he=0.0, cylinder_preset="2xLP85",
        )
        self.assertIn("<td><strong>Air (21%)</strong></td>", out["zero_he_air"])
        self.assertIn("Air (21%) @ 500 psi", out["zero_he_air"])
        self.assertIn(f"+{py_air['add_topup_air']:.0f} psi (to 2640 psi)", out["zero_he_air"])

        # Case 3: Residual EAN36 @ 2500 psi -> Target EAN32 @ 3000 psi -> 300 psi bleed-down
        py_bleed = p.calculate_gas_blender(
            mode="partial_pressure", start_pressure=2500, start_f_o2=0.36, start_f_he=0.0,
            target_pressure=3000, target_f_o2=0.32, target_f_he=0.0, cylinder_preset="AL80",
        )
        self.assertIn("EAN36 @ 2500 psi", out["partial_bleed_ean36_to_ean32"])
        self.assertIn(f"<td>{py_bleed['bleed_down_amount']:.0f} psi</td>", out["partial_bleed_ean36_to_ean32"])
        self.assertIn(f"<td>{py_bleed['usable_initial_pressure']:.0f} psi</td>", out["partial_bleed_ean36_to_ean32"])
        self.assertIn(f"+{py_bleed['add_topup_air']:.0f} psi (to 3000 psi)", out["partial_bleed_ean36_to_ean32"])

        # Case 4: Empty start (0 psi) -> Target EAN32 @ 3000 psi
        py_empty = p.calculate_gas_blender(
            mode="partial_pressure", start_pressure=0, start_f_o2=0.21, start_f_he=0.0,
            target_pressure=3000, target_f_o2=0.32, target_f_he=0.0, cylinder_preset="AL80",
        )
        self.assertIn("Empty (0 psi)", out["empty_start_to_ean32"])
        self.assertIn(f"+{py_empty['add_oxygen']:.0f} psi", out["empty_start_to_ean32"])
        self.assertIn(f"+{py_empty['add_topup_air']:.0f} psi", out["empty_start_to_ean32"])

        # Case 5: Default Trimix cascade (Tx 18/45 @ 500 psi -> Tx 21/35 @ 2640 psi)
        py_tx = p.calculate_gas_blender(
            mode="partial_pressure", start_pressure=500, start_f_o2=0.18, start_f_he=0.45,
            target_pressure=2640, target_f_o2=0.21, target_f_he=0.35, cylinder_preset="2xLP85",
        )
        self.assertIn("<td><strong>Tx 21/35</strong></td>", out["default_trimix_cascade"])
        self.assertIn(f"+{py_tx['add_helium']:.0f} psi", out["default_trimix_cascade"])
        self.assertIn(f"+{py_tx['add_oxygen']:.0f} psi", out["default_trimix_cascade"])
        self.assertIn(f"+{py_tx['add_topup_air']:.0f} psi", out["default_trimix_cascade"])

        # Case 6 & 7: Impossible Air top-up and invalid gas sum alerts
        self.assertIn("[BLEND IMPOSSIBLE]", out["impossible_air_topup"])
        self.assertIn("[INVALID GAS MIX]", out["invalid_sum_over_100"])

        # Case 8: Tab 4 Rock Bottom — Rule of Thirds governs, Rock Bottom governs (switch=0), and Sync from Plan
        py_rb_thirds = p.solve_rock_bottom(
            depth=180.0, bottom_time_min=25.0, cylinder_preset="2xLP85",
            fill_pressure_psi=2640.0, first_switch_depth=70.0, stressed_rmv_per_diver=1.00,
        )
        self.assertIn("[RULE OF THIRDS]", out["u4_thirds_governs"])
        self.assertIn(f"<strong>{py_rb_thirds['effective_turn_pressure_psi']:.0f} psi</strong>", out["u4_thirds_governs"])

        py_rb_gov = p.solve_rock_bottom(
            depth=130.0, bottom_time_min=20.0, cylinder_preset="AL80",
            fill_pressure_psi=3000.0, first_switch_depth=0.0, stressed_rmv_per_diver=1.00,
        )
        self.assertIn("ascent to 0ft", out["u4_switch_depth_zero"])
        self.assertNotIn("ascent to 70ft", out["u4_switch_depth_zero"])
        self.assertIn("[ROCK BOTTOM GOVERNS]", out["u4_switch_depth_zero"])
        self.assertIn("[ROCK BOTTOM EXCEEDS THIRDS]", out["u4_switch_depth_zero"])
        self.assertIn(f"<strong>{py_rb_gov['effective_turn_pressure_psi']:.0f} psi</strong>", out["u4_switch_depth_zero"])
        self.assertEqual(str(out["u4_synced_depth"]), "200")
        self.assertEqual(str(out["u4_synced_switch"]), "70")

        # Tab 5: Repetitive / Surface Interval CNS % decay (60% over 90 min -> 30.0%)
        self.assertIn("<td><strong>30.0%</strong></td>", out["u5_si_decay"])
        self.assertIn("<td>1.00x</td>", out["u5_si_decay"])

        # Case 9-12: Best Mix Gas Mode toggle (Nitrox/Air Only vs Trimix) parity with Python engine
        bm100 = out["bestmix_100_nitrox"]
        py_bm100 = p.calculate_best_mix_for_depth(100.0, max_po2_ata=1.40, max_end=100.0, allow_helium=False)
        self.assertEqual(bm100["nitroxPressed"], "true")
        self.assertEqual(bm100["trimixPressed"], "false")
        self.assertEqual(bm100["endLabel"], "Max END Alert Threshold")
        self.assertIn(f"<td><strong>{py_bm100['best_mix_name']}</strong></td>", bm100["html"])
        self.assertIn("<td>0%</td>", bm100["html"])
        self.assertIn("[GAS DENSITY CAUTION]", bm100["html"])

        bm130 = out["bestmix_130_nitrox"]
        py_bm130 = p.calculate_best_mix_for_depth(130.0, max_po2_ata=1.40, max_end=100.0, allow_helium=False)
        self.assertIn(f"<td><strong>{py_bm130['best_mix_name']}</strong></td>", bm130["html"])
        self.assertIn("[NARCOSIS WARNING]", bm130["html"])
        self.assertIn("[CRITICAL GAS DENSITY]", bm130["html"])

        bm200_no_he = out["bestmix_200_nitrox"]
        self.assertIn("[TRIMIX / SHALLOWER DEPTH REQUIRED]", bm200_no_he["html"])

        bm200_tx = out["bestmix_200_trimix"]
        py_bm200_tx = p.calculate_best_mix_for_depth(200.0, max_po2_ata=1.40, max_end=100.0, allow_helium=True)
        self.assertEqual(bm200_tx["trimixPressed"], "true")
        self.assertEqual(bm200_tx["endLabel"], "Target Max END")
        self.assertIn(f"<td><strong>{py_bm200_tx['best_mix_name']}</strong></td>", bm200_tx["html"])


if __name__ == "__main__":
    unittest.main()
