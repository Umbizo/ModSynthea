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


class TestRheumatoidArthritis(unittest.TestCase):
    BIOLOGICS = {'J0135', 'J1438', 'J1745', 'J0129', 'J3262', 'J9312'}

    def test_emits_at_least_four_distinct_biologics(self):
        got = emitted_hcpcs('rheumatoid_arthritis') & self.BIOLOGICS
        self.assertGreaterEqual(len(got), 4, f'only {sorted(got)}')

    def test_biologics_are_flagged_administration(self):
        flags = administration_flags('rheumatoid_arthritis')
        for cui in ('1551887', '1653225', '213361', '1145929', '1441527'):
            self.assertTrue(flags.get(cui), f'RxCUI {cui} must set administration: true')

    def test_oral_methotrexate_remains_chronic(self):
        j = module('rheumatoid_arthritis')
        st = j['states']['DMARD']
        self.assertTrue(st.get('chronic'), 'oral methotrexate must stay chronic')
        self.assertFalse(st.get('administration'), 'oral MTX is Part D, not Part B')


class TestNSCLC(unittest.TestCase):
    IO = {'J9271', 'J9299', 'J9022', 'J9173', 'J9119', 'J9228'}
    ANTIANGIOGENIC = {'J9035', 'J9308'}

    def test_emits_at_least_four_distinct_checkpoint_inhibitors(self):
        got = emitted_hcpcs('non_small_cell_lung_cancer') & self.IO
        self.assertGreaterEqual(len(got), 4, f'only {sorted(got)}')

    def test_emits_an_antiangiogenic_agent(self):
        got = emitted_hcpcs('non_small_cell_lung_cancer') & self.ANTIANGIOGENIC
        self.assertTrue(got, 'neither bevacizumab nor ramucirumab is ordered')

    def test_new_agents_are_flagged_administration(self):
        flags = administration_flags('non_small_cell_lung_cancer')
        for cui in ('1657192', '1792776', '1657066', '2058830'):
            self.assertTrue(flags.get(cui), f'RxCUI {cui} must set administration: true')


class TestEndometrial(unittest.TestCase):
    TARGETED = {'J9271', 'J9272', 'J9035', 'J9355'}

    def test_emits_at_least_three_of_ricks_four_targeted_agents(self):
        got = emitted_hcpcs('endometrial_cancer') & self.TARGETED
        self.assertGreaterEqual(len(got), 3, f'only {sorted(got)}')

    def test_dostarlimab_is_ordered(self):
        self.assertIn('J9272', emitted_hcpcs('endometrial_cancer'))

    def test_targeted_agents_are_reachable(self):
        """col2 was 2.3% against col1 50% -- the arm existed but never fired."""
        j = module('endometrial_cancer')
        targets = set()
        for _n, s in j['states'].items():
            if isinstance(s.get('direct_transition'), str):
                targets.add(s['direct_transition'])
            for key in ('conditional_transition', 'distributed_transition', 'complex_transition'):
                for t in (s.get(key) or []):
                    if t.get('transition'):
                        targets.add(t['transition'])
                    for d in (t.get('distributions') or []):
                        if d.get('transition'):
                            targets.add(d['transition'])
        self.assertIn('Endometrial_Targeted_Selection', targets,
                      'the targeted-agent selector is unreachable')


if __name__ == '__main__':
    unittest.main()
