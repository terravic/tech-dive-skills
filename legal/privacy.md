# Privacy Policy

> **DRAFT — REQUIRES LEGAL REVIEW**
> This document is a draft template for open-source distribution and does not constitute legal advice. Obtain review from qualified legal counsel before operating any hosted deployment or commercial service.

**Maintainers:** `tech-dive-skills` Open-Source Contributors  
**Repository & Issue Tracker:** `https://github.com/terravic/tech-dive-skills/issues`  
**License:** Apache License, Version 2.0 (`LICENSE`)

---

## 1. Scope

This Privacy Policy applies to the `tech-dive-planner` (`tech-dive-skills`) open-source command-line software (`scripts/zhl16c_planner.py`), dashboard generator (`scripts/build_dashboard.py`), and standalone offline HTML dashboard (`dashboard.html`).

## 2. Data Collection and Local-Only Processing

* **Zero Server-Side Data Collection:** The software executes locally on the user's device. The `tech-dive-skills` Open-Source Contributors do not operate a backend server, user account database, telemetry service, or analytics pipeline for this repository.
* **Zero Personal Data Transmission:** Neither the Python scripts nor `dashboard.html` transmit dive profiles, IP addresses, device identifiers, or usage metrics to the contributors or any third party.
* **Local Browser Storage (`dashboard.html`):** When opened in a web browser, `dashboard.html` stores only user-initiated configuration state locally via browser `localStorage`:
  * `zhl16c-custom-profiles`: Dive plan parameters explicitly saved or imported by the user.
  * `theme-preference`: Selected visual appearance mode (`light`, `dark`, or `system`).
* **Local JSON Files (CLI):** When invoking CLI profile subcommands (`profiles --action save|delete` or `plan --save-profile-id`), dive configuration parameters are written strictly to the local JSON file specified by the user (default: `assets/synthetic_dive_profiles.json`).

## 3. Third-Party Processors and External Network Resources

* **Discovered Third-Party Processors:** None.
* **External Fonts, CDNs, and Embeds:** None. `dashboard.html` enforces a browser Content Security Policy (`default-src 'none'; connect-src 'none'`) and performs zero outbound network requests.
* **Cross-Border Data Transfers:** Not applicable to local offline execution.

## 4. Local Data Controls (Portability and Erasure)

Because all data remains strictly on the user's local device:

* **Data Portability (Export):** Export browser-saved dive profiles in machine-readable JSON format at any time via the `Export` button in `dashboard.html` or by reading `assets/synthetic_dive_profiles.json`.
* **Erasure (Deletion):** Delete an individual saved profile via the `Delete` button, erase all locally stored profiles and theme preferences via the `Clear Local Data` button in `dashboard.html`, or delete CLI profiles via `python3 scripts/zhl16c_planner.py profiles --action delete`.

## 5. Downstream Hosted Deployments

If any third party hosts `dashboard.html` or wraps this open-source software in an online service, that downstream operator acts as an independent data controller and is solely responsible for publishing its own legal entity details, contact channel, hosting region, Data Processing Agreements (DPAs), and cross-border transfer disclosures prior to launch.
