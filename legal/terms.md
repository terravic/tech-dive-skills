# Terms of Use

> **DRAFT — REQUIRES LEGAL REVIEW**
> This document is a draft template for open-source distribution and does not constitute legal advice or a guaranteed liability shield. Enforceability of personal-injury, negligence, and assumption-of-risk disclaimers varies by jurisdiction. Obtain review from qualified legal counsel before relying on these terms in production, hosted, or commercial contexts.

**Licensors:** `tech-dive-skills` Open-Source Contributors  
**Repository:** `https://github.com/terravic/tech-dive-skills`  
**License:** Apache License, Version 2.0 (`LICENSE` and companion `NOTICE`)

---

## 1. Open-Source Software License

The `tech-dive-planner` (`tech-dive-skills`) source code, schemas, dashboard templates, and documentation are distributed under the **Apache License, Version 2.0** (see [`LICENSE`](../LICENSE)) together with the companion attribution and safety notice file ([`NOTICE`](../NOTICE)) issued under Apache License 2.0 Section 4(d). Use, reproduction, modification, contribution, and redistribution of this software are governed by the terms and conditions of the Apache License, Version 2.0. Any redistribution of this software or derivative works must retain `LICENSE` and `NOTICE` in accordance with Apache License 2.0 Section 4.

## 2. Mandatory Independent Verification and Dive Professional / Instructor Confirmation

* **Theoretical Estimates Only:** This software generates theoretical mathematical estimates and is **not** a certified dive computer, medical device, or life-support system.
* **Independent Cross-Check Required:** Before diving or blending breathing gas based on any schedule, gas reserve calculation, bailout plan, or blending recipe produced by this software, you **must independently verify** every input parameter and numerical output against a certified dive computer, redundant decompression planning software, or recognized diving agency tables.
* **Dive Professional / Instructor Confirmation Required:** You **must review and confirm** any generated dive plan, decompression schedule, bailout plan, or gas-blending procedure with a certified dive professional, qualified technical diving instructor, or certified gas blender prior to diving or filling cylinders.

## 3. Acknowledgment of Inherent Risks

Open-circuit (`OC`) scuba diving, closed-circuit rebreather (`CCR`) diving, staged decompression diving, altitude diving, and high-pressure nitrox/trimix/oxygen gas blending are inherently hazardous activities. Participation in these activities exposes divers and gas blenders to serious risks that can result in severe personal injury, permanent disability, or death, including without limitation:

* Decompression sickness (`DCS`), arterial gas embolism (`AGE`), and pulmonary or ear/sinus barotrauma;
* Central nervous system (`CNS`) oxygen toxicity (including underwater convulsions and drowning) and pulmonary oxygen toxicity;
* Hypoxia, hypercapnia (carbon dioxide retention), and inert gas narcosis;
* High work of breathing caused by elevated breathing gas density, regulator free-flow or malfunction, gas supply exhaustion, or breathing the wrong cylinder at depth;
* Closed-circuit rebreather loop hypoxia/hyperoxia, oxygen sensor failure, carbon dioxide scrubber breakthrough, flooding, or bailout failure; and
* Oxygen-enriched fire, adiabatic compression ignition, or high-pressure cylinder rupture during gas handling and partial-pressure blending.

## 4. Theoretical Model Limitations and No Physiological Guarantee

* **Mathematical Models Implemented:** Calculations rely strictly on published mathematical approximations: **Bühlmann ZH-L16C** (`1b` and `1`), **Haldane** and **Schreiner** inert gas transport equations, **Erik C. Baker Gradient Factors** (`GF Low` / `GF High`), **NOAA CNS %** 7-segment piecewise linear oxygen toxicity with 90-minute surface interval decay, **Lambertsen/Baker OTU**, **UHMS/DAN** gas density reference thresholds (`5.2 g/L` and `6.2 g/L`), and **Real-Gas Virial Z-factor** compressibility equations.
* **No Guarantee of Physiological Safety:** Decompression algorithms and oxygen toxicity indices do not account for individual physiology, hydration, thermal stress, exertion, patent foramen ovale (PFO), medication, fatigue, illness, or environmental hazards. **Decompression sickness, oxygen toxicity, or other diving injuries can occur even when a diver strictly follows a computed dive plan within published model limits.**

## 5. Diver Certification, Medical Fitness, Physical Gas Analysis, and AI Verification

* **Training and Medical Fitness:** You must hold appropriate, current certification from a recognized scuba training agency for the depth, decompression obligation, breathing gas, and equipment configuration planned, maintain medical fitness to dive (for example, meeting Recreational Scuba Training Council (RSTC) Diver Medical screening standards and physician clearance where required), dive with redundant instrumentation and conservative gas reserves, and follow recognized safe-diving practices.
* **Mandatory Physical Gas Analysis and Labeling:** Every breathing gas cylinder filled or used in connection with any plan or blending recipe from this software **must be personally and physically analyzed** using a calibrated oxygen analyzer (and calibrated helium analyzer for trimix/heliox) and clearly marked with its gas composition, date, analyst initials, and Maximum Operating Depth (`MOD`) before diving. Never rely solely on calculated blending pressures or verbal assurances.
* **AI Agent and Automated Workflow Warning:** When this skill is invoked through a conversational AI agent or automated harness, natural-language summaries may introduce transcription, unit-conversion, or interpretation errors. Users must inspect and verify the exact numerical inputs and outputs produced by `scripts/zhl16c_planner.py` directly.

## 6. Voluntary Assumption of Risk, "AS IS" Warranty Disclaimer, Limitation of Liability, and Downstream Operators

* **Voluntary Assumption of Risk:** By using this software, its CLI outputs, exported JSON files, or printed dashboard schedules, you acknowledge and voluntarily assume all risks associated with scuba diving, decompression planning, and high-pressure gas blending, and accept sole responsibility for your diving decisions and safety.
* **"AS IS" Disclaimer and Limitation of Liability (Apache License 2.0 Sections 7 and 8):** Consistent with Sections 7 and 8 of the Apache License, Version 2.0, the `tech-dive-skills` Open-Source Contributors provide this software on an **"AS IS"** basis, without warranties or conditions of any kind, either express or implied (including without limitation any warranties of title, non-infringement, merchantability, accuracy, or fitness for a particular purpose). Unless required by applicable law or agreed to in writing, in no event and under no legal theory (whether in tort, including negligence, contract, or otherwise) shall any contributor be liable to you for any direct, indirect, special, incidental, consequential, property, or personal-injury damages arising from the use of or inability to use this software, even if advised of the possibility of such damages.
* **Severability:** These disclaimers and liability limitations apply to the maximum extent permitted by applicable law. If any provision is held unenforceable in a given jurisdiction, the remaining provisions continue in full force and effect to the fullest extent permitted by law.
* **Downstream Hosted or Commercial Services:** Any downstream party that deploys this software as a hosted service, dive-shop tool, or commercial product is solely responsible for establishing its own legal entity identification, governing jurisdiction, participant liability waivers, and service terms in compliance with Apache License 2.0 Section 9, and may not represent any contributor as endorsing or warranting its deployment.
