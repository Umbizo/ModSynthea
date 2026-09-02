#!/usr/bin/env python3
"""Per-TA claim-coverage metrics from a ModSynthea RIF/BFD export.

Reproduces the four columns of the codesheet-driven priority TA audit:
  col1  % of the TA's Rick J-codes seen at least once anywhere in the cohort
  col2  % of cohort patients with >=1 Rick J-code
  col3  % of cohort patients with >=1 Rick NDC or HCPCS/CPT code
  col4  % of cohort patients with >=1 NDC/HCPCS the TA's own modules can emit

Cohort semantics match the notebook: cohort membership comes only from the
categories named in dx_categories, matching is prefix-semantic in the parent
direction, and include_exclude == EXCLUDE rows are dropped.
"""
import argparse, collections, csv, glob, json, os, re, sys

csv.field_size_limit(10 ** 9)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, 'src', 'main', 'resources', 'modules')
EXP = os.path.join(ROOT, 'src', 'main', 'resources', 'export')
CS = os.environ.get(
    'CODESHEET_DIR',
    '/Users/ollie/dev/careset/srdc_pipelines/reference/codesheets')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ta_config import TA_CONFIG  # noqa: E402

DX_TYPE = 'ICD-10-CM'
RX_TYPES = {'HCPCS', 'CPT'}
NDC_TYPE = 'NDC'
# ICD-10-CM: a letter, a digit, then alphanumerics. U07/U09 (COVID) must pass.
ICD_SHAPE = re.compile(r'^[A-Z][0-9][0-9A-Z][0-9A-Z]*$')
CLAIM_FILES = ['carrier.csv', 'outpatient.csv', 'inpatient.csv', 'dme.csv',
               'hha.csv', 'hospice.csv', 'snf.csv']

_sheets = {}


def sheet(name):
    if name not in _sheets:
        rows = []
        with open(os.path.join(CS, name + '.csv'), encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                rows.append(dict(
                    code=(r['code'] or '').strip().upper(),
                    code_type=(r['code_type'] or '').strip(),
                    category=(r['category'] or '').strip(),
                    excluded=(r.get('include_exclude') or 'INCLUDE').strip().upper() == 'EXCLUDE'))
        _sheets[name] = rows
    return _sheets[name]


def select(rows, types, cats=None, restrict=None, shape=None):
    out = set()
    for r in rows:
        if r['code_type'] not in types or r['excluded']:
            continue
        if cats is not None and r['category'] not in cats:
            continue
        if restrict and not any(r['code'].startswith(p) for p in restrict):
            continue
        if shape and not shape.match(r['code']):
            continue
        out.add(r['code'])
    return out


for _k, _cfg in TA_CONFIG.items():
    _rows = sheet(_cfg['sheet'])
    _cfg['dx_codes'] = select(_rows, {DX_TYPE}, _cfg['dx_categories'],
                              _cfg.get('dx_restrict'), ICD_SHAPE)
    _cfg['target_hcpcs'] = select(_rows, RX_TYPES, _cfg.get('rx_categories'))
    _cfg['target_ndc'] = select(_rows, {NDC_TYPE}, _cfg.get('rx_categories'))
    _cfg['target_j'] = {c for c in _cfg['target_hcpcs'] if c.startswith('J')}


def module_exists(stem):
    return bool(glob.glob(os.path.join(MOD, '**', stem + '.json'), recursive=True))


_maps = {}


def our_codes(cfg):
    """NDC and HCPCS sets the TA's own modules can emit, following CallSubmodule."""
    if not _maps:
        _maps['med'] = json.load(open(os.path.join(EXP, 'medication_code_map.json')))
        _maps['rx'] = json.load(open(os.path.join(EXP, 'rxnorm_hcpcs_map.json')))
        _maps['hc'] = json.load(open(os.path.join(EXP, 'hcpcs_code_map.json')))
        mods = {}
        for p in glob.glob(os.path.join(MOD, '**', '*.json'), recursive=True):
            try:
                j = json.load(open(p))
            except ValueError:
                continue
            if 'states' in j:
                mods[os.path.relpath(p, MOD)[:-5]] = j
        _maps['mods'] = mods
    mods = _maps['mods']

    def walk(rel, seen):
        if rel in seen or rel not in mods:
            return set(), set()
        seen.add(rel)
        rx, pr = set(), set()
        for _n, s in mods[rel]['states'].items():
            t = s.get('type')
            if t == 'MedicationOrder':
                for e in (s.get('codes') or []):
                    rx.add(str(e.get('code')))
            elif t == 'Procedure':
                for e in (s.get('codes') or []):
                    pr.add(str(e.get('code')))
            elif t == 'CallSubmodule' and s.get('submodule'):
                a, b = walk(s['submodule'], seen)
                rx |= a
                pr |= b
        return rx, pr

    rx, pr = set(), set()
    for stem in (cfg.get('module_stems') or []):
        for rel in mods:
            if os.path.basename(rel) == stem:
                a, b = walk(rel, set())
                rx |= a
                pr |= b
    ndc, hcp = set(), set()
    for c in rx:
        for e in _maps['med'].get(c, []):
            ndc.add(str(e['code']))
        for e in _maps['rx'].get(c, []):
            hcp.add(str(e['code']).upper())
    for c in pr:
        for e in (_maps['hc'].get(c) or []):
            hcp.add(str(e['code']).upper())
    return ndc, hcp


def scan(bfd):
    dx = collections.defaultdict(set)
    hc = collections.defaultdict(set)
    nd = collections.defaultdict(set)
    for fn in CLAIM_FILES:
        p = os.path.join(bfd, fn)
        if not os.path.exists(p):
            continue
        with open(p, newline='', encoding='utf-8', errors='replace') as fh:
            rd = csv.reader(fh, delimiter='|')
            hdr = next(rd)
            ib = hdr.index('BENE_ID')
            idx_dx = [i for i, h in enumerate(hdr) if h.startswith('ICD_DGNS_CD')]
            idx_h = [i for i, h in enumerate(hdr) if h == 'HCPCS_CD']
            for row in rd:
                if len(row) <= ib or not row[ib]:
                    continue
                b = row[ib]
                for i in idx_dx:
                    if i < len(row) and row[i]:
                        dx[b].add(row[i].strip().upper().replace('.', ''))
                for i in idx_h:
                    if i < len(row) and row[i]:
                        hc[b].add(row[i].strip().upper())
    p = os.path.join(bfd, 'pde.csv')
    if os.path.exists(p):
        with open(p, newline='', encoding='utf-8', errors='replace') as fh:
            rd = csv.reader(fh, delimiter='|')
            hdr = next(rd)
            ib, ip = hdr.index('BENE_ID'), hdr.index('PROD_SRVC_ID')
            for row in rd:
                if len(row) > max(ib, ip) and row[ib] and row[ip]:
                    nd[row[ib]].add(row[ip].strip())
    return dx, hc, nd


def prefix_hit(codes, targets, lengths):
    for c in codes:
        for L in lengths:
            if c[:L] in targets:
                return True
    return False


def run(bfd, keys=None):
    dx, hc, nd = scan(bfd)
    benes = set(dx) | set(hc) | set(nd)
    out = {}
    for k, cfg in TA_CONFIG.items():
        if keys and k not in keys:
            continue
        lens = sorted({len(c) for c in cfg['dx_codes']})
        cohort = [b for b in benes if prefix_hit(dx.get(b, ()), cfg['dx_codes'], lens)]
        n = len(cohort)
        ourn, ourh = our_codes(cfg)
        if n == 0:
            out[k] = dict(n=0)
            continue
        seen, c2, c3, c4 = set(), 0, 0, 0
        for b in cohort:
            H, N = hc.get(b, set()), nd.get(b, set())
            j = H & cfg['target_j']
            seen |= j
            if j:
                c2 += 1
            if (N & cfg['target_ndc']) or (H & cfg['target_hcpcs']):
                c3 += 1
            if (N & ourn) or (H & ourh):
                c4 += 1
        out[k] = dict(n=n, total_benes=len(benes),
                      col1=(100.0 * len(seen) / len(cfg['target_j'])) if cfg['target_j'] else None,
                      col2=100.0 * c2 / n, col3=100.0 * c3 / n, col4=100.0 * c4 / n)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bfd', required=True)
    ap.add_argument('--ta', default='')
    ap.add_argument('--json', default='')
    a = ap.parse_args()
    keys = [k.strip().upper() for k in a.ta.split(',') if k.strip()] or None
    res = run(a.bfd, keys)

    def f(x):
        return '    -' if x is None else '%5.1f' % x
    print('%-32s%7s%8s%8s%8s%8s' % ('TA', 'N', 'col1', 'col2', 'col3', 'col4'))
    print('-' * 71)
    for k, cfg in TA_CONFIG.items():
        if k not in res:
            continue
        r = res[k]
        if not r.get('n'):
            print('%-32s%7d   -- no cohort --' % (cfg['name'][:31], 0))
            continue
        print('%-32s%7d%8s%8s%8s%8s' % (cfg['name'][:31], r['n'],
                                        f(r.get('col1')), f(r.get('col2')),
                                        f(r.get('col3')), f(r.get('col4'))))
    if a.json:
        json.dump(res, open(a.json, 'w'), indent=1)


if __name__ == '__main__':
    main()
