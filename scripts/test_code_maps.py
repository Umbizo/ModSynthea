#!/usr/bin/env python3
"""Assertions on export code maps. Pure JSON, no generation required."""
import json, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(ROOT, 'src', 'main', 'resources', 'export')
HCPCS = json.load(open(os.path.join(EXP, 'hcpcs_code_map.json')))
CONDITIONS = json.load(open(os.path.join(EXP, 'condition_code_map.json')))


def mapped_codes(snomed):
    return [e['code'] for e in (HCPCS.get(snomed) or [])]


def condition_weight(snomed, code):
    """Total weight on `code` among snomed's condition-map entries.
    Missing weight defaults to 1.0 (CodeMapper draws unweighted lists
    uniformly), so an explicit '0.0' is required to exclude a code."""
    return sum(float(e.get('weight', 1))
               for e in (CONDITIONS.get(snomed) or []) if e['code'] == code)


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







class TestHypertensionDiagnosisCode(unittest.TestCase):
    def test_essential_hypertension_cannot_resolve_to_neonatal_code(self):
        entries = CONDITIONS.get('59621000') or []
        non_i10_weight = sum(float(e.get('weight', 1)) for e in entries if e['code'] != 'I10')
        self.assertEqual(non_i10_weight, 0.0,
                          f'59621000 has nonzero weight on non-I10 codes: {entries}')


class TestHypertension(unittest.TestCase):
    def test_abpm_snomed_maps_to_abpm_cpt(self):
        got = set(mapped_codes('164847006'))
        self.assertTrue(got <= {'93784', '93786', '93788', '93790'} and got,
                        f'ABPM 164847006 -> {got}')

    def test_self_measured_bp_maps_to_smbp_cpt(self):
        got = set(mapped_codes('413153004'))
        self.assertTrue(got <= {'99473', '99474'} and got,
                        f'self-measured BP 413153004 -> {got}')




class TestPneumococcal(unittest.TestCase):
    def test_pneumococcal_vaccine_maps_to_vaccine_cpt(self):
        got = set(mapped_codes('12866006'))
        self.assertTrue(got <= {'90670', '90671', '90677', '90732'} and got,
                        f'pneumococcal vaccination 12866006 -> {got}')

    def test_vaccine_administration_maps_to_g0009(self):
        self.assertIn('G0009', mapped_codes('33879002'))



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
