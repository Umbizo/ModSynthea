#!/usr/bin/env python3
"""Reweight medication_code_map NDC lists toward the codesheet NDC sets.

For every RxCUI a module can order, if that RxCUI's NDC list overlaps the NDC
set of any TA whose module orders it, attach weights so the overlapping NDCs
carry FAVOURED_MASS of the probability and the remainder shares the rest.
Nothing is deleted -- an NDC outside the sheet stays reachable, just rarer,
which keeps the data from becoming a perfect mirror of the target list.

FAVOURED_MASS is tiered by how many in-sheet NDCs exist for the RxCUI, rather
than fixed at one value: concentrating a flat 0.90 onto only 1-2 NDCs would
make those specific products implausibly dominant in the output relative to
real Part D long-tail behaviour.
    >= 10 in-sheet NDCs -> 0.90
    3-9   in-sheet NDCs -> 0.75
    1-2   in-sheet NDCs -> 0.50
That per-product-dominance rationale only justifies picking a tier -- it does
not guarantee the tier is an improvement over the RxCUI's pre-existing
uniform draw (n_inside / n_total). When in-sheet NDCs are a large share of a
small total (e.g. 2 of 3), a low tier can fall *below* uniform and make the
reweighting counterproductive. favoured_mass() therefore takes both counts
and floors the tier at the uniform baseline, so a reweighted RxCUI never
lands below where it started.
A zero weight is never used here -- every out-of-sheet NDC must stay
selectable (RandomCollection.add() silently drops weight <= 0 entries).
"""
import argparse, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(ROOT, 'src', 'main', 'resources', 'export')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tools_ta_coverage as T  # noqa: E402


def favoured_mass(n_inside, n_total):
    if n_inside >= 10:
        tier = 0.90
    elif n_inside >= 3:
        tier = 0.75
    else:
        tier = 0.50
    uniform = n_inside / n_total
    return max(tier, uniform)


def rxcuis_by_ta():
    """{ta_key: set(rxcui)} for every TA whose sheet carries NDC rows."""
    out = {}
    for key, cfg in T.TA_CONFIG.items():
        if not cfg['target_ndc']:
            continue
        cuis = set()
        mods = T._maps.get('mods') or {}
        if not mods:
            T.our_codes(cfg)
            mods = T._maps['mods']

        def walk(rel, seen):
            if rel in seen or rel not in mods:
                return set()
            seen.add(rel)
            got = set()
            for _n, s in mods[rel]['states'].items():
                if s.get('type') == 'MedicationOrder':
                    for c in (s.get('codes') or []):
                        got.add(str(c.get('code')))
                elif s.get('type') == 'CallSubmodule' and s.get('submodule'):
                    got |= walk(s['submodule'], seen)
            return got

        for stem in (cfg.get('module_stems') or []):
            for rel in mods:
                if os.path.basename(rel) == stem:
                    cuis |= walk(rel, set())
        if cuis:
            out[key] = cuis
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    path = os.path.join(EXP, 'medication_code_map.json')
    med = json.load(open(path))
    by_ta = rxcuis_by_ta()

    targets = {}
    for ta, cuis in by_ta.items():
        for c in cuis:
            targets.setdefault(c, set()).update(T.TA_CONFIG[ta]['target_ndc'])

    changed = 0
    tiers = {0.90: 0, 0.75: 0, 0.50: 0}
    for cui, wanted in sorted(targets.items()):
        entries = med.get(cui)
        if not entries:
            continue
        inside = [e for e in entries if str(e['code']) in wanted]
        outside = [e for e in entries if str(e['code']) not in wanted]
        if not inside or not outside:
            continue  # nothing to favour, or nothing to demote
        uniform = len(inside) / len(entries)
        mass = favoured_mass(len(inside), len(entries))
        raw_tier = 0.90 if len(inside) >= 10 else 0.75 if len(inside) >= 3 else 0.50
        w_in = mass / len(inside)
        w_out = (1.0 - mass) / len(outside)
        for e in inside:
            e['weight'] = '%.8f' % w_in
        for e in outside:
            e['weight'] = '%.8f' % w_out
        changed += 1
        tiers[raw_tier] += 1
        print('%-10s %5d NDCs, %4d in sheet -> mass %.2f, uniform baseline %.2f, P(hit) %.2f' %
              (cui, len(entries), len(inside), mass, uniform, mass))

    print('reweighted %d RxCUIs' % changed)
    print('tiers: 0.90=%d  0.75=%d  0.50=%d' % (tiers[0.90], tiers[0.75], tiers[0.50]))
    if a.apply:
        with open(path, 'w') as f:
            json.dump(med, f, indent=2)
            f.write('\n')
        print('written to', path)
    else:
        print('dry run; pass --apply to write')


if __name__ == '__main__':
    main()
