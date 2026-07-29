#!/usr/bin/env python3
"""Lint Synthea modules for encounter-lock hazards.

ModSynthea's engine gives each person a single encounter reservation. A module
that opens an Encounter and does not reach an EncounterEnd holds that lock:
EncounterModule stops scheduling wellness/urgent-care visits for that person
(EncounterModule.java:95) and every other module's Encounter state blocks
(State.java:991). Only EncounterEnd, a reachable Terminal, Death, or the module
re-entering its own Encounter state releases it.

CRITICAL  no EncounterEnd is reachable from an opened Encounter, so the lock is
          held until Terminal/Death -- or forever, if the module loops. This is
          the defect that flattened carrier/DME/hospice volume in the 2026-07-29
          generation run.
WARNING   an ambulatory/outpatient/virtual/urgent-care visit stays open across a
          delay of a day or more. Legitimate for inpatient/SNF/hospice (that
          delay is the length of stay); wrong for a clinic visit.
"""
import json, glob, os, sys

DAY = 86400_000
UNIT_MS = {"seconds": 1000, "minutes": 60_000, "hours": 3_600_000,
           "days": DAY, "weeks": 7 * DAY, "months": 30 * DAY, "years": 365 * DAY}
# classes where an open encounter spanning days is a modelling error
AMBULATORY = {"ambulatory", "outpatient", "virtual", "urgentcare", "wellness"}
CLOSERS = {"EncounterEnd", "Terminal", "Death"}


def targets(v):
    out = []
    if 'direct_transition' in v:
        out.append(v['direct_transition'])
    for key in ('distributed_transition', 'conditional_transition',
                'lookup_table_transition'):
        for t in v.get(key, []) or []:
            out.append(t.get('transition'))
    for t in v.get('complex_transition', []) or []:
        if 'transition' in t:
            out.append(t['transition'])
        for d in t.get('distributions', []) or []:
            out.append(d.get('transition'))
    return [x for x in out if x]


def delay_ms(v):
    d = v.get('range') or v.get('exact') or {}
    unit = d.get('unit', 'days')
    hi = d.get('high', d.get('quantity', 0)) or 0
    return hi * UNIT_MS.get(unit, DAY)


def analyze(path):
    states = json.load(open(path)).get('states', {})
    if not states:
        return []
    findings = []

    def walk_from(start, cls):
        """Explore forward from an opened encounter until it is closed.

        Returns (reaches_end, long_waits) where reaches_end is True if any
        EncounterEnd is reachable while the encounter is still open.
        """
        seen, stack = set(), [start]
        reaches_end, long_waits = False, []
        while stack:
            k = stack.pop()
            if k in seen or k not in states:
                continue
            seen.add(k)
            v = states[k]
            t = v.get('type')
            if t == 'EncounterEnd':
                reaches_end = True
                continue          # closed on this path; stop descending
            if t in ('Terminal', 'Death'):
                continue          # releases the lock, but only at the very end
            if t == 'Encounter' and k != start and not v.get('wellness'):
                continue          # re-entering an Encounter force-closes the old
            if t in ('Delay', 'Guard'):
                ms = delay_ms(v) if t == 'Delay' else float('inf')
                if cls in AMBULATORY and ms >= DAY:
                    long_waits.append((k, t, v.get('range') or v.get('exact') or 'guard'))
            stack.extend(targets(v))
        return reaches_end, long_waits

    for k, v in states.items():
        if v.get('type') != 'Encounter' or v.get('wellness'):
            continue
        cls = (v.get('encounter_class') or '').lower()
        reaches_end, long_waits = walk_from(k, cls)
        if not reaches_end:
            findings.append(('CRITICAL', k, 'no EncounterEnd reachable', cls))
        for w in long_waits:
            findings.append(('WARNING', k, f'open across {w[0]} ({w[2]})', cls))
    return findings


def main(dirpath, only=None):
    crit = warn = 0
    for f in sorted(glob.glob(os.path.join(dirpath, '**/*.json'), recursive=True)):
        name = os.path.relpath(f, dirpath)
        if only and name not in only:
            continue
        try:
            fnd = analyze(f)
        except Exception as e:
            print(f"{name}: PARSE-ERROR {e}")
            continue
        c = [x for x in fnd if x[0] == 'CRITICAL']
        w = [x for x in fnd if x[0] == 'WARNING']
        crit += len(c)
        warn += len(w)
        if c or w:
            print(f"== {name}")
            for x in c:
                print(f"   CRITICAL {x[1]} [{x[3]}] {x[2]}")
            for x in w[:6]:
                print(f"   WARNING  {x[1]} [{x[3]}] {x[2]}")
            if len(w) > 6:
                print(f"   ... {len(w)-6} more warnings")
    print(f"\nCRITICAL={crit} WARNING={warn}")
    return 1 if crit else 0


if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    d = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(here, 'src', 'main', 'resources', 'modules')
    sys.exit(main(d))
