#!/usr/bin/env python3
"""Assertions on export code maps. Pure JSON, no generation required."""
import json, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(ROOT, 'src', 'main', 'resources', 'export')
HCPCS = json.load(open(os.path.join(EXP, 'hcpcs_code_map.json')))


def mapped_codes(snomed):
    return [e['code'] for e in (HCPCS.get(snomed) or [])]


class TestRevascularisation(unittest.TestCase):
    """Rick's ai_coronary_artery_disease.csv lists exactly these nine CPT codes."""

    def test_pci_maps_to_pci_cpt(self):
        got = set(mapped_codes('415070008'))
        self.assertTrue(got, 'PCI 415070008 is absent from hcpcs_code_map')
        self.assertTrue(got <= {'92920', '92928', '92933', '92937', '92941', '92943'},
                        f'PCI mapped outside the PTCA family: {got}')
        self.assertIn('92928', got, 'stent placement 92928 is the modal PCI code')

    def test_cabg_maps_to_cabg_cpt_not_a_quality_gcode(self):
        got = set(mapped_codes('232717009'))
        self.assertNotIn('G8159', got, 'G8159 is a quality measure, not a CABG procedure')
        self.assertTrue(got <= {'33510', '33533'}, f'CABG mapped outside 33510/33533: {got}')

    def test_emergency_and_offpump_cabg_also_map(self):
        for snomed in ('414088005', '418824004'):
            got = set(mapped_codes(snomed))
            self.assertTrue(got <= {'33510', '33533'} and got, f'{snomed} -> {got}')

    def test_coronary_angiography_maps_to_left_heart_cath(self):
        self.assertIn('93458', mapped_codes('33367005'))


class TestNoDuplicateKeys(unittest.TestCase):
    def test_hcpcs_map_has_no_duplicate_top_level_keys(self):
        """Gson keeps the LAST duplicate silently; json.load hides it identically."""
        seen, dupes = set(), []
        with open(os.path.join(EXP, 'hcpcs_code_map.json')) as fh:
            for line in fh:
                s = line.strip()
                if s.startswith('"') and s.rstrip(',').endswith('['):
                    k = s.split('"')[1]
                    (dupes.append(k) if k in seen else seen.add(k))
        self.assertEqual(dupes, [])


if __name__ == '__main__':
    unittest.main()
