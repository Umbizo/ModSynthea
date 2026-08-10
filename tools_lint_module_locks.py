#!/usr/bin/env python3
"""Lint Synthea modules for encounter-lock hazards.

ModSynthea's engine gives each person a single encounter reservation. A module
that opens an Encounter and does not reach an EncounterEnd holds that lock:
EncounterModule stops scheduling wellness/urgent-care visits for that person
(EncounterModule.java:95) and every other module's Encounter state blocks
(State.java:991). Only EncounterEnd, a reachable Terminal, Death, or the module
re-entering its own Encounter state releases it.

CRITICAL  fires in three cases: (1) an ambulatory/outpatient/virtual/urgentcare/
          wellness/emergency/home encounter (or one with no encounter_class --
          it silently defaults to ambulatory) can reach a Delay >= 1 day or a
          Guard before reaching a closer (EncounterEnd/Terminal/Death) or
          re-entering an Encounter; (2) an inpatient/snf/hospice encounter can
          never reach a closer at all -- held until Terminal/Death, or forever
          if the module loops; (3) while any encounter is open, a state named
          `*_Supply_Delay` is reachable -- the banned medication-supply-delay
          idiom, which is never a legitimate length of stay. This is the class
          of defect that flattened carrier/DME/hospice volume in the 2026-07-29
          generation run.
WARNING   an inpatient/snf/hospice encounter stays open across a delay of more
          than 90 days. A bounded length-of-stay delay is legitimate for these
          classes; a 90+ day open reservation is not.
"""
import json, glob, os, sys

DAY = 86400_000
UNIT_MS = {"seconds": 1000, "minutes": 60_000, "hours": 3_600_000,
           "days": DAY, "weeks": 7 * DAY, "months": 30 * DAY, "years": 365 * DAY}
# classes where an open encounter spanning days is a modelling error
AMBULATORY = {"ambulatory", "outpatient", "virtual", "urgentcare", "wellness"}
# emergency (ED) and home-health visits are also same-day encounters, not
# multi-day admissions -- a handoff to a genuine inpatient stay already
# counts as a closer via same-module Encounter re-entry, so these get the
# strict closed-before-blocked rule too, not the permissive inpatient one.
STRICT_CLASSES = AMBULATORY | {"emergency", "home"}
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
    d = v.get('range') or v.get('exact')
    if d is not None:
        unit = d.get('unit', 'days')
        hi = d.get('high', d.get('quantity', 0)) or 0
        return hi * UNIT_MS.get(unit, DAY)
    # GMF also allows a `distribution` delay (UNIFORM/GAUSSIAN/EXPONENTIAL)
    # with the unit at the state's top level and magnitude in `parameters`.
    # ~20% of Delay states in this tree use this form -- treating them as
    # 0ms (as a bare `v.get('range') or v.get('exact') or {}` would) hides
    # real multi-month locks (e.g. prostate_cancer's annual-screening loop).
    dist = v.get('distribution')
    if isinstance(dist, dict):
        p = dist.get('parameters') or {}
        unit = v.get('unit', 'days')
        # UNIFORM -> high; GAUSSIAN/EXPONENTIAL -> mean; EXACT -> value.
        hi = p.get('high', p.get('mean', p.get('value', 0))) or 0
        return hi * UNIT_MS.get(unit, DAY)
    return 0


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


def walk_closer_reachable(states, start):
    """For inpatient/snf/hospice classes: is any closer (EncounterEnd/
    Terminal/Death) reachable at all from `start`, and does the path cross a
    Delay > 90 days while the encounter is still open?
    """
    seen, stack = set(), list(targets(states[start]))
    reaches_closer, long_delays = False, []
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        v = states.get(name)
        if v is None:
            continue
        t = v.get('type')
        if t in CLOSERS:
            reaches_closer = True
            continue
        if t == 'Encounter':
            continue          # re-entering an Encounter releases the old lock
        if t == 'Delay':
            ms = delay_ms(v)
            if ms > 90 * DAY:
                long_delays.append((name, v.get('range') or v.get('exact')
                                    or v.get('distribution') or {}))
        stack.extend(targets(v))
    return reaches_closer, long_delays


def find_supply_delays(states, start):
    """Names of `*_Supply_Delay` states reachable from `start` while the
    encounter is still open (before a closer or a same-module Encounter
    re-entry). Always the banned idiom, regardless of encounter class."""
    seen, stack, found = set(), list(targets(states[start])), []
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        v = states.get(name)
        if v is None:
            continue
        if name.endswith('_Supply_Delay'):
            found.append(name)
        t = v.get('type')
        if t in CLOSERS or t == 'Encounter':
            continue
        stack.extend(targets(v))
    return found


def analyze(path):
    states = json.load(open(path)).get('states', {})
    if not states:
        return []
    findings = []

    for k, v in states.items():
        if v.get('type') != 'Encounter' or v.get('wellness'):
            continue
        cls = (v.get('encounter_class') or '').lower()

        # Supply-Delay idiom: CRITICAL while any encounter is open, any class.
        for name in find_supply_delays(states, k):
            findings.append(('CRITICAL', k,
                              f'{name} (Supply_Delay idiom) reachable while open', cls))

        if cls in STRICT_CLASSES or cls == '':
            closes_first, blockers = closes_before_block(states, k)
            if not closes_first:
                for name, t in blockers:
                    bv = states.get(name, {})
                    if t == 'Guard':
                        detail = 'guard'
                    else:
                        detail = bv.get('range') or bv.get('exact') or bv.get('distribution') or {}
                    findings.append(('CRITICAL', k, f'open across {name} ({detail})', cls))
        else:
            reaches_closer, long_delays = walk_closer_reachable(states, k)
            if not reaches_closer:
                findings.append(('CRITICAL', k,
                                  'no closer (EncounterEnd/Terminal/Death) reachable', cls))
            if cls in ('inpatient', 'snf', 'hospice'):
                for name, detail in long_delays:
                    findings.append(('WARNING', k,
                                      f'open across {name} ({detail}) > 90 days', cls))
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
    only = set(sys.argv[2:]) if len(sys.argv) > 2 else None
    sys.exit(main(d, only))
