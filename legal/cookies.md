# Cookie and Local Storage Policy

> **DRAFT — REQUIRES LEGAL REVIEW**
> This document is a draft template for open-source distribution and does not constitute legal advice. Obtain review from qualified legal counsel before operating any hosted deployment.

**Maintainers:** `tech-dive-skills` Open-Source Contributors  
**Repository:** `https://github.com/terravic/tech-dive-skills`  
**License:** Apache License, Version 2.0 (`LICENSE`)

---

## 1. HTTP Cookies

Neither the Python CLI scripts (`scripts/zhl16c_planner.py`, `scripts/build_dashboard.py`) nor the standalone offline dashboard (`dashboard.html`) sets, reads, or transmits first-party or third-party HTTP cookies.

## 2. Browser `localStorage` Usage

When `dashboard.html` is opened locally in a web browser, it may store two user-initiated keys in browser `localStorage` exclusively on the user's device:

| Storage Key | Purpose | Category | Retention | Shared With Third Parties |
|---|---|---|---|---|
| `theme-preference` | Remembers the user's selected theme (`light`, `dark`, or `system`). | Local Preference | Until cleared by user or browser | No |
| `zhl16c-custom-profiles` | Stores dive profiles explicitly saved or imported by the user in the browser. | User-Requested Local State | Until deleted or cleared by user | No |

## 3. Managing and Clearing Local Storage

Users can clear both `localStorage` keys at any time by clicking **`Clear Local Data`** in the top navigation bar of `dashboard.html` or by clearing browser site data. No tracking pixels, advertising identifiers, third-party scripts, or external web fonts are loaded.
