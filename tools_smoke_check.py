#!/usr/bin/env python3
"""Check epidemiology bounds against a Synthea CSV smoke-generation run.

Reads output/smoke/csv/{patients,conditions,encounters}.csv (or --out) and
validates population-level epidemiology invariants: the share of an eligible
sub-population with a given condition, the age at which that condition first
appears, and two population-wide encounter/condition-volume checks used to
catch starvation caused by encounter-lock bugs.

Every later module-fix task's SMOKE step runs this against a fresh
./tools_smoke_gen.sh output.

Age is computed as (sim-end date - BIRTHDATE) in years, where sim-end is
DEATHDATE for deceased patients, else the patient's own last encounter STOP
(falling back to the population's last encounter STOP if the patient somehow
has no encounters at all). Onset age is (first CODE-matching condition START
- BIRTHDATE).

Column lookups (Id/PATIENT/BIRTHDATE/DEATHDATE/GENDER/CODE/START/STOP) are
case-insensitive to tolerate CSV header drift across Synthea versions.
"""
import argparse
import csv
import os
import sys
from datetime import date


def parse_date(s):
    """Parse a Synthea CSV date/datetime string's leading YYYY-MM-DD."""
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def age_years(start, end):
    if start is None or end is None:
        return None
    days = (end - start).days
    if days < 0:
        return None
    return days / 365.25


def colmap(fieldnames):
    """lowercase header name -> actual header name, for case-insensitive lookup."""
    return {h.lower(): h for h in fieldnames or []}


def get(row, cmap, name):
    key = cmap.get(name.lower())
    if key is None:
        return None
    return row.get(key)


def read_table(path, required):
    if not os.path.exists(path):
        print(f"ERROR: missing {path}", file=sys.stderr)
        sys.exit(2)
    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        cmap = colmap(reader.fieldnames)
        missing = [c for c in required if c.lower() not in cmap]
        if missing:
            print(f"ERROR: {path} missing required column(s): {missing} "
                  f"(found: {reader.fieldnames})", file=sys.stderr)
            sys.exit(2)
        rows = list(reader)
    return rows, cmap


def percentile(values, pct):
    """Linear-interpolation percentile (numpy 'linear' method), pure python."""
    if not values:
        return None
    v = sorted(values)
    if len(v) == 1:
        return v[0]
    k = (len(v) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(v) - 1)
    if f == c:
        return v[f]
    return v[f] + (v[c] - v[f]) * (k - f)


def check(label, value, min_bound, max_bound, violations, fmt='{:.3f}'):
    """Print `value` next to whichever of min_bound/max_bound is set, and
    record a violation for any bound the value fails. A value of None (not
    computable) only counts as a violation if a bound was actually requested
    -- an unrequested check never fails ("--code with no share bounds given
    should not fail on share")."""
    bounds_requested = min_bound is not None or max_bound is not None
    if value is None:
        parts = [f"{label}: n/a"]
        if min_bound is not None:
            parts.append(f"min={fmt.format(min_bound)}")
        if max_bound is not None:
            parts.append(f"max={fmt.format(max_bound)}")
        print("  ".join(parts))
        if bounds_requested:
            violations.append(f"{label}: n/a but bound requested "
                               f"(min={min_bound}, max={max_bound})")
        return

    parts = [f"{label}: {fmt.format(value)}"]
    if min_bound is not None:
        ok = value >= min_bound
        parts.append(f"min={fmt.format(min_bound)} [{'OK' if ok else 'FAIL'}]")
        if not ok:
            violations.append(f"{label} = {fmt.format(value)} < min {fmt.format(min_bound)}")
    if max_bound is not None:
        ok = value <= max_bound
        parts.append(f"max={fmt.format(max_bound)} [{'OK' if ok else 'FAIL'}]")
        if not ok:
            violations.append(f"{label} = {fmt.format(value)} > max {fmt.format(max_bound)}")
    print("  ".join(parts))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--code', help='SNOMED condition code to check epidemiology bounds for')
    ap.add_argument('--sex', choices=['M', 'F'], help='restrict eligible population to this GENDER')
    ap.add_argument('--eligible-min-age', type=float, default=0.0,
                     help='minimum age at sim end to count as eligible (default 0)')
    ap.add_argument('--min-share', type=float,
                     help='min allowed share of eligible pop with >=1 dx of --code')
    ap.add_argument('--max-share', type=float,
                     help='max allowed share of eligible pop with >=1 dx of --code')
    ap.add_argument('--min-onset-age', type=float,
                     help='min allowed 5th-percentile onset age for --code')
    ap.add_argument('--max-onset-age', type=float,
                     help='max allowed 95th-percentile onset age for --code')
    ap.add_argument('--mean-encounters-min', type=float,
                     help='min allowed mean encounter rows per patient (whole population)')
    ap.add_argument('--top-share-max', type=float,
                     help='max allowed share of all condition rows held by a single code '
                          '(whole population)')
    ap.add_argument('--exclude-codes',
                     help='comma-separated condition codes to exclude from the '
                          '--top-share-max computation only (both numerator and '
                          'denominator); these codes still count normally for every '
                          'other check (e.g. legitimate high-frequency administrative '
                          'codes like med_rec\'s "Medication review due" that would '
                          'otherwise permanently jam the monoculture gate)')
    ap.add_argument('--out', default='output/smoke/csv',
                     help='directory containing patients/conditions/encounters.csv '
                          '(default output/smoke/csv)')
    args = ap.parse_args()

    share_requested = args.min_share is not None or args.max_share is not None
    onset_requested = args.min_onset_age is not None or args.max_onset_age is not None
    global_requested = args.mean_encounters_min is not None or args.top_share_max is not None

    if (share_requested or onset_requested) and not args.code:
        ap.error('--min-share/--max-share/--min-onset-age/--max-onset-age require --code')
    if not args.code and not global_requested:
        ap.error('nothing to check: pass --code (with bounds) and/or '
                  '--mean-encounters-min/--top-share-max')

    patients_path = os.path.join(args.out, 'patients.csv')
    conditions_path = os.path.join(args.out, 'conditions.csv')
    encounters_path = os.path.join(args.out, 'encounters.csv')

    patients, pcmap = read_table(patients_path, ['Id', 'BIRTHDATE', 'DEATHDATE', 'GENDER'])
    conditions, ccmap = read_table(conditions_path, ['PATIENT', 'CODE', 'START'])
    encounters, ecmap = read_table(encounters_path, ['PATIENT', 'START', 'STOP'])

    # Per-patient max encounter STOP (falls back to START if STOP is blank,
    # e.g. an encounter left open by a lock bug) and per-patient encounter counts.
    max_stop = {}
    enc_count = {}
    for r in encounters:
        pid = get(r, ecmap, 'PATIENT')
        enc_count[pid] = enc_count.get(pid, 0) + 1
        stop = parse_date(get(r, ecmap, 'STOP')) or parse_date(get(r, ecmap, 'START'))
        if stop is not None and (pid not in max_stop or stop > max_stop[pid]):
            max_stop[pid] = stop
    global_max_stop = max(max_stop.values()) if max_stop else None

    pinfo = {}
    for r in patients:
        pid = get(r, pcmap, 'Id')
        birth = parse_date(get(r, pcmap, 'BIRTHDATE'))
        death = parse_date(get(r, pcmap, 'DEATHDATE'))
        gender = (get(r, pcmap, 'GENDER') or '').strip().upper()
        sim_end = death or max_stop.get(pid) or global_max_stop
        age = age_years(birth, sim_end) if sim_end else None
        pinfo[pid] = {'birth': birth, 'gender': gender, 'age': age}

    total_patients = len(patients)
    violations = []

    # Condition-code frequency (needed for --top-share-max regardless of --code)
    # and, if --code given, each patient's first onset date of that code.
    cond_code_counts = {}
    total_condition_rows = 0
    first_onset = {}
    for r in conditions:
        code = get(r, ccmap, 'CODE')
        cond_code_counts[code] = cond_code_counts.get(code, 0) + 1
        total_condition_rows += 1
        if args.code and code == args.code:
            pid = get(r, ccmap, 'PATIENT')
            st = parse_date(get(r, ccmap, 'START'))
            if st is not None and (pid not in first_onset or st < first_onset[pid]):
                first_onset[pid] = st

    # ---- code-specific checks: share of eligible pop with dx, onset-age percentiles ----
    if args.code:
        eligible_ids = [pid for pid, info in pinfo.items()
                         if info['age'] is not None and info['age'] >= args.eligible_min_age
                         and (args.sex is None or info['gender'] == args.sex)]
        n_eligible = len(eligible_ids)
        n_with_dx = sum(1 for pid in eligible_ids if pid in first_onset)
        share = (n_with_dx / n_eligible) if n_eligible else None

        print(f"eligible population (code={args.code}, sex={args.sex or 'any'}, "
              f"min-age={args.eligible_min_age}): n={n_eligible}, n_with_dx={n_with_dx}")
        check(f"share of dx {args.code} in eligible pop", share,
              args.min_share, args.max_share, violations)

        onset_ages = []
        for pid in eligible_ids:
            if pid in first_onset:
                a = age_years(pinfo[pid]['birth'], first_onset[pid])
                if a is not None:
                    onset_ages.append(a)

        p5 = percentile(onset_ages, 5)
        p95 = percentile(onset_ages, 95)
        print(f"onset age samples for dx {args.code} in eligible pop: n={len(onset_ages)}")
        check(f"onset age p5 for dx {args.code}", p5, args.min_onset_age, None,
              violations, fmt='{:.1f}')
        check(f"onset age p95 for dx {args.code}", p95, None, args.max_onset_age,
              violations, fmt='{:.1f}')

    # ---- global checks: mean encounters/patient, top condition-code share ----
    total_encounters = len(encounters)
    mean_enc = (total_encounters / total_patients) if total_patients else None
    check("mean encounters/patient", mean_enc, args.mean_encounters_min, None,
          violations, fmt='{:.2f}')

    exclude_set = {c.strip() for c in (args.exclude_codes or '').split(',') if c.strip()}
    top_counts = {c: n for c, n in cond_code_counts.items() if c not in exclude_set}
    top_total = sum(top_counts.values())
    if top_total:
        top_code, top_count = max(top_counts.items(), key=lambda kv: kv[1])
        top_share = top_count / top_total
        excl_note = ''
        if exclude_set:
            dropped = total_condition_rows - top_total
            excl_note = (f" (excluding {len(exclude_set)} code(s) "
                          f"{{{', '.join(sorted(exclude_set))}}}, {dropped} rows dropped "
                          f"from this computation only)")
        print(f"top condition code{excl_note}: {top_code} ({top_count}/{top_total} rows)")
    else:
        top_share = None
    check("top condition code share", top_share, None, args.top_share_max, violations)

    print()
    if violations:
        print(f"FAIL: {len(violations)} bound(s) violated:")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("PASS: all requested bounds satisfied")
    return 0


if __name__ == '__main__':
    sys.exit(main())
