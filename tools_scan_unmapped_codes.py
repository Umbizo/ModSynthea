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
