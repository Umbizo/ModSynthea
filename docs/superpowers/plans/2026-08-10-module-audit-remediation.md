# ModSynthea Module Audit Remediation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate every finding in the 2026-08-10 module audit (`~/dev/srdc_pipelines/reference/modsynthea_module_audit.md`) so ModSynthea can regenerate claims data with no encounter-lock starvation, no generation crashes, and epidemiology within defensible bounds.

**Architecture:** Phase 0 builds the verification harness (upgraded lock linter, recursive code-map scanner, smoke-generation checker). Phases 1–2 make regeneration *safe* (kill every encounter lock and crash landmine), fixing each module completely while it is open — locks, incidence, wiring, rates, and codes in one commit per module. Phase 3 remediates the remaining modules. Phase 4 holds the two ground-up rewrites (own sub-plans). Phase 5 fixes cross-module coordination, Phase 6 sweeps code mappings, Phase 7 is the full verification regen and PR.

**Tech Stack:** Synthea GMF JSON modules (engine semantics per `State.java` / `HealthRecord.java`), Python 3 lint/scan tooling in the repo root, `./run_synthea` (Gradle) for smoke generation, CSV exporter output for assertions.

**Repo:** `~/dev/ModSynthea`, branch `fix/module-audit-remediation` (cut from `master` @ `feffd500`). All paths below are relative to the repo root. Modules live in `src/main/resources/modules/`, export maps in `src/main/resources/export/`.

## Global Constraints

Every task implicitly includes these. They come from the audit and from engine semantics verified against `State.java` / `HealthRecord.java`.

1. **Single encounter reservation per person.** Every path out of an opened `Encounter` state must reach `EncounterEnd`, `Terminal`, or `Death` **before crossing any `Delay` ≥ 1 day or any `Guard`** — for ambulatory/outpatient/virtual/urgentcare/wellness classes (and for encounters with *no* `encounter_class`, which silently default to AMBULATORY). Inpatient/SNF/hospice encounters may span a bounded length-of-stay delay but must still reach a closer.
2. **Banned idiom:** a `*_Supply_Delay` (30-day medication-supply delay) or any recovery/monitoring delay placed *inside* the open encounter. Pattern is always: orders → `EncounterEnd` → delay → next encounter.
3. **Medication codes are prescribable SCD/SBD RxNorm codes**, never ingredient-level CUIs (model to copy: ALL's `1863354`). `administration: true` only for clinician-administered infusions that have a J-code in `export/rxnorm_hcpcs_map.json`; oral/self-administered drugs are dispensed prescriptions and must map in `export/medication_code_map.json`. Match the flag to the route.
4. **Terminology systems:** conditions/procedures use `SNOMED-CT` (the exporter maps SNOMED→ICD-10/HCPCS via the export maps); observations use `LOINC`. Never `"system": "CPT"` or ICD-10 codes directly in GMF — they bypass the mappers invisibly. Closing a gap by adding rows to the fork-owned export maps is allowed and expected.
5. **Incidence discipline:** no lifetime risk rolled at birth; gate by age/sex (and smoking where relevant); convert annual rates to per-pass probability as `p_pass = 1 − (1 − p_annual)^Δt_years`. Calibration targets in tasks are approximate epidemiology — cite the source in the module's `remarks` when implementing.
6. **Stacking discipline:** guard `ConditionOnset`/`MedicationOrder` states that sit inside loops with an attribute check so re-execution can't stack duplicates; every fixed-course drug gets a `MedicationEnd`; genuinely chronic drugs use `"chronic": true` and are *not* MedicationEnd'ed at 30 days.
7. `target_encounter` must name an encounter **state** (a string); the engine matches by state name — `0` silently never matches.
8. Every touched module declares `"gmf_version": 2` and keeps/adds sourced `remarks`.
9. **Any code introduced by this plan** (SNOMED/RxNorm/LOINC) must be verified before commit: SNOMED IDs pass the Verhoeff check (Task 0.2's scanner validates), and the code must resolve in the relevant export map (or a map row is added in the same commit). Where this plan suggests a specific code, treat it as a candidate to verify, not gospel.
10. **Commit protocol:** one commit per task minimum, conventional-commit style (`fix(module): …`, `feat(tools): …`), linter run clean (or expected-benign only) before every commit. Never batch multiple modules into one commit.

## Standard Module Remediation Cycle

Each Phase 1–3 task runs this cycle; the task supplies the specifics.

1. **RED** — `python3 tools_lint_module_locks.py src/main/resources/modules <module>.json` and `python3 tools_scan_unmapped_codes.py --module <module>.json`: confirm the findings the task lists (if a listed finding does not reproduce, stop and re-verify against the audit before editing).
2. **FIX** — apply the task's fix spec.
3. **GREEN** — re-run both tools: zero CRITICAL, zero un-triaged scan rows for the module.
4. **SMOKE** — `./tools_smoke_gen.sh 400` then the task's `tools_smoke_check.py` assertions; also confirm the run log has no exceptions.
5. **COMMIT** — `git add <files> && git commit -m "<task's message>"`.

## Baseline (recorded 2026-08-10, master @ feffd500)

`python3 tools_lint_module_locks.py` → **CRITICAL=43 WARNING=30** across the tree. Zero `EncounterEnd` states exist in prostate_cancer, polycystic_kidney_disease, CIDP, ovarian_cancer. `SLE.json:367` has `"target_encounter": 0`. `heart/chf_meds.json:22` branches on `chf_med_check` (everything else writes `chf_med_step`). parkinsons carries the intentional Verhoeff-failing placeholder (lines ~490–553). No generator for `unmapped_module_codes.csv` exists in the repo (it was a one-off script; the CSV is stale, top-level-only, 07-29).

Lint findings in **stock** modules (self_harm, veteran_ptsd, veteran_self_harm `Autopsy_Encounter`/`Inpatient_admission`) are out of scope: record them in the Phase 7 report as triaged-stock, do not edit those files.

---

## Phase 0 — Verification harness

### Task 0.1: Upgrade the lock linter

**Files:** Modify: `tools_lint_module_locks.py`

**Interfaces — Produces:** same CLI (`python3 tools_lint_module_locks.py [modules_dir] [name.json ...]`), exit 1 on any CRITICAL. All later tasks depend on the stricter semantics below.

Current gaps (audit process notes): it misses locks whose `EncounterEnd` sits *beyond* a blocking state (MCL pattern), and its warnings under-rank the `*_Supply_Delay` idiom.

- [ ] **Step 1: Add a closed-before-blocked reachability check.** Inside `analyze()`, replace the ambulatory-class logic so that for every opened `Encounter` state with class in `AMBULATORY` **or with no `encounter_class`**, it is CRITICAL when any path can reach a `Delay` ≥ 1 day or a `Guard` before reaching a closer:

```python
def closes_before_block(states, start):
    """True iff no path from `start` reaches a Delay >= 1 day or a Guard
    before reaching EncounterEnd/Terminal/Death or re-entering an Encounter
    (same-module re-entry releases the reservation)."""
    seen, stack, blockers = set(), list(targets(states[start])), []
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        v = states.get(name)
        if v is None:
            continue
        t = v.get('type')
        if t in CLOSERS or t == 'Encounter':
            continue
        if t == 'Guard' or (t == 'Delay' and delay_ms(v) >= DAY):
            blockers.append((name, t))
            continue
        stack.extend(targets(v))
    return (not blockers), blockers
```

For inpatient/snf/hospice classes keep the existing rule (CRITICAL only when no closer is reachable at all) and add WARNING when open across a delay > 90 days.

- [ ] **Step 2: Add the Supply-Delay idiom check.** While an encounter is open (any class), reaching a state whose name matches `*_Supply_Delay` is CRITICAL (it is always the banned idiom, never a length of stay).
- [ ] **Step 3: Verify against known cases (red/green for the tool itself).** Run `python3 tools_lint_module_locks.py`. Expected: mantle_cell_lymphoma's `Clinical_Trial_Treatment` and `Salvage_Chemotherapy` are now CRITICAL (were WARNING); right_sided/valvular/chf `*_Supply_Delay` findings are now CRITICAL; congestive_heart_failure's `Encounter → scheduled Death → Terminal` hospice pattern is **not** flagged. Total CRITICAL rises above 43. Record the new totals in this plan's Baseline section.
- [ ] **Step 4: Commit.** `git add tools_lint_module_locks.py docs/superpowers/plans/2026-08-10-module-audit-remediation.md && git commit -m "feat(tools): lint closed-before-blocked encounters and Supply_Delay idiom"`

### Task 0.2: Recursive unmapped-code scanner

**Files:** Create: `tools_scan_unmapped_codes.py`

**Interfaces — Produces:** `python3 tools_scan_unmapped_codes.py [--module name.json] [--csv unmapped_module_codes.csv]` — scans `src/main/resources/modules/**/*.json` (recursive — the stale CSV's top-level-only scan is the bug being fixed), exit 1 if any gap rows for the scanned scope. Gap kinds: `med->NDC` (MedicationOrder without `administration` whose code is missing from `medication_code_map.json`), `admin-med->HCPCS` (with `administration: true`, missing from `rxnorm_hcpcs_map.json`), `condition->ICD` (ConditionOnset code missing from `condition_code_map.json`), `procedure->HCPCS` (Procedure code missing from `hcpcs_code_map.json`), `bad-system` (any `"system"` outside `{SNOMED-CT, RxNorm, LOINC, CVX, DICOM-DCM, DICOM-SOP}`), `bad-verhoeff` (SNOMED code failing its check digit), `bad-gmf` (a `SetAttribute` with `value_set`, or an `Observation` with a raw `"value"` block — the Gson-silently-dropped syntax from the audit).

- [ ] **Step 1: Write the scanner.** All four export maps are dicts keyed by source code (verified 2026-08-10), so membership is `str(code) in map`:

```python
#!/usr/bin/env python3
"""Scan modules (recursively) for codes the RIF export maps cannot map."""
import argparse, csv, glob, json, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.join(ROOT, 'src', 'main', 'resources', 'modules')
EXP = os.path.join(ROOT, 'src', 'main', 'resources', 'export')
OK_SYSTEMS = {'SNOMED-CT', 'RxNorm', 'LOINC', 'CVX', 'DICOM-DCM', 'DICOM-SOP'}

_d = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],
      [3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],
      [6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],
      [9,8,7,6,5,4,3,2,1,0]]
_p = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],
      [8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],
      [2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]]

def verhoeff_ok(num):
    c = 0
    for i, ch in enumerate(reversed(str(num))):
        if not ch.isdigit():
            return False
        c = _d[c][_p[i % 8][int(ch)]]
    return c == 0

def load(name):
    with open(os.path.join(EXP, name)) as f:
        return json.load(f)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--module', action='append', default=[],
                    help='relative module path(s) to scan; default all')
    ap.add_argument('--csv', help='also write full-tree results to this CSV')
    args = ap.parse_args()
    med, jmap = load('medication_code_map.json'), load('rxnorm_hcpcs_map.json')
    cond, proc = load('condition_code_map.json'), load('hcpcs_code_map.json')
    rows = []
    for f in sorted(glob.glob(os.path.join(MOD, '**', '*.json'), recursive=True)):
        rel = os.path.relpath(f, MOD)
        if os.path.sep in rel and rel.split(os.path.sep)[0] == 'lookup_tables':
            continue
        if args.module and rel not in args.module:
            continue
        try:
            with open(f) as fh:
                mod = json.load(fh)
        except Exception as e:
            rows.append(('parse-error', '', str(e), rel)); continue
        for sname, st in (mod.get('states') or {}).items():
            t = st.get('type')
            if t == 'SetAttribute' and 'value_set' in st:
                rows.append(('bad-gmf', sname, 'SetAttribute value_set', rel))
            if t == 'Observation' and isinstance(st.get('value'), dict):
                rows.append(('bad-gmf', sname, 'Observation raw value block', rel))
            for c in st.get('codes', []) or []:
                code, system = str(c.get('code', '')), c.get('system', '')
                disp = c.get('display', '')
                if system not in OK_SYSTEMS:
                    rows.append(('bad-system', sname, f'{system}:{code} {disp}', rel))
                    continue
                if system == 'SNOMED-CT' and not verhoeff_ok(code):
                    rows.append(('bad-verhoeff', sname, f'{code} {disp}', rel))
                if t == 'MedicationOrder':
                    if st.get('administration'):
                        if code not in jmap:
                            rows.append(('admin-med->HCPCS', sname, f'{code} {disp}', rel))
                    elif code not in med:
                        rows.append(('med->NDC', sname, f'{code} {disp}', rel))
                elif t == 'ConditionOnset' and code not in cond:
                    rows.append(('condition->ICD', sname, f'{code} {disp}', rel))
                elif t == 'Procedure' and code not in proc:
                    rows.append(('procedure->HCPCS', sname, f'{code} {disp}', rel))
    for r in rows:
        print(f'{r[0]:>20}  {r[3]}  [{r[1]}]  {r[2]}')
    if args.csv:
        with open(args.csv, 'w', newline='') as fh:
            w = csv.writer(fh)
            w.writerow(['gap', 'state', 'code', 'module'])
            w.writerows(rows)
    print(f'\n{len(rows)} gaps')
    return 1 if rows else 0

if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 2: Verify.** `python3 tools_scan_unmapped_codes.py --csv unmapped_module_codes.csv`. Expected: rows for `eye/` subfolder modules and wet_amd's anti-VEGF codes appear (the stale CSV never scanned them); **no** `admin-med->HCPCS` row for daratumumab `1721947` (the 07-24 J-code fix is live per audit); `bad-gmf` rows for non_small_cell_lung_cancer (`value_set`) and right_sided/valvular (`Observation` value blocks); `bad-system` rows for endometrial/pneumonia/alzheimers/parkinsons CPT entries; parkinsons' placeholder appears as `bad-verhoeff`.
- [ ] **Step 3: Commit.** `git add tools_scan_unmapped_codes.py unmapped_module_codes.csv && git commit -m "feat(tools): recursive unmapped-code scanner; regenerate unmapped_module_codes.csv"`

### Task 0.3: Smoke-generation harness

**Files:** Create: `tools_smoke_gen.sh`, `tools_smoke_check.py`

**Interfaces — Produces:** `./tools_smoke_gen.sh [population]` → CSV output under `output/smoke/csv/`, log at `output/smoke_run.log`, fails on any exception. `python3 tools_smoke_check.py --code <SNOMED> [--sex M|F] [--eligible-min-age N] [--min-share X] [--max-share X] [--min-onset-age N] [--max-onset-age N] [--mean-encounters-min N] [--top-share-max X]` → exit 1 on any violated bound. Every later task's SMOKE step uses these.

- [ ] **Step 1: Write `tools_smoke_gen.sh`:**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
rm -rf output/smoke
./run_synthea -p "${1:-400}" -s 4444 \
  --exporter.baseDirectory "output/smoke/" \
  --exporter.csv.export true \
  2>&1 | tee output/smoke_run.log
! grep -E "Exception|StackTrace|	at " output/smoke_run.log
```

- [ ] **Step 2: Write `tools_smoke_check.py`.** Read `output/smoke/csv/patients.csv`, `conditions.csv`, `encounters.csv` with case-insensitive column lookup (`Id`/`PATIENT`/`BIRTHDATE`/`DEATHDATE`/`GENDER`/`CODE`/`START`). Compute per patient: age at sim end (DEATHDATE or max encounter STOP, minus BIRTHDATE, in years) and age at first onset of `--code`. Assertions: share of the eligible population (after `--sex`/`--eligible-min-age` filters) with ≥1 dx of `--code` within `[--min-share, --max-share]`; onset-age percentiles within `[--min-onset-age, --max-onset-age]` (5th/95th percentile respectively); `--mean-encounters-min`: mean encounter rows per patient ≥ N; `--top-share-max`: no single condition code exceeds X share of all condition rows. Print each computed value next to its bound; exit 1 listing every violated bound.
- [ ] **Step 3: Record the pre-fix baseline (RED for all of Phase 1).** `chmod +x tools_smoke_gen.sh && ./tools_smoke_gen.sh 400`, then `python3 tools_smoke_check.py --code 399068003 --sex M --eligible-min-age 55 --max-share 0.20 --mean-encounters-min 30 --top-share-max 0.05 | tee docs/superpowers/plans/2026-08-10-baseline-smoke.txt`. Expected: FAIL (prostate share and/or starved encounter mean) — that failure output is the baseline artifact.
- [ ] **Step 4: Commit.** `git add tools_smoke_gen.sh tools_smoke_check.py docs/superpowers/plans/2026-08-10-baseline-smoke.txt && git commit -m "feat(tools): smoke generation harness and epidemiology bounds checker"`

---

## Phase 1 — The ten do-not-regenerate modules

One task per module. Each task fixes **everything** the audit found in that module (lock + incidence + wiring + rates + codes), runs the Standard Cycle, and lands one commit. After Task 1.10, run `./tools_smoke_gen.sh 1000` and require `--mean-encounters-min 30 --top-share-max 0.05` to PASS — that is the phase gate proving starvation is gone.

### Task 1.1: prostate_cancer.json (worst in audit)

**Defects:** zero `EncounterEnd` in file — `Screening_Discussion` opens ~age 55 and the PSA loop holds the reservation to death (~60% of all men, permanently); `Treatment_Discussion` likewise for diagnosed patients. 3%/yr screened conversion with no age-out → ~28% of men diagnosed (~2.2× real). Recurrence 0.2/yr → ~89% by 10 yr (real ~30%); castration-resistance 0.6/pass with no other exit; every diagnosed patient funnels to prostate-cancer death.

- [ ] **Fix — close every visit:** after `Screening_Discussion`'s content states, insert `End_Screening_Visit` (`{"type": "EncounterEnd", "direct_transition": "PSA_Interval_Delay"}`); the annual PSA loop becomes Delay → re-open Encounter → PSA → close. Same shape for `Treatment_Discussion` → `End_Treatment_Visit`. Every Delay in the file must sit between an `EncounterEnd` and the next `Encounter`.
- [ ] **Fix — screening window:** Guard age ≥ 55 to enter; conditional exit from the screening loop at age ≥ 70 → `Terminal`.
- [ ] **Fix — calibration:** annual dx probability while screened 0.009 (lifetime ~13%); biochemical recurrence per-pass from 3.5%/yr (~30%/10 yr) with a 10-year discharge-to-surveillance exit; CRPC from recurrence at 3%/yr with explicit non-CRPC exits (stable-on-ADT, other-cause death); prostate-cancer death only from the metastatic/CRPC arm (~5%/yr there), everyone else exits to surveillance/Terminal.
- [ ] **Verify:** lint RED `Screening_Discussion`/`Treatment_Discussion` CRITICAL → GREEN 0. Smoke: `python3 tools_smoke_check.py --code 399068003 --sex M --eligible-min-age 55 --min-share 0.06 --max-share 0.18 --min-onset-age 50`.
- [ ] **Commit:** `fix(prostate_cancer): close screening/treatment encounters, gate screening 55-69, calibrate incidence/recurrence/mortality`

### Task 1.2: polycystic_kidney_disease.json

**Defects:** zero `EncounterEnd`; `Acute_Care_Encounter`/`PCP_Encounter` (lint CRITICALs) hold the lock across decades of CKD/dialysis/transplant Delays (~0.15% of population). Admissions coded to the wrong claim stream. Sets capitalized `"Hypertension"` attribute stock modules can't see. Lisinopril `29046` is an ingredient CUI.

- [ ] **Fix:** close both encounters before any progression Delay; model the decades-long course as closed visits separated by Delays (each CKD-stage review its own open→close encounter). Acute admissions get `"encounter_class": "inpatient"` with a bounded LOS then `EncounterEnd`. Replace attribute `"Hypertension"` with the stock-visible lowercase `"hypertension"` at both write sites. Replace `29046` with the lisinopril 10 MG oral tablet SCD (candidate `314076` — verify per Global Constraint 9; add a `medication_code_map.json` row if absent).
- [ ] **Verify:** lint 2 CRITICAL → 0; scanner `med->NDC` row for 29046 gone. Smoke: mean-encounters floor passes; PKD onset ages plausible (`--code` = the module's ADPKD SNOMED, `--max-share 0.004`).
- [ ] **Commit:** `fix(polycystic_kidney_disease): close encounters, inpatient admissions, stock-visible hypertension attr, SCD lisinopril`

### Task 1.3: CIDP.json

**Defects:** zero `EncounterEnd`; monitoring loop's 1%/cycle exit holds the lock a median ~24 years; incidence typo `0.002` vs remarked 2/100k (100×); duplicate stacking in loops. "The next HOHF."

- [ ] **Fix:** incidence `0.002` → `0.00002`, gated to ages 30+ (peak 40–60). Close every monitoring visit; loop = Delay(3 mo) → Encounter → assess → EncounterEnd. Replace the 1%/cycle exit with real outcomes per quarterly pass: remission 5%, continue 94%, death-other 1%. Guard loop-resident `ConditionOnset`/`MedicationOrder` states with attribute checks; IVIG as `administration: true` with J-code map row; oral drugs (azathioprine, pyridostigmine, mycophenolate) as SCD dispensed prescriptions.
- [ ] **Verify:** lint CRITICAL → 0; scanner rows for the five CIDP drugs cleared. Smoke: `--max-share 0.0005` for the CIDP SNOMED code.
- [ ] **Commit:** `fix(CIDP): 100x incidence typo, close monitoring encounters, realistic loop exits, mapped drug codes`

### Task 1.4: ovarian_cancer.json

**Defects:** zero `EncounterEnd`; high-risk arm holds a wellness encounter through lifelong surveillance (~1% of women, to death). 99.05% of women structurally immune; BRCA arm converts ~100% by 48 (~90% of cases BRCA). 25% recurrence per 4.5-month pass, no remission exit → 100% disease mortality stamped same-instant as recurrence. Drugs unmapped.

- [ ] **Fix:** close every encounter (surveillance = q6mo Delay → Encounter → imaging/CA-125 → EncounterEnd loop). General-population arm: annual incidence 1e-4 at 45 rising to 3e-4 at 60–75 (lifetime ~1.3%); BRCA-carrier arm ~2%/yr from 40 (lifetime ~40%), carriers ~0.3% of women. Recurrence per-pass from ~20%/yr platinum-sensitive with a remission exit; recurrence → 6–24 months of treatment/hospice (closed encounters) before Death, never same-instant. Carboplatin/paclitaxel as `administration: true` with J-code rows; PARP inhibitors as SCD prescriptions.
- [ ] **Verify:** lint → 0; scanner rows cleared. Smoke: `--code` ovarian-CA SNOMED `--sex F --min-share 0.005 --max-share 0.03 --min-onset-age 35`.
- [ ] **Commit:** `fix(ovarian_cancer): close surveillance encounters, population+BRCA incidence, survivable recurrence, mapped drugs`

### Task 1.5: pneumonia.json

**Defects:** no incidence gate — 100% of patients at birth, once; encounters open across 37–72-day delays (lint: `OutpatientManagement` open across `AntibioticTreatmentOutpatient_Supply_Delay`, `Doxycycline_End_Delay`; `FollowUpCare` across `RecoveryMild`). ICD-10/CPT mixed into conditions/procedures. Doxycycline unmapped. Bookkeeping otherwise disciplined — keep the structure.

- [ ] **Fix:** replace the birth roll with an annual susceptibility loop: p_annual 0.015 under 5, 0.004 ages 5–64, 0.02 at 65+; allow repeat episodes. Reorder to orders → `EncounterEnd` → supply/recovery delays (kills both Supply_Delay CRITICALs and the RecoveryMild hold). Recode conditions/procedures to SNOMED-CT (map ICD-10/CPT strays via `condition_code_map.json`/`hcpcs_code_map.json` rows). Doxycycline 100 MG oral capsule SCD (candidate `1649988` — verify) with map row.
- [ ] **Verify:** lint → 0. Smoke: pneumonia SNOMED `--min-share 0.10 --max-share 0.45 --min-onset-age 1` (5th-percentile onset must clear infancy).
- [ ] **Commit:** `fix(pneumonia): annual age-shaped incidence, close encounters before recovery delays, SNOMED coding, mapped doxycycline`

### Task 1.6: alzheimers.json — containment hotfix (full rework is Task 4.2)

**Defects:** no gate — ~100% get MCI, ~5/6 progress to AD; end-stage unblocked loop leaks never-closed nursing-home/hospice encounters for life; no Death state; memantine stacking; CPT-system entries; infusions before InfusionProgram run with no encounter open.

- [ ] **Fix (containment only):** Guard age ≥ 65 + annual MCI incidence 1.5%/yr; MCI→AD 10%/yr; add a Death state (post-dx survival median ~6 yr via scheduled death from the end-stage arm). Close every nursing-home/hospice encounter in the end-stage loop (Delay-separated closed visits). Guard memantine order with an attribute. Wrap the pre-InfusionProgram infusions in an encounter or move them after it. Leave deeper redesign and dementia.json coordination to Task 4.2.
- [ ] **Verify:** lint → 0 for the module. Smoke: AD code 26929004 `--eligible-min-age 65 --max-share 0.15 --min-onset-age 60`.
- [ ] **Commit:** `fix(alzheimers): gate incidence, close end-stage encounters, add mortality (containment before full rework)`

### Task 1.7: heart/chf_meds.json + chf_meds_hfref_nyha2/3/4.json (+ chf_meds_hfmef.json check)

**Defects:** `chf_meds.json:22` branches on `chf_med_check` — nothing sets it (typo for `chf_med_step`) → titration frozen at step 1; MRA/ivabradine/BiDil/digoxin/ARNI dead. 30-day `*_Supply_Delay`s inside the encounter; NYHA≥2 submodules have no `EncounterEnd` and end via a 365-day `Terminal_Delay` → lock held ~13–20 months per maintenance cycle, called from inside congestive's own open encounter (every HFrEF NYHA≥2 patient; CHF ≈19% of adults). `chronic: true` GDMT MedicationEnd'ed at exactly 30 days → 1 fill/drug/yr. `EF Check`→`CKD Check` bypass strands the EF 36–40 chains.

- [ ] **Fix:** line 22 `"attribute": "chf_med_check"` → `"chf_med_step"`. Move every `*_Supply_Delay` after `EncounterEnd`. Add `EncounterEnd` to each NYHA submodule before its maintenance delay; replace `Terminal_Delay` (365 d) with EncounterEnd → Delay → Terminal. Delete the 30-day `MedicationEnd`s on `chronic: true` GDMT (chronic flag handles refills). Rewire `EF Check` so EF 36–40 reaches its chain. Verify the submodule call sites in congestive close congestive's encounter first (coordinate with Task 2.8).
- [ ] **Verify:** lint (all four files + congestive) → 0 CRITICAL. Smoke: mean encounter floor passes; in `output/smoke/csv/medications.csv`, GDMT drugs show multi-year spans (STOP−START > 300 days or blank STOP) instead of 30-day fills.
- [ ] **Commit:** `fix(chf_meds): chf_med_check typo, close NYHA submodule encounters, supply delays after close, chronic GDMT refills, EF 36-40 rewire`

### Task 1.8: pancreatic_cancer.json

**Defects:** `Staging_Workup` and `Incidental_Finding` never reach `EncounterEnd` (lint CRITICALs); all four arms delay weeks-to-years to Death/Terminal with the lock held. Annual 0.00013 rolled once at 50 → ~100× under, all onset exactly 50. Gemcitabine dispensed as an open-ended prescription (belongs on the J-code path). Pathway shape otherwise salvageable.

- [ ] **Fix:** close `Incidental_Finding` and `Staging_Workup` same-day (workup content then `EncounterEnd`); each treatment arm = cycles of closed encounters separated by Delays, terminal decline as closed hospice visits then Death. Incidence: annual loop from 45 — 5e-5 (45–54), 1.5e-4 (55–64), 3e-4 (65+). Gemcitabine → `administration: true` + `rxnorm_hcpcs_map.json` row (J9201), with `MedicationEnd` per fixed course.
- [ ] **Verify:** lint 2 CRITICAL → 0. Smoke: pancreatic-CA SNOMED `--min-share 0.005 --max-share 0.03 --min-onset-age 40 --max-onset-age 95` (onset spread, not spiked at 50).
- [ ] **Commit:** `fix(pancreatic_cancer): close workup/treatment encounters, age-shaped incidence, gemcitabine as administered J-code`

### Task 1.9: mantle_cell_lymphoma.json

**Defects:** lint CRITICALs `BR_Treatment`, `R_CHOP_Treatment`, `End_of_Life_Care`; `Clinical_Trial_Treatment` (6–18 mo) and `Salvage_Chemotherapy` (3–9 mo) open across Delays (CRITICAL after Task 0.1). Transplant arm {`Consider_Stem_Cell_Transplant`, `Autologous_SCT`, `Post_Transplant_Recovery`, `Maintenance_Therapy`} orphaned — zero ASCT, zero rituximab maintenance — and lacks an enclosing encounter. Up to 6 stacked open copies per chemo drug; second-line runs outside encounters. Incidence 8e-05 × 0.3 one-shot at 45 → 30–50× under. Clean surveillance visits record "Recurrent malignant neoplasm" (inverted).

- [ ] **Fix:** per-cycle encounter shape everywhere (Encounter → infusion → EncounterEnd → 21–28 d Delay → next cycle) for BR, R-CHOP, trial, salvage, and second line; `End_of_Life_Care` as closed hospice visits then Death. Wire `Check_First_Line_Cycles` / `Follow_Up_Period` CR/PR branch → `Consider_Stem_Cell_Transplant`, and give the ASCT arm its own inpatient encounter (open → conditioning + `Autologous_SCT` → EncounterEnd with LOS ~14–21 d) → `Post_Transplant_Recovery` (delay, no encounter) → `Maintenance_Therapy` (closed q8wk rituximab visits). Guard each chemo `MedicationOrder` with an attribute + `MedicationEnd` per cycle (max 1 open copy). Incidence: annual 1e-5 from age 50, male-weighted 3:1 (median dx ~68). Remove the recurrent-neoplasm observation from clean surveillance visits. Chemo/rituximab as `administration: true` with J-code rows; oral agents (ibrutinib etc.) as SCD prescriptions.
- [ ] **Verify:** lint 3+2 CRITICAL → 0. Smoke: in `medications.csv`, no drug shows >1 concurrent open order per patient; MCL SNOMED `--max-share 0.003 --min-onset-age 40`.
- [ ] **Commit:** `fix(mantle_cell_lymphoma): close treatment encounters, wire ASCT arm, dedupe chemo, calibrate incidence, fix surveillance coding`

### Task 1.10: bladder_cancer.json

**Defects:** `Hospice_Enrollment` (30–180 d) on **every** death path, `Intravesical` (~10 wk), `Medical_Oncology` (~13–16 wk) all hold the lock. Post-diagnosis chemo outside encounters. No age/smoking gate, lifelong annual rolls → ~25% male lifetime (~7× real), onset from infancy. ~40%/yr recurrence, ~12%/yr MIBC progression (real Ta-LG <1%/yr). Entire palliative subgraph dead; umbrella `Develop_Bladder_Cancer` ConditionOnset unreachable. Dropped-digit code `"122985900"`. Drugs unmapped.

- [ ] **Fix:** hospice = enrollment encounter (closed same-day) → Delay(30–180 d) with weekly closed hospice visits → Death. Intravesical = 6 weekly closed instillation encounters; Medical_Oncology = closed per-cycle encounters. Wrap all chemo in encounters. Gate: age ≥ 45, annual 1e-4 (45–64) → 1e-3 (75+) for males, ×0.25 female, ×2 smokers. Recurrence per-pass from 8%/6 mo NMIBC; Ta-LG progression 0.8%/yr. Wire the palliative referral subgraph (palliative visits before hospice, per the module's existing dead states). Wire or delete `Develop_Bladder_Cancer` (prefer: fire it as the umbrella dx at first site-specific diagnosis). Fix `122985900` to the intended Verhoeff-valid concept for its display (scanner gates this). BCG/gemcitabine intravesical as `administration: true` + J-code rows.
- [ ] **Verify:** lint → 0. Smoke: bladder-CA SNOMED `--sex M --min-share 0.01 --max-share 0.06 --min-onset-age 40`; hospice encounters exist but carrier/DME encounter mean unaffected.
- [ ] **Commit:** `fix(bladder_cancer): close hospice/intravesical/oncology encounters, gate incidence, wire palliative arm, fix codes`

### Phase 1 gate

- [ ] `python3 tools_lint_module_locks.py` → 0 CRITICAL outside stock modules. `./tools_smoke_gen.sh 1000` → no exceptions; `python3 tools_smoke_check.py --code 399068003 --sex M --eligible-min-age 55 --max-share 0.18 --mean-encounters-min 30 --top-share-max 0.05` → PASS. Commit the recorded gate output: `chore(audit): phase 1 gate - encounter starvation eliminated`.

---

## Phase 2 — Remaining locks, leaks, and crash landmines

Same Standard Cycle; one commit per task.

### Task 2.1: non_small_cell_lung_cancer.json — crash hotfix only

`SetAttribute` with `value_set` parses to a LinkedTreeMap; the Map-vs-String compare **throws at generation time**. Replace the `value_set` block with a plain `"value": "<one stage string>"` (pick the modal stage; the full rewrite in Task 4.1 restores the distribution properly via `distributed_transition` into separate SetAttribute states).
- [ ] Verify scanner `bad-gmf` row gone; smoke run has no NSCLC stack traces. Commit: `fix(nsclc): remove value_set crash landmine pending rewrite`

### Task 2.2: parkinsons.json

**Defects:** intentional Verhoeff-failing placeholder SNOMED in `AdvanceCarePlanning` on the mainline path (designed to fail ingestion loudly — must resolve before any regen); lint CRITICALs `PrimaryCareVisit` (open across 1–6 mo `NeurologyReferral`), `DBSFollowUp`, `PalliativeCareReferral`, `LongTermCare`, `MultidisciplinaryCare_Action_1`; `no_dementia`/`levodopa_response`/`dyskinesia_severe` never set → DBS and amantadine arms dead; `disease_duration_years` incremented exactly once → PD-dementia unreachable, 100% die of PD 5–8 yr post-dx; CPT-system entries.
- [ ] **Fix:** replace the placeholder with `371538006` (Advance directive discussion) — verify per Global Constraint 9 and the module's own remarks (lines ~490–553), adding a `hcpcs_code_map.json` row for it. Close `PrimaryCareVisit` before the referral Delay; close the other four flagged encounters. Set the three attributes at their clinical decision points (`levodopa_response` at initial treatment response, `dyskinesia_severe` in the motor-complication branch, `no_dementia` from the cognitive check); increment `disease_duration_years` inside the annual loop. Mortality: PD hazard ~2× background, PD-dementia arm reachable at ~10 yr duration. Recode CPT entries to SNOMED.
- [ ] Verify lint 5 CRITICAL → 0; scanner `bad-verhoeff` gone. Commit: `fix(parkinsons): resolve ACP placeholder, close encounters, wire progression attributes, SNOMED coding`

### Task 2.3: right_sided_heart_failure.json and Task 2.4: valvular_heart_failure.json

**Defects (each):** four 30-day `*_Supply_Delay`s inside `Initial_Cardiology_Encounter` (CRITICAL after 0.1); ~120-day onset encounter; 30–70-day admissions; invalid `Observation "value"` blocks → BNP/JVD/murmur record null; unsourced rates. Valvular additionally performs valve surgery with **no valve disease on record**. Both share `furosemide_40_mg_oral_tablet_rx`/`_2`/lisinopril attrs with chf_meds (renamed in Task 5.4).
- [ ] **Fix:** orders → `EncounterEnd` → supply delays; onset workup closed same-day; admissions as `inpatient` with bounded LOS. Observations: numeric → `"range": {"low": …, "high": …}` with LOINC + unit; qualitative (JVD, murmur) → `"value_code"` SNOMED. Valvular: add `ConditionOnset` before surgery — aortic stenosis `60573004` or mitral regurgitation `48724000` per arm (verify), targeting the diagnosis encounter. Add rate sources to remarks.
- [ ] Verify lint → 0; scanner `bad-gmf` rows gone. Commits: `fix(right_sided_heart_failure): …`, `fix(valvular_heart_failure): add valve diagnosis, …`

### Task 2.5: rheumatoid_arthritis.json

**Defects:** no `ConditionOnset` exists — every `reason: "Rheumatoid_Arthritis_Onset"` references a nonexistent state; RA is never recorded while methotrexate/prednisone/care plans are emitted. `Primary_Care_Visit` open across 3–6 mo `Watchful_Waiting` (CRITICAL); dead heuristic arm.
- [ ] **Fix:** create the state with the exact name every `reason` already references:

```json
"Rheumatoid_Arthritis_Onset": {
  "type": "ConditionOnset",
  "target_encounter": "Diagnosis_Encounter",
  "assign_to_attribute": "rheumatoid_arthritis",
  "codes": [{"system": "SNOMED-CT", "code": "69896004", "display": "Rheumatoid arthritis"}],
  "direct_transition": "Diagnosis_Encounter"
}
```

wired between symptom onset and the diagnosis encounter (retarget the transition currently entering that encounter; use the module's actual diagnosis-encounter state name for `target_encounter`). Close `Primary_Care_Visit` before `Watchful_Waiting`; rewire the dead heuristic arm per its evident intent.
- [ ] Verify lint → 0; smoke: RA code 69896004 now appears (`--min-share 0.002`). Commit: `fix(rheumatoid_arthritis): record the disease, close watchful-waiting encounter, revive dead arm`

### Task 2.6: acute_lymphoblastic_leukemia.json

**Defects:** 28-day induction lock; 365-day death delays; deaths coded 91861009 (acute **myeloid** leukemia); lifelong compounding incidence, no age shape (~5× over, elderly-skewed vs real peak 2–5).
- [ ] **Fix:** induction as `inpatient` encounter with ~28-day LOS then `EncounterEnd` (legitimate LOS — keep under the inpatient rule), or closed weekly visits; death paths close encounters before delays. Death code → `91857003` (acute lymphoid leukemia — verify). Incidence: annual 7e-5 (ages 1–4), 3e-5 (5–14), 1e-5 (15+), no compounding re-rolls. Keep `1863354` vincristine as the SCD model.
- [ ] Commit: `fix(all): induction LOS, ALL death code, pediatric-peaked incidence`

### Task 2.7: polycythemia_vera.json

**Defects:** `Repeat_PegInterferon` fires for everyone, quarterly, forever; 30-day pruritus-branch hold (`Initial_Hematology_Encounter` across `Prescribe_Pruritus_Treatment_Supply_Delay`); LOINC 2157-6 (creatine kinase) recorded for erythropoietin; thrombotic events + warfarin stack in loops; interferons/ruxolitinib/busulfan unmapped ingredient CUIs.
- [ ] **Fix:** gate `Repeat_PegInterferon` on an `pv_on_interferon` attribute set only in the interferon arm (~10% of patients), with `MedicationEnd` on discontinue. Close the encounter before the pruritus supply delay. Replace 2157-6 with the serum-erythropoietin LOINC (look up on loinc.org; do not reuse 2157-6). Guard thrombotic `ConditionOnset` + warfarin order with attributes. SCD codes for orals; interferons as administered J-codes if that's how they're billed (verify route).
- [ ] Commit: `fix(polycythemia_vera): gate interferon repeat, close pruritus branch, EPO LOINC, dedupe thrombosis/warfarin, mapped drugs`

### Task 2.8: congestive_heart_failure.json

**Defects:** own graph well-built; was blocked entirely by the chf_meds call chain (fixed in 1.7); Stage D progression ~3× its cited source. Audit confirmed its hospice `Encounter → scheduled Death → Terminal` is a valid pattern — do not "fix" it.
- [ ] **Fix:** divide the Stage D progression per-pass probability by 3 to match the module's own cited source (update remarks with the arithmetic). Confirm calls into chf_meds happen after congestive's encounter closes.
- [ ] Commit: `fix(congestive_heart_failure): stage D progression to cited rate`

### Task 2.9: multiple_myeloma.json

**Defects:** lint CRITICALs `Initial_MM_Workup`, `Transfusion_Encounter`, `Renal/Fracture/Hypercalcemia_Hospitalization`, `Salvage_Therapy_Encounter` (audit: superseded same-instant, so no lock — but all inpatient stays are zero-duration with no discharge_disposition). Orphaned: `Death_From_MM`, `Hospice_Check`, `Hospice_Enrollment`, `Hospice_Visit(+End)`, `Terminal_MM`, `Pegfilgrastim` — MM patients never die of MM, never generate hospice claims, pegfilgrastim (a pipeline target drug) never fires. MGUS rolled at birth (3% of newborns). New salvage line 1–2×/yr forever; 35% complication per monitoring visit; complications stack (CKD/fracture/hypercalcemia).
- [ ] **Fix:** wire `Relapse_Check` → `Hospice_Check` and `Autologous_Transplant` → `Pegfilgrastim` → `Maintenance_Lenalidomide` (audit's intended wires). Give the three hospitalizations real LOS (3–7 d inpatient, `EncounterEnd` with `discharge_disposition`); close workup/transfusion/salvage encounters. MGUS: one-shot 3% at age 50 + 0.2%/yr after; MGUS→MM 1%/yr. Cap salvage: attribute `mm_salvage_lines`, max 4, 18–30 mo apart. Complications: annual rates (CKD 3%/yr, fracture 8%/yr, hypercalcemia 4%/yr) converted per-pass, each `ConditionOnset` attribute-guarded. Add sources to remarks.
- [ ] Verify: smoke — hospice encounters for MM patients exist; pegfilgrastim (`administration`, J2506) appears in output. Commit: `fix(multiple_myeloma): wire death/hospice/pegfilgrastim, real hospitalizations, MGUS at 50, cap salvage lines`

### Task 2.10: AIS_From_School_Screening_to_SOSORT_Recommendations.json

**Defects:** X-ray encounter open across a 3–7-day delay; diagnosis recorded twice; 13-way uniform severity distribution; claims-invisible (no ICD mapping for dx, 11 unmapped procedures).
- [ ] **Fix:** close the X-ray visit before the delay; attribute-guard the second dx; severity distribution → mild 0.80 / moderate 0.15 / severe 0.05; add `condition_code_map.json` row for the scoliosis SNOMED dx (→ ICD-10-CM M41.12x) and `hcpcs_code_map.json` rows for the 11 procedures.
- [ ] Commit: `fix(ais): close imaging encounter, dedupe diagnosis, weighted severity, map dx and procedures`

---

## Phase 3 — Remaining per-module remediation

Standard Cycle; one commit per module, message pattern `fix(<module>): <summary>`.

- [ ] **3.1 SLE.json** — line 367 `"target_encounter": 0` → the diagnosis-encounter state's name (audit: `"Diagnosis_Encounter"`; confirm the state exists under that exact name). Replace birth-rolled lifetime risk + 6–36 mo prodrome with annual incidence ages 15–45, F:M 9:1, keeping the existing (well-built) race/sex stratification ratios. Add sources. Verify: SLE code 55464009 appears in smoke output with onset ≥ 10. The four `{"condition_type": "True"}` fallback lint flags are **false positives** — leave them.
- [ ] **3.2 acute_myeloid_leukemia.json** — age classification at *diagnosis*, not once at 1–10 (kills the frozen "pediatric forever" state); adult arm: annual 1e-5 (<60), 8e-5 (60+); wire `Rapid_AML_Progression`/death (currently unreachable → immortal relapsing disease); restructure the azacitidine funnel per its remarks.
- [ ] **3.3 acute_kidney_injury.json** — drop the 22% pediatric roll; hospital/community AKI annual 0.4% at 65+ (0.05% younger adults); sourced mortality ~15% of severe cases (attributed via the module's Death state); `ConditionEnd` on recovery 7–90 days.
- [ ] **3.4 myasthenia_gravis.json** — outcome loop: refractory ≤ 10% (was ~87%), annual mortality ~0.7% (was ~6%); bimodal onset (F 20–40 annual 3e-5, M 60–80 annual 5e-5) replacing the one-shot age-15 roll; SCD codes for pyridostigmine/azathioprine; IVIG/rituximab as administered J-codes.
- [ ] **3.5 myelodysplastic_syndromes.json** — transfusion-loop AML transformation to its own cited 2.5%/yr converted per-pass (was ~70%/yr); attribute-guard deferasirox/azacitidine/venetoclax orders; `MedicationEnd` for fixed courses (ATG, cytarabine, idarubicin); implement the cited 1.8× male excess; incidence annual 3e-5 (60) → 2e-4 (80+), replacing 4%-by-50; lower-risk-arm drugs (ESA/luspatercept/imetelstat/chelation/IST): infusions → `administration` + J-rows, orals → SCD + NDC rows.
- [ ] **3.6 wet_amd.json** — dry-AMD annual 0.8% from 55 (was 5–25% per 1–3-yr pass → >90% by 85); dry→wet conversion 1.5%/yr; record dry AMD at a (closed) encounter; anti-VEGF maintenance q4–8wk closed injection visits ongoing (not 3 lifetime); scanner must clear the never-scanned anti-VEGF codes (aflibercept J0178 / ranibizumab J2778 rows as needed).
- [ ] **3.7 eye/intraocular_pressure.json** — restore attribute-driven IOP: persist `iop_reading`, adjust by treatment state, stop re-rolling uniform 8–35 per visit (was ~77%/visit "elevated" → every T2 diabetic glaucomatous); attribute-guard the per-visit re-diagnosis and drop re-orders.
- [ ] **3.8 eye/ophthalmic_progression.json** — fix the brimonidine code mismatch in the IOP feedback loop (order and end must use the same SCD).
- [ ] **3.9 dlbcl.json** — R-CHOP as 6 × 21-day cycles of closed encounters (currently all care same-instant); explicit `encounter_class` everywhere; age gate annual 2e-5 (40) → 1e-4 (75+), median ~66 (was newborn DLBCL); refractory arm inside encounters; SCD/J-code mapping per Constraint 3.
- [ ] **3.10 endometrial_cancer.json** — second-line care inside encounters, delete the orphan `EncounterEnd`s; recode the 8 CPT-system procedures (incl. definitive hysterectomy — candidate SNOMED `116140006` total hysterectomy, verify — and all radiation) to SNOMED + `hcpcs_code_map.json` rows; the 8 stackable open-ended med orders get attribute guards + `MedicationEnd`; single pembrolizumab order path (one state, `administration: true`, J9271 row); recurrence per-pass from ~13%/5 yr (~0.9% per 4-mo pass, was 35%/pass); `LocalRecurrence` coded as local recurrence, not widespread metastatic disease (verify concept).
- [ ] **3.11 small_cell_lung_cancer.json** — rewrite the front half: remove infant onset; annual adult loop checking `smoker` *at adult ages* (the current check ~1 day after birth precedes the attribute existing — that ordering bug is the dead branch): smokers 50+ annual 1.5e-4, never-smokers 5e-6; close `Present_Symptoms` (lint CRITICAL); keep the treatment spine intact.
- [ ] **3.12 acute_myeloid_leukemia_pediatric_prophylaxis.json** — drop `administration: true` on levofloxacin `199885` (oral tablet → dispensed Rx; currently the namesake drug vanishes); move dedupe/bacteremia checks off the birth-instant onto the prophylaxis-start encounter.
- [ ] **3.13 primary_immunodeficiency.json** — condition/symptom cleanup + source the unsourced weights (near-shippable; keep small).
- [ ] **3.14 colorectal_cancer.json** — delete the clinically bogus 1% BMT-after-chemo arm; CMP labs to normal (non-ESRD) reference ranges; add `gmf_version`.
- [ ] **3.15 high_output_heart_failure.json** — July lock fix is verified complete; calibrate incidence (HOHF is rare: ≤ 2% of HF incidence); resolve the two dead guard arms reading never-set `hyperthyroidism`/`av_fistula` attrs — delete the guards (documenting why in remarks) rather than inventing setters.
- [ ] **3.16 asthma.json + hypertension.json** — map asthma's one unmapped screening code; hypertension cosmetics (`gmf_version`, the one display typo). One commit: `chore(modules): asthma screening code map, hypertension cosmetics`.

---

## Phase 4 — Ground-up rewrites (each gets its own sub-plan before execution)

Scope check: these two are full module redesigns — write a dedicated plan doc for each (same directory, same format) before implementing. The requirements below are binding for those sub-plans.

### Task 4.1: non_small_cell_lung_cancer.json rewrite

Requirements: `ConditionOnset` for NSCLC (SNOMED 254637007, verify) targeted at a diagnosis encounter — the current module has **no diagnosis at all** and carries condition codes as observation codes in the pathology MultiObservation (recode as proper dx + LOINC pathology report). Incidence: annual smoker 50+ 5e-4, never-smoker 2e-5, median ~70 (currently full course at birth, 0.1% of newborns). Staging via `distributed_transition` into per-stage `SetAttribute` states (string values — no `value_set`, see Task 2.1), attribute renamed `nsclc_stage` (Task 5.4 contract). Treatment arms: surgery (stage I–II), chemoradiation (III), pembrolizumab ± platinum doublet (IV) — all as closed per-cycle encounters, drugs per Constraint 3 (pembrolizumab J9271, carboplatin J9045, pemetrexed J9305 rows as needed). Mortality by stage (5-yr survival ~65%/40%/15%/5%). Coordination guard per Task 5.3.

### Task 4.2: alzheimers.json rework (on top of 1.6's containment)

Requirements: keep 1.6's gating/mortality; restructure progression MCI → mild → moderate → severe with annual stage transitions (~10%/yr each); cholinesterase inhibitors as SCD prescriptions (donepezil/rivastigmine/galantamine — map rows), lecanemab/donanemab as administered J-codes gated to early-stage + amyloid-positive subgroup; nursing-home phase as recurring closed SNF encounters; hospice per the `hospice`/`hospice_reason` attribute contract; CPT strays recoded. Coordination with stock `dementia.json` per Task 5.2 (custom module must not double-diagnose 26929004).

---

## Phase 5 — Cross-module coordination

- [ ] **5.1 Retire b_cell_lymphomas.json** — duplicates DLBCL (same code!) and MCL (different code) against the dedicated modules, and codes MCL salvage chemo as 385763009 "Hospice care" (contaminating monitored hospice volumes). `git rm src/main/resources/modules/b_cell_lymphomas.json`; grep the tree for references (lookup tables, submodule calls) — expect none. Commit: `feat(modules): retire b_cell_lymphomas in favor of dlbcl/mantle_cell_lymphoma`.
- [ ] **5.2 Double-diagnosis gates** — pattern: at each custom module's onset point, a `conditional_transition` on the Active Condition of the rival code → `Terminal`. Apply to: SLE (vs stock lupus 200936003), alzheimers (vs stock dementia 26929004), NSCLC + SCLC (vs stock lung_cancer and veteran_lung_cancer active-condition codes), the four HF modules (each checks the others' dx codes; first-to-fire wins). One commit per pair/group.
- [ ] **5.3 Prostate ↔ veteran coordination** — custom module sets attribute `"Prostate Cancer"`; stock veteran module and the hospice modules read `prostate_cancer`. Fix: custom module *also* sets `prostate_cancer` (so `home_hospice_snf`/`hospice_treatment` fire for its patients) and both prostate modules gate on it (no double prostatectomy). Commit: `fix(prostate_cancer): honor stock prostate_cancer attribute contract`.
- [ ] **5.4 Shared-attribute renames** — `cancer_stage`/`histology` written by NSCLC + pancreatic + ovarian with ovarian the sole reader (overwrite inside its 2–5-week windows misroutes treatment): rename to `nsclc_stage`, `pancreatic_stage`, `ovarian_stage`/`ovarian_histology` in writers *and* readers. `furosemide_40_mg_oral_tablet_rx`(+`_2`, lisinopril) written by chf_meds, right_sided, valvular (one module MedicationEnd's another's order): prefix per module (`chf_`, `rshf_`, `vhf_`). Verify with `grep -rn '"cancer_stage"\|furosemide_40_mg' src/main/resources/modules/` → only prefixed hits remain. Commit: `fix(modules): namespace shared attributes across cancer and HF modules`.

---

## Phase 6 — Code-mapping sweep

- [ ] **6.1** `python3 tools_scan_unmapped_codes.py --csv unmapped_module_codes.csv` over the whole tree. Phases 1–5 should have cleared the audit's named gaps; this sweep catches stragglers. For each remaining row: ingredient CUI → SCD swap (find via `curl "https://rxnav.nlm.nih.gov/REST/rxcui/<cui>/related.json?tty=SCD"`), route-mismatched flags corrected, or an export-map row added. Fork-owned custom modules must reach zero rows; stock-module rows get a triage note in the Phase 7 report instead of edits. Commit: `fix(modules): close remaining code-map gaps from full-tree scan`.
- [ ] **6.2** Update the authoring rules doc used by future module work (`~/dev/srdc_pipelines/reference/synthea_module_authoring_rules.md`): add §10 pitfalls for the `*_Supply_Delay`-inside-encounter idiom and ingredient-level RxNorm CUIs, and note the linter/scanner as mandatory pre-commit checks. (Commit in srdc_pipelines, not this repo.)

---

## Phase 7 — Full verification regen and PR

- [ ] **7.1 Static gate:** `python3 tools_lint_module_locks.py` → 0 CRITICAL outside triaged stock modules; `python3 tools_scan_unmapped_codes.py` → 0 rows for fork modules.
- [ ] **7.2 Generation gate:** `./tools_smoke_gen.sh 1000` → no exceptions. Assertions, all must PASS: `--mean-encounters-min 30 --top-share-max 0.05` (starvation/monoculture); prostate 399068003 M 55+ share 0.06–0.18; AD 26929004 65+ share ≤ 0.15; pneumonia share 0.10–0.45 with onset 5th percentile ≥ 1 yr; MM/MCL/CIDP/ovarian/bladder/pancreatic shares within their task bounds; every custom-module target drug from the audit (pegfilgrastim, daratumumab, pembrolizumab, anti-VEGF, IVIG) appears ≥ once in `medications.csv`. Save the full check output as `docs/superpowers/plans/2026-08-10-final-verification.txt`.
- [ ] **7.3 Report:** update `~/dev/srdc_pipelines/reference/modsynthea_module_audit.md` with a "Remediation status 2026-08" section: per-module before/after verdicts, the stock-module triage list, and the new baseline numbers.
- [ ] **7.4 PR:** `git push -u origin fix/module-audit-remediation` and open a PR to `master` with the phase gates and final verification artifact linked. Regeneration of the actual dataset happens only after merge, per the srdc_pipelines regen flow.

---

## Self-review record (per writing-plans skill)

*Spec coverage:* audit classes → tasks: locks (1.1–1.10, 2.2–2.4, 2.10, 3.11), disease-never-recorded (2.5, 3.1, 4.1, 1.10 umbrella), unreachable arms (1.7, 1.9, 2.2, 2.9, 3.2, 1.10, 3.11), incidence (every Phase 1/2/3 module task; table values inlined), compounding rates (1.1, 1.4, 1.10, 2.7, 2.8, 2.9, 3.4, 3.5, 3.6, 3.10), mapping/coding (Constraint 3–4, per-task code fixes, 6.1), cross-module (Phase 5), stacking (Constraint 6, per-task guards), tooling notes (Phase 0). Corrections section honored: J-code map treated as live; SLE fallback flags left alone (3.1); hypertension redraw idiom untouched; congestive hospice pattern explicitly not "fixed" (2.8, 0.1); stale CSV regenerated before trust (0.2).
*Known open items:* candidate codes marked "verify" resolve at implementation time under Constraint 9; Phase 4 sub-plans required before those two rewrites.
