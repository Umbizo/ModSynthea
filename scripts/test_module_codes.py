#!/usr/bin/env python3
"""Assertions that modules emit the drug/procedure codes their TA needs."""
import glob, json, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, 'src', 'main', 'resources', 'modules')
EXP = os.path.join(ROOT, 'src', 'main', 'resources', 'export')
RX = json.load(open(os.path.join(EXP, 'rxnorm_hcpcs_map.json')))
HC = json.load(open(os.path.join(EXP, 'hcpcs_code_map.json')))


def module(stem):
    hits = glob.glob(os.path.join(MOD, '**', stem + '.json'), recursive=True)
    assert hits, f'no module named {stem}'
    return json.load(open(hits[0]))


def emitted_hcpcs(stem):
    j, out = module(stem), set()
    for _n, s in j['states'].items():
        if s.get('type') == 'MedicationOrder':
            for c in (s.get('codes') or []):
                for e in RX.get(str(c.get('code')), []):
                    out.add(e['code'].upper())
        elif s.get('type') == 'Procedure':
            for c in (s.get('codes') or []):
                for e in (HC.get(str(c.get('code'))) or []):
                    out.add(e['code'].upper())
    return out


def administration_flags(stem):
    """{rxcui: bool} -- True where the order is billed Part B as a J-code."""
    out = {}
    for _n, s in module(stem)['states'].items():
        if s.get('type') == 'MedicationOrder':
            for c in (s.get('codes') or []):
                out[str(c.get('code'))] = bool(s.get('administration'))
    return out


class TestProstateADT(unittest.TestCase):
    """Rick's prostate_cancer.csv lists five distinct ADT agents."""
    ADT = {'J9217', 'J1950', 'J9202', 'J3315', 'J9155'}

    def test_emits_at_least_four_distinct_adt_agents(self):
        got = emitted_hcpcs('prostate_cancer') & self.ADT
        self.assertGreaterEqual(len(got), 4, f'only {sorted(got)} of {sorted(self.ADT)}')

    def test_emits_bone_targeted_agents(self):
        got = emitted_hcpcs('prostate_cancer')
        self.assertIn('J0897', got, 'denosumab absent')
        self.assertIn('J3489', got, 'zoledronic acid absent')

    def test_emits_second_line_chemotherapy(self):
        self.assertIn('J9043', emitted_hcpcs('prostate_cancer'), 'cabazitaxel absent')

    def test_all_injected_agents_are_flagged_administration(self):
        flags = administration_flags('prostate_cancer')
        for cui in ('310592', '905053', '828749', '1046398', '1001433'):
            self.assertTrue(flags.get(cui), f'RxCUI {cui} must set administration: true')


if __name__ == '__main__':
    unittest.main()
